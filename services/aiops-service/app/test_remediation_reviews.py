"""Offline review state machine/API tests using an isolated transactional DB fixture.

The fixture serializes transactions and models SQL persistence, not PostgreSQL's
lock manager. Real PostgreSQL concurrency/ACL verification remains a release gate.
"""
import asyncio
import copy
import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4

import httpx2 as httpx
import pytest
from psycopg.types.json import Jsonb
from fastapi import HTTPException
from . import remediation_store, remediation_routes, project_evidence, main
from .remediation_store import RemediationStore
from .remediation_models import RemediationAction, RemediationStatus, PolicyDecision, RemediationProposal
from .remediation_integrity import fingerprint, contract, validate_approval, select_alternative
from .test_telemetry_api import KEY,signed_request

PROJECT='00000000-0000-0000-0000-000000000001'
TARGET='00000000-0000-0000-0000-000000000002'


class ReviewDB:
    def __init__(self):
        self.memberships={'proposer':'maintainer','reviewer':'maintainer','executor':'maintainer'}
        self.permissions={'proposer':'platform-engineer','reviewer':'platform-engineer','executor':'platform-engineer'}
        self.advisories={}
        self.rows={};self.reviews=[];self.events=[];self.lock=threading.RLock();self.queries=[]
        self.incident={'id':'owned','project_id':PROJECT,'status':'open','acknowledged_at':None,'revision':10}
        self.target={'id':TARGET,'project_id':PROJECT,'environment':'staging','status':'pending','revision':20,
                     'image':'image:pinned','git_commit_sha':'abcdef123','namespace':f'cf-{PROJECT}',
                     'execution_mode':'kubernetes','strategy':{'type':'rolling'},'created_by':'proposer'}
    @contextmanager
    def connection(self,**kwargs):
        with self.lock:
            snapshot=copy.deepcopy((self.rows,self.reviews,self.events,self.incident,self.advisories))
            try: yield self
            except BaseException:
                self.rows,self.reviews,self.events,self.incident,self.advisories=snapshot
                raise
    def execute(self,sql,args=()):
        sql=' '.join(sql.split());self.queries.append((sql,args));row=None;rows=[]
        values=[v.obj if isinstance(v,Jsonb) else v for v in args]
        if sql.startswith('SELECT i.id,i.status'):
            assert 'FOR UPDATE OF i' in sql
            row=self.incident if args[0]==self.incident['id'] else None
        elif sql.startswith('SELECT u.username'):
            row={'username':args[1]} if (self.permissions.get(args[1]) in args[2] and args[0]==PROJECT and
                ("m.level='maintainer'" not in sql or self.memberships.get(args[1])=='maintainer')) else None
        elif sql.startswith('SELECT id::text,project_id::text'):
            row=self.target if args[0]==TARGET and args[1]==self.target['project_id'] and args[2]==self.target['namespace'] else None
        elif sql.startswith('SELECT incident_id FROM aiops_remediation_proposals'):
            p=self.rows.get(args[0]);row={'incident_id':p['incident_id']} if p else None
        elif sql.startswith('SELECT alternative_result FROM aiops_remediation_proposals'):
            p=self.rows.get(args[0]);row={'alternative_result':p['alternative_result']} if p and p['incident_id']==args[1] and str(p['project_id'])==str(args[2]) else None
        elif sql.startswith('SELECT * FROM aiops_remediation_proposals WHERE incident_id'):
            rows=[p for p in self.rows.values() if p['incident_id']==args[0]]
        elif sql.startswith('SELECT b.project_id FROM'):
            row={'project_id':PROJECT} if args[2]=='owned' and self.permissions.get(args[0])==args[1] else None
        elif sql.startswith("SET LOCAL"):
            pass
        elif sql.startswith('SELECT * FROM aiops_remediation_proposals'):
            row=self.rows.get(args[0])
        elif sql.startswith('SELECT 1 FROM aiops_remediation_proposals'):
            from .remediation_integrity import action_family
            row=next(({'denied':1} for p in self.rows.values() if p['incident_id']==args[0] and action_family(p['action'])==args[1] and p['status']=='REJECTED'),None)
            if len(args)>2 and (args[2],str(args[3]),args[4]) in self.advisories:row={'denied':1}
        elif sql.startswith('SELECT COALESCE(MAX(recommendation_version)'):
            row={'version':max([p['recommendation_version'] for p in self.rows.values()],default=0)+1}
        elif sql.startswith('SELECT effect FROM aiops_advisory_rejections'):
            from .remediation_integrity import action_family
            effects={action_family(p['action']) for p in self.rows.values() if p['status']=='REJECTED'}
            effects.update(key[2] for key in self.advisories if key[0]==args[0] and key[1]==args[1])
            rows=[{'effect':effect} for effect in effects]
        elif sql.startswith('INSERT INTO aiops_advisory_rejections'):
            record=dict(zip(['incident_id','project_id','effect','action_fingerprint','resource_scope','actor','reason'],values))
            self.advisories.setdefault(tuple(values[:3]),record)
        elif sql.startswith('SELECT action_family FROM'):

            from .remediation_integrity import action_family
            rows=[{'action_family':action_family(p['action'])} for p in self.rows.values() if p['status']=='REJECTED']
        elif sql.startswith('INSERT INTO aiops_remediation_proposals'):
            columns=re.search(r'proposals \((.*?)\) VALUES',sql).group(1).split(',')
            fields={c.strip():v for c,v in zip(columns,values)}
            proposal=RemediationProposal(**fields)
            row=proposal.model_dump(mode='python')
            for key in ('status','action','policy_decision'):row[key]=row[key].value
            row.update(fields);row['approved_environment']=None;row['approved_contract']=None;row['alternative_result']=None
            row['state_snapshot']=fields['state_snapshot'];row['execution_idempotency_key']=None
            self.rows[row['id']]=row
        elif sql.startswith('INSERT INTO aiops_remediation_reviews'):
            self.reviews.append(dict(zip(['proposal_id','incident_id','project_id','recommendation_version','event_type','actor','reason'],values)))
        elif sql.startswith('INSERT INTO aiops_incident_events'):
            self.events.append(values)
        elif sql.startswith("UPDATE aiops_remediation_proposals SET status='APPROVED'"):
            row=self.rows[values[-1]]
            row.update(dict(zip(['approved_by','approved_role','approved_environment','approved_at','approved_contract','updated_at'],values[:-1])))
            row['status']='APPROVED'
        elif sql.startswith("UPDATE aiops_remediation_proposals SET status='REJECTED'"):
            row=self.rows[values[-1]];row.update(dict(zip(['rejected_by','rejection_reason','rejected_at','updated_at'],values[:-1])));row['status']='REJECTED'
        elif sql.startswith('UPDATE aiops_remediation_proposals SET alternative_result='):
            self.rows[values[1]]['alternative_result']=values[0]
        elif sql.startswith("UPDATE aiops_remediation_proposals SET status='EXECUTING'"):
            row=self.rows[values[-1]]
            if row['status']!='APPROVED' or row['execution_idempotency_key']:row=None
            else:
                row.update(dict(zip(['execution_requested_by','execution_idempotency_key','dispatch_token_hash','updated_at'],values[:-1])));row['status']='EXECUTING'
        elif sql.startswith('UPDATE aiops_incidents SET acknowledged_at='):
            self.incident['acknowledged_at']=values[0];self.incident['revision']+=1
        elif sql.startswith("UPDATE aiops_remediation_proposals SET status='SUCCEEDED'"):
            row=self.rows[values[-1]];row.update(status='SUCCEEDED',executed_at=values[0],result=values[1])
        elif sql.startswith('SELECT id,proposal_id,recommendation_version'):
            rows=[dict(id=i+1,created_at=datetime.now(timezone.utc),**r) for i,r in enumerate(self.reviews)]
        else: raise AssertionError(f'Unmocked SQL: {sql}')
        return SimpleNamespace(fetchone=lambda:copy.deepcopy(row),fetchall=lambda:copy.deepcopy(rows))


