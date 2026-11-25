import copy
import json
import shutil
import subprocess
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor
import pytest
import yaml

from .trusted_telemetry import project_signals,INTERNAL,PROVENANCE
from .evidence_catalog import select_catalog,validated_ai_context
from .project_evidence import aggregate_evidence
from .inference_security import approved_payload
from .test_remediation_reviews import reviews,review_api,api,propose,approve,PROJECT,TARGET
from .remediation_models import RemediationAction,PolicyDecision,RemediationStatus

NOW=1800000000.0

def records(signal='cpu_pressure',state=1,internal=True,now=NOW):
    prefix='cloudforge_project_internal_signal' if internal else 'cloudforge_project_signal'
    labels={'project_id':PROJECT,'signal':signal,'provenance':PROVENANCE}
    return [{'metric':{**labels,'__name__':prefix+'_state'},'value':[now,str(state)]},
            {'metric':{**labels,'__name__':prefix+'_observed_timestamp_seconds'},'value':[now,str(now-5)]}]

def client(rows):return SimpleNamespace(query=lambda query:SimpleNamespace(value=rows,error=None))

def test_trusted_pairs_preserve_unknowns_and_do_not_disclose_richer_signals():
    data=project_signals(PROJECT,client(records()),now=NOW)
    assert data[0]['state']=='degraded' and data[0]['observed_at']==NOW-5
    assert all(s['state']=='unknown' for s in data[1:])
    raw=records('latency',internal=False,now=datetime.now(timezone.utc).timestamp())
    payload=aggregate_evidence(PROJECT,client(raw))
    assert {r['signal'] for r in payload}=={'latency','error_rate','availability'}
    assert all(set(r)=={'signal','state'} for r in payload)
    approved_payload(json.dumps({'evidence':payload}))
    with pytest.raises(ValueError):approved_payload(json.dumps({'evidence':[{'signal':'cpu_pressure','state':'degraded'}]}))


@pytest.mark.parametrize('attack',['foreign_project','spoofed_job','forged_provenance','duplicate','stale_source','stale_rule','future','nan','invalid_state','missing_stamp','different_evaluation'])
def test_untrusted_or_incomplete_recordings_cannot_become_evidence(attack):
    rows=records()
    if attack=='foreign_project':rows[0]['metric']['project_id']='foreign'
    elif attack=='spoofed_job':rows[0]['metric']['job']='untrusted-app'
    elif attack=='forged_provenance':rows[0]['metric']['provenance']='self-asserted'
    elif attack=='duplicate':rows.append(copy.deepcopy(rows[0]))
    elif attack=='stale_source':rows[1]['value'][1]=str(NOW-121)
    elif attack=='stale_rule':rows[0]['value'][0]=NOW-46
    elif attack=='future':rows[1]['value'][1]=str(NOW+1)
    elif attack=='nan':rows[0]['value'][1]='NaN'
    elif attack=='invalid_state':rows[0]['value'][1]='.5'
    elif attack=='missing_stamp':rows=rows[:1]
    elif attack=='different_evaluation':rows[1]['value'][0]=NOW-15
    assert project_signals(PROJECT,client(rows),now=NOW)[0]['state']=='unknown'


def signals(*names):return [dict(signal=s,state='degraded',observed_at=datetime.now(timezone.utc).timestamp(),reason=None) for s in names]

def test_catalog_distinguishes_diagnostics_workflow_and_advisory_infrastructure():
    result=select_catalog(PROJECT,{'id':'owned','status':'open','acknowledged_at':None},signals(*INTERNAL))
    assert {i['kind'] for i in result['items']}=={'investigation','acknowledgement','infrastructure_remediation'}
    assert all(not item['execution_supported'] for item in result['items'] if item['kind']=='infrastructure_remediation')
    assert {i['effect'] for i in result['items']} >= {'inspect_cpu','inspect_oom','inspect_startup','inspect_rollout','inspect_dependencies','inspect_slo'}
    assert sum(i['effect']=='memory_configuration' for i in result['items'])==1