@pytest.fixture
def reviews(monkeypatch):
    db=ReviewDB();store=RemediationStore()
    monkeypatch.setattr(remediation_store,'get_connection',db.connection)
    return db,store


def propose(store,action=RemediationAction.RERUN_DEPLOYMENT,reason='Review pending deployment'):
    return store.create(incident_id='owned',action=action,status=RemediationStatus.PENDING_APPROVAL,
        policy_decision=PolicyDecision.REQUIRES_APPROVAL,policy_reason='Controlled action',reason=reason,
        target_deployment_id=TARGET if action==RemediationAction.RERUN_DEPLOYMENT else None,proposed_by='proposer')


def approve(store,p,actor='reviewer',role='platform-engineer'):
    return store.move_to_approved(p.id,actor,role,p.recommendation_version,p.action_fingerprint)


def test_optional_rejection_is_append_only_and_not_sent_to_general_timeline(reviews):
    db,store=reviews;p=propose(store)
    rejected=store.move_to_rejected(p.id,'reviewer')
    assert rejected.status==RemediationStatus.REJECTED and rejected.rejection_reason is None
    assert [r['event_type'] for r in db.reviews]==['proposed','rejected']
    with pytest.raises(PermissionError):store.move_to_rejected(p.id,'reviewer','overwrite')
    p=propose(store,RemediationAction.NO_ACTION)
    store.move_to_rejected(p.id,'reviewer','internal-secret-history')
    assert db.reviews[-1]['reason']=='internal-secret-history'
    assert 'internal-secret-history' not in str(db.events)