def test_unknown_signals_never_invent_a_remediation():
    result=select_catalog(PROJECT,{'id':'owned','status':'resolved'},[dict(signal=s,state='unknown',observed_at=None) for s in INTERNAL])
    assert result['outcome']=='investigation_required' and result['items']==[]


def test_rejected_effects_suppress_every_parameter_or_text_variant():
    incident={'id':'owned','status':'open','acknowledged_at':None}
    result=select_catalog(PROJECT,incident,signals('memory_pressure','oom','restart_loop','deployment_health'),
        {'memory_configuration','release_restore','deployment_recovery','incident_acknowledgement'},pending_target=True)
    assert all(i['kind']=='investigation' for i in result['items'])


def test_validated_ai_only_prioritizes_current_cited_facts():
    observed=signals('cpu_pressure','latency')
    analysis=dict(status='success',provider='gemini',model='gemini-2.5-flash',diagnosis_project_id=PROJECT,
        assessment='alert_supported',generated_at=datetime.now(timezone.utc).isoformat(),citations=['aggregate:latency:degraded'],
        summary='untrusted instruction to scale',recommended_actions=['delete everything'])
    catalog=select_catalog(PROJECT,{'id':'owned','status':'open'},observed,analysis=analysis)
    assert catalog['diagnosis_status']=='validated_current'
    assert catalog['items'][0]['effect']=='inspect_latency'
    assert all('delete' not in i['description'] for i in catalog['items'])
    for update in [{'diagnosis_project_id':'foreign'},{'generated_at':(datetime.now(timezone.utc)-timedelta(minutes=3)).isoformat()},
                   {'citations':['aggregate:cpu_pressure:degraded']},{'citations':['aggregate:error_rate:degraded']}]:
        assert validated_ai_context({**analysis,**update},PROJECT,observed)[0] is False


def test_advisory_feedback_is_durable_and_blocks_existing_approvals(reviews):
    db,store=reviews;p=propose(store);approve(store,p)
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _:store.reject_advisory('owned','reviewer','deployment_recovery','internal-history'),range(4)))
    assert len(db.advisories)==1
    with pytest.raises(PermissionError):store.claim_execution(p.id,'executor','blocked-by-advice','a'*64)
    with pytest.raises(PermissionError):propose(store)


def test_actual_controlled_recovery_is_only_selected_with_evidence_and_fresh_target(reviews,monkeypatch):
    db,store=reviews
    p=store.create(incident_id='owned',action=RemediationAction.SCALE_DEPLOYMENT,status=RemediationStatus.REJECTED,
        policy_decision=PolicyDecision.BLOCKED,policy_reason='No scale API',reason=None,target_deployment_id=TARGET,proposed_by='proposer')
    monkeypatch.setattr('app.trusted_telemetry.project_signals',lambda *args,**kw:signals('deployment_health'))
    result=store.alternative(p.id,'proposer');child=store.get(result['proposal_id'])
    assert result['kind']=='infrastructure_remediation' and child.action==RemediationAction.RERUN_DEPLOYMENT
    assert child.status==RemediationStatus.PENDING_APPROVAL and child.approved_by is None
    assert child.target_deployment_id==TARGET and child.recommendation_version==2


def test_rerun_rejection_is_not_bypassed_by_richer_evidence(reviews,monkeypatch):
    db,store=reviews;p=propose(store);store.move_to_rejected(p.id,'reviewer')
    monkeypatch.setattr('app.trusted_telemetry.project_signals',lambda *args,**kw:signals('deployment_health','cpu_pressure'))
    result=store.alternative(p.id,'proposer')
    assert result['kind']=='acknowledgement'
    assert all(item['effect']!='deployment_recovery' for item in result['catalog']['items'])