def test_reworded_and_parameter_only_duplicates_never_reappear(reviews):
    db,store=reviews;p=propose(store);store.move_to_rejected(p.id,'reviewer','no')
    for text in ('Retry with longer timeout','Please repeat this rollout'):
        with pytest.raises(PermissionError):propose(store,reason=text)
    assert fingerprint(PROJECT,'owned','restart_deployment')==fingerprint(PROJECT,'owned','rerun_deployment')
    assert fingerprint(PROJECT,'other','rerun_deployment')!=p.action_fingerprint


def test_alternative_has_new_version_no_inherited_approval_and_exhaustion(reviews):
    db,store=reviews;p=propose(store);approve(store,p);store.move_to_rejected(p.id,'reviewer')
    result=store.alternative(p.id,'proposer');child=store.get(result['proposal_id'])
    assert child.action==RemediationAction.ACKNOWLEDGE_INCIDENT and child.recommendation_version==2
    assert child.status==RemediationStatus.PENDING_APPROVAL and child.approved_by is None
    assert child.action_fingerprint!=p.action_fingerprint and child.alternative_of==p.id
    assert store.alternative(p.id,'proposer')==result
    store.move_to_rejected(child.id,'reviewer')
    exhausted=store.alternative(child.id,'proposer')
    assert exhausted['outcome']=='investigation_required' and exhausted['proposal_id'] is None
    assert len(db.rows)==2


@pytest.mark.parametrize('actor,role',[('proposer','platform-engineer'),('reviewer','sre'),('outsider','platform-engineer')])
def test_approval_requires_independent_current_platform_engineer(reviews,actor,role):
    db,store=reviews;p=propose(store)
    with pytest.raises(PermissionError):approve(store,p,actor,role)
    assert store.get(p.id).status==RemediationStatus.PENDING_APPROVAL


@pytest.mark.parametrize('change',['version','fingerprint','incident','target','expiry','parameters','identity'])
def test_stale_approval_is_denied(reviews,change):
    db,store=reviews;p=propose(store)
    if change=='version':p.recommendation_version+=1
    elif change=='fingerprint':p.action_fingerprint='0'*64
    elif change=='incident':db.incident['revision']+=1
    elif change=='target':db.target['image']='different:image'
    elif change=='expiry':db.rows[p.id]['expires_at']=datetime.now(timezone.utc)-timedelta(seconds=1)
    elif change=='parameters':db.rows[p.id]['parameters']={'replicas':2}
    elif change=='identity':db.rows[p.id]['proposed_by']='reviewer'
    with pytest.raises(PermissionError):approve(store,p)


def test_final_claim_revalidates_contract_and_current_state(reviews):
    db,store=reviews;p=propose(store);approve(store,p)
    db.target['revision']+=1
    with pytest.raises(PermissionError):store.claim_execution(p.id,'executor','same-key-123','a'*64)
    assert store.get(p.id).status==RemediationStatus.APPROVED
    db.target['revision']-=1
    assert store.claim_execution(p.id,'executor','same-key-123','a'*64).status==RemediationStatus.EXECUTING
    with pytest.raises(PermissionError):store.claim_execution(p.id,'executor','same-key-123','a'*64)


def test_concurrent_alternative_requests_create_one_version(reviews):
    db,store=reviews;p=propose(store);store.move_to_rejected(p.id,'reviewer')
    with ThreadPoolExecutor(max_workers=8) as pool:
        results=list(pool.map(lambda _:store.alternative(p.id,'proposer'),range(8)))
    assert len({r['proposal_id'] for r in results})==1 and len(db.rows)==2


def test_concurrent_approval_rejection_cannot_reopen_rejected_version(reviews):
    db,store=reviews;p=propose(store)
    def approval():
        try:return approve(store,p).status.value
        except PermissionError:return 'denied'
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(approval),pool.submit(store.move_to_rejected,p.id,'reviewer')]
        for f in futures:f.result()
    assert store.get(p.id).status==RemediationStatus.REJECTED
    with pytest.raises(PermissionError):approve(store,p)


def test_acknowledgement_is_atomic_in_operational_service(reviews):
    db,store=reviews;p=propose(store,RemediationAction.ACKNOWLEDGE_INCIDENT);approve(store,p)
    result=store.claim_execution(p.id,'executor','ack-key-123',None)
    assert result.status==RemediationStatus.SUCCEEDED and result.result=={'atomic_acknowledgement':True}
    assert db.incident['acknowledged_at'] is not None


def test_preexisting_duplicate_cannot_be_approved_after_rejection(reviews):
    db,store=reviews;p=propose(store);other=propose(store,reason='Different parameters')
    store.move_to_rejected(p.id,'reviewer')
    with pytest.raises(PermissionError):approve(store,other)


@pytest.fixture
def review_api(reviews,monkeypatch):
    db,store=reviews
    monkeypatch.setenv('CLOUDFORGE_FRONTEND_KEY',KEY)
    monkeypatch.setattr(project_evidence,'get_connection',db.connection)
    from .remediation_service import RemediationService
    incidents=SimpleNamespace(get=lambda ident:SimpleNamespace(id=ident,status=SimpleNamespace(value='open')))
    monkeypatch.setattr(remediation_routes,'service',RemediationService(incident_store=incidents,remediation_store=store))
    nonces=set();lock=threading.Lock()
    def claim(nonce,expiry):
        with lock:
            if nonce in nonces:return False
            nonces.add(nonce);return True
    monkeypatch.setattr(main,'claim_telemetry_assertion',claim)
    from .ai_provider import AIProvider
    def forbidden(*args,**kwargs):raise AssertionError('Review history must never reach inference')
    monkeypatch.setattr(AIProvider,'analyze',forbidden)
    return db,store


def api(path,body=None,*,actor='reviewer',role='platform-engineer',headers=None,method='POST'):
    encoded=json.dumps(body).encode() if body is not None else b''
    if headers is None:
        headers=dict(signed_request(path,method=method,sub=actor,role=role,nonce=uuid4().hex,
                     body=hashlib.sha256(encoded).hexdigest()).headers)
    headers={**headers, "Content-Type":"application/json"}
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app),base_url='https://testserver') as client:
            return await asyncio.wait_for(client.request(method,path,headers=headers,content=encoded),timeout=3)
    return asyncio.run(request())