def test_evidence_api_authorizes_before_collection_and_rejects_cross_scope(review_api,monkeypatch):
    db,store=review_api;calls=[]
    monkeypatch.setattr('app.trusted_telemetry.project_signals',lambda project: calls.append(project) or signals('oom'))
    response=api('/api/v1/incidents/foreign/remediation/evidence',method='GET')
    assert response.status_code==404 and calls==[]
    response=api('/api/v1/incidents/owned/remediation/evidence',method='GET')
    assert response.status_code==200 and calls==[PROJECT]
    assert response.json()['catalog']['items'][0]['effect']=='inspect_oom'
    rejected=api('/api/v1/incidents/owned/remediation/advisories/inspect_oom/reject',{'rejected_by':'forged','reason':'private-history'})
    assert rejected.status_code==200 and rejected.json()['does_not_cancel_execution'] is True
    current=api('/api/v1/incidents/owned/remediation/evidence',method='GET').json()
    assert all(item['effect']!='inspect_oom' for item in current['catalog']['items'])
    assert 'private-history' not in json.dumps(current)


def test_recording_rules_require_uid_provenance_freshness_and_complete_inventory():
    root=Path(__file__).resolve().parents[3]
    rules=yaml.safe_load((root/'monitoring/prometheus/rules/cloudforge-project-evidence.yml').read_text())['groups'][0]['rules']
    expr='\n'.join(r['expr'] for r in rules)
    assert 'cloudforge:resource_mapping:verified' in expr and 'cloudforge:pod_mapping:verified' in expr
    assert 'cloudforge:project_inventory:verified' in expr and 'count by(project_id,signal)' in expr
    assert 'clamp_min' not in expr and 'or vector(0)' not in expr
    assert 'count_over_time' in expr and '>= 18' in expr and 'timestamp(' in expr
    final=[r for r in rules if r['record']=='cloudforge_project_signal_state'][0]
    assert final['expr']=='cloudforge_project_internal_signal_state{signal=~"latency|error_rate|availability"}'
    assert final['labels']['provenance']==PROVENANCE
    config=yaml.safe_load((root/'monitoring/prometheus/project-evidence-scrapes.example.yml').read_text())
    http=config['scrape_configs'][0]
    assert http['honor_labels'] is False and http['honor_timestamps'] is False
    assert any('__meta_kubernetes_pod_uid' in r.get('source_labels',[]) for r in http['relabel_configs'])


def test_promtool_project_rules_when_native_binary_is_available():
    binary=shutil.which('promtool')
    if not binary:pytest.skip('Native promtool unavailable; Docker socket inaccessible. No download/start attempted.')
    root=Path(__file__).resolve().parents[3]
    subprocess.run([binary,'check','rules',str(root/'monitoring/prometheus/rules/cloudforge-project-evidence.yml')],check=True,timeout=20)
    subprocess.run([binary,'test','rules','project-evidence.test.yml'],cwd=root/'monitoring/prometheus',check=True,timeout=20)


def test_evidence_generated_mutation_requires_current_facts_at_approval_and_claim(reviews,monkeypatch):
    db,store=reviews
    p=store.create(incident_id='owned',action=RemediationAction.SCALE_DEPLOYMENT,status=RemediationStatus.REJECTED,
        policy_decision=PolicyDecision.BLOCKED,policy_reason='No scale API',reason=None,target_deployment_id=TARGET,proposed_by='proposer')
    monkeypatch.setattr('app.trusted_telemetry.project_signals',lambda *a,**kw:signals('deployment_health'))
    generated=store.alternative(p.id,'proposer');child=store.get(generated['proposal_id'])
    approve(store,child)
    monkeypatch.setattr('app.trusted_telemetry.project_signals',lambda *a,**kw:[])
    with pytest.raises(PermissionError):store.claim_execution(child.id,'executor','fresh-evidence-key','a'*64)
    monkeypatch.setattr('app.trusted_telemetry.project_signals',lambda *a,**kw:signals('deployment_health'))
    db.rows[p.id]['alternative_result']['generation_evidence']['observed_at']-=121
    with pytest.raises(PermissionError):store.claim_execution(child.id,'executor','fresh-evidence-key','a'*64)