def test_api_rejection_alternative_history_and_fresh_approval(review_api):
    db,store=review_api;p=propose(store)
    root=f'/api/v1/incidents/owned/remediation/{p.id}'
    response=api(root+'/reject',{'rejected_by':'forged','reason':'private-internal-reason'})
    assert response.status_code==200 and response.json()['rejected_by']=='reviewer'
    alt=api(root+'/alternative',actor='proposer')
    assert alt.status_code==200 and alt.json()['outcome']=='pending_approval'
    child=store.get(alt.json()['proposal_id'])
    assert child.approved_by is None
    # Knowing the child ID or having a previous approval cannot authorize execution.
    blocked=api(f'/api/v1/incidents/owned/remediation/{child.id}/execute',{'executed_by':'reviewer','idempotency_key':'bypass-key'})
    assert blocked.status_code==409
    approval=api(f'/api/v1/incidents/owned/remediation/{child.id}/approve',{
        'approved_by':'forged','expected_version':child.recommendation_version,'expected_fingerprint':child.action_fingerprint})
    assert approval.status_code==200 and approval.json()['approved_by']=='reviewer'
    history=api('/api/v1/incidents/owned/remediation/history',method='GET')
    assert history.status_code==200
    assert [r['event_type'] for r in history.json()['history']]==['proposed','rejected','proposed','approved']
    assert history.json()['history'][1]['reason']=='private-internal-reason'
    assert 'private-internal-reason' not in str(db.events)


def test_api_optional_reason_and_body_bound_replay(review_api):
    db,store=review_api;p=propose(store)
    path=f'/api/v1/incidents/owned/remediation/{p.id}/reject'
    body={'rejected_by':'forged'}
    headers=dict(signed_request(path,method='POST',sub='reviewer',role='platform-engineer',nonce=uuid4().hex,
                 body=hashlib.sha256(json.dumps(body).encode()).hexdigest()).headers)
    assert api(path,{**body,'reason':'tampered'},headers=headers).status_code==401
    assert api(path,body,headers=headers).status_code==200
    assert api(path,body,headers=headers).status_code==401
    assert len([r for r in db.reviews if r['event_type']=='rejected'])==1


@pytest.mark.parametrize('path_suffix,method',[('history','GET'),('preview','POST'),('proposal/alternative','POST'),('proposal/approve','POST'),('proposal/execute','POST')])
def test_api_cross_project_denied_before_recommendation_reads(review_api,path_suffix,method):
    db,store=review_api
    response=api(f'/api/v1/incidents/foreign/remediation/{path_suffix}',{},method=method)
    assert response.status_code==404
    assert not db.rows and not db.reviews
    assert not any('SELECT * FROM aiops_remediation_proposals' in sql for sql,args in db.queries)


def test_api_sre_cannot_approve_but_may_reject(review_api):
    db,store=review_api;db.permissions['proposer']='sre';p=propose(store)
    root=f'/api/v1/incidents/owned/remediation/{p.id}'
    assert api(root+'/approve',{'approved_by':'reviewer','expected_version':p.recommendation_version,
                               'expected_fingerprint':p.action_fingerprint},actor='proposer',role='sre').status_code==403
    assert api(root+'/reject',{'rejected_by':'proposer'},actor='proposer',role='sre').status_code==200


def test_api_wrong_proposal_incident_cannot_be_reviewed(review_api):
    db,store=review_api;p=propose(store)
    db.rows[p.id]['incident_id']='foreign'
    response=api(f'/api/v1/incidents/owned/remediation/{p.id}/alternative')
    assert response.status_code==404


def test_current_reviewer_revocation_and_foreign_target_deny(reviews):
    db,store=reviews;p=propose(store);approve(store,p)
    db.permissions.pop('reviewer')
    with pytest.raises(PermissionError):store.claim_execution(p.id,'executor','identity-key','a'*64)
    db.permissions['reviewer']='platform-engineer';db.target['project_id']='foreign'
    with pytest.raises(PermissionError):store.claim_execution(p.id,'executor','identity-key','a'*64)


def test_rejection_history_cannot_expand_disclosure_contract():
    from .inference_security import approved_payload
    with pytest.raises(ValueError):approved_payload(json.dumps({'evidence':[{'signal':'latency','state':'degraded'}],
        'rejections':[{'reason':'private'}]}))


def test_concurrent_execution_claims_have_one_winner(reviews):
    db,store=reviews;p=propose(store);approve(store,p)
    def claim(_):
        try:return store.claim_execution(p.id,'executor','concurrent-key','a'*64).status.value
        except PermissionError:return 'denied'
    with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(claim,range(8)))
    assert results.count('EXECUTING')==1 and results.count('denied')==7
    assert len([r for r in db.reviews if r['event_type']=='execution_claimed'])==1


@pytest.mark.parametrize('field,value',[('parameters',{'replicas':3}),('action','no_action'),
    ('approved_role','sre'),('approved_by','proposer'),('action_fingerprint','0'*64)])
def test_approved_contract_tampering_never_claims_execution(reviews,field,value):
    db,store=reviews;p=propose(store);approve(store,p);db.rows[p.id][field]=value
    with pytest.raises(PermissionError):store.claim_execution(p.id,'executor','tamper-key','a'*64)
    assert db.rows[p.id]['execution_idempotency_key'] is None


def test_expiry_cannot_be_extended_after_approval(reviews):
    db,store=reviews;p=propose(store);approve(store,p)
    db.rows[p.id]['expires_at']+=timedelta(hours=1)
    with pytest.raises(PermissionError):store.claim_execution(p.id,'executor','extended-key','a'*64)


def test_resolved_or_acknowledged_incident_has_no_invented_alternative():
    assert select_alternative({'status':'resolved','acknowledged_at':None},set()) is None
    assert select_alternative({'status':'open','acknowledged_at':'already'},set()) is None


def test_database_boundaries_do_not_grant_ai_mutation_or_review_history():
    from pathlib import Path
    root=Path(__file__).resolve().parents[3]
    sql=(root/'services/aiops-service/migrations/005_remediation_reviews.sql').read_text()
    grants=(root/'deploy/postgres/004_remediation_review_grants.sql').read_text()
    assert 'immutable_remediation BEFORE UPDATE' in sql
    assert "OLD.status IN ('REJECTED','EXPIRED','SUCCEEDED','FAILED')" in sql
    assert 'SECURITY DEFINER SET search_path=pg_catalog' in sql
    assert 'REVOKE ALL ON public.aiops_remediation_reviews FROM PUBLIC,cf_inference,cf_deployment' in grants
    assert 'GRANT SELECT,INSERT ON public.aiops_remediation_reviews TO cf_aiops' in grants
    docker=(root/'services/aiops-service/Dockerfile.inference').read_text()
    assert 'remediation' not in docker[docker.index('COPY app/__init__'):docker.index('USER 10001')]


def test_high_risk_deployment_author_cannot_approve_own_action(reviews):
    db,store=reviews;p=propose(store)
    # A different recommendation proposer does not erase the deployment requester.
    db.rows[p.id]['proposed_by']='executor'
    with pytest.raises(PermissionError):approve(store,p,actor='proposer')


def test_project_viewer_cannot_approve_or_execute_mutation(reviews):
    db,store=reviews;p=propose(store);db.memberships['reviewer']='viewer'
    with pytest.raises(PermissionError):approve(store,p)
    db.memberships['reviewer']='maintainer';approve(store,p);db.memberships['executor']='viewer'
    with pytest.raises(PermissionError):store.claim_execution(p.id,'executor','viewer-denied-key','a'*64)
