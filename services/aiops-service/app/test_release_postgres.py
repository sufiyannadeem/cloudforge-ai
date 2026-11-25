"""REAL PostgreSQL full migration/ACL/store gate; disposable externally supplied DB only.

No server/database/role provisioning. Set RELEASE_TEST_POSTGRES_DSN to an EMPTY
local cloudforge_release_test on a dedicated test cluster with precreated service
roles and pgcrypto, plus RELEASE_TEST_ALLOW_SCHEMA_RESET=yes-disposable-public.
The public schema is deleted on cleanup. Never use a shared/production database.
"""
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
from uuid import uuid4
import pytest
import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row
from psycopg import sql
from fastapi import HTTPException

ROOT=Path(__file__).resolve().parents[3]
ROLES=('cf_migrator','cf_project','cf_infrastructure','cf_deployment','cf_aiops',
       'cf_finops_project','cf_finops_audit','cf_drift','cf_inference')


@pytest.fixture(scope='module')
def release_database():
    dsn=os.getenv('RELEASE_TEST_POSTGRES_DSN')
    if not dsn:pytest.skip('Explicit disposable release PostgreSQL database not supplied')
    config=conninfo_to_dict(dsn)
    if (config.get('host') not in {'127.0.0.1','localhost','::1'}
        or config.get('dbname')!='cloudforge_release_test'
        or os.getenv('RELEASE_TEST_ALLOW_SCHEMA_RESET')!='yes-disposable-public'):
        pytest.fail('Requires explicit isolated DB/schema-reset authorization')
    @contextmanager
    def connect(role=None,**kwargs):
        with psycopg.connect(dsn,connect_timeout=2,row_factory=dict_row,
                              options='-c statement_timeout=15000 -c lock_timeout=5000') as db:
            if role:
                assert role in ROLES
                db.execute('SET ROLE '+role)
            yield db
    with connect() as db:
        assert db.execute("SELECT count(*) AS n FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')").fetchone()['n']==0
        existing={r['rolname'] for r in db.execute('SELECT rolname FROM pg_roles WHERE rolname=ANY(%s)',(list(ROLES),))}
        assert existing==set(ROLES),'Service roles must be preprovisioned on the isolated test cluster'
        assert db.execute("SELECT 1 FROM pg_extension WHERE extname='pgcrypto'").fetchone(),'Preprovision pgcrypto'
    try:
        # Actual SQL sources, actual Python migration, actual identities; no invented baseline schema.
        with connect() as db:
            db.execute(sql.SQL('REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC').format(sql.Identifier(config['dbname'])))
            db.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
            db.execute((ROOT/'deploy/postgres/001_principals.sql').read_text())
        with connect('cf_migrator') as db:
            for service in ('project-service','infrastructure-service','deployment-service'):
                for path in sorted((ROOT/'services'/service/'internal/migration/migrations').glob('*.sql')):
                    db.execute(path.read_text())
        from . import database
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv('APP_ENV','development') # Only explicit local test DSN; production TLS gates tested separately.
            patch.setattr(database,'get_connection',lambda **kw:connect('cf_migrator'))
            database.initialize_database(migration=True)
        with connect('cf_migrator') as db:
            for _ in range(2):
                for path in sorted((ROOT/'services/aiops-service/migrations').glob('*.sql')):db.execute(path.read_text())
        with connect() as db:
            # All roles already exist; bootstrap creates no roles on this test cluster.
            for path in sorted((ROOT/'deploy/postgres').glob('*.sql')):db.execute(path.read_text())
        yield connect
    finally:
        with connect() as db:
            db.execute('RESET ROLE')
            db.execute('DROP SCHEMA public CASCADE; CREATE SCHEMA public')


def test_real_effective_acl_boundaries(release_database):
    connect=release_database
    with connect() as db:
        rows=db.execute("""SELECT c.oid,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                            WHERE n.nspname='public' AND c.relkind IN ('r','p','v','S')""").fetchall()
        for row in rows:
            if row['relkind']=='S':
                assert not db.execute("SELECT has_sequence_privilege('cf_inference',%s,'USAGE,SELECT,UPDATE') AS p",(row['oid'],)).fetchone()['p']
            else:
                assert not db.execute("SELECT has_any_column_privilege('cf_inference',%s,'SELECT,INSERT,UPDATE,REFERENCES') AS p",(row['oid'],)).fetchone()['p']
        assert db.execute("SELECT has_function_privilege('cf_inference','cloudforge_reserve_inference(text,text,bigint)','EXECUTE') AS p").fetchone()['p']
        for table in ('aiops_remediation_reviews','aiops_advisory_rejections'):
            assert not db.execute("SELECT has_table_privilege('cf_aiops',%s,'UPDATE,DELETE,TRUNCATE') AS p",(table,)).fetchone()['p']
        assert db.execute("SELECT has_column_privilege('cf_deployment','aiops_advisory_rejections','effect','SELECT') AS p").fetchone()['p']
        assert not db.execute("SELECT has_column_privilege('cf_deployment','aiops_advisory_rejections','reason','SELECT') AS p").fetchone()['p']
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connect('cf_inference') as db:db.execute('SELECT * FROM aiops_incidents')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connect('cf_deployment') as db:db.execute('SELECT reason FROM aiops_advisory_rejections')


@pytest.fixture
def live_store(release_database,monkeypatch):
    from . import remediation_store,project_evidence
    connect=release_database
    monkeypatch.setattr(remediation_store,'get_connection',lambda **kw:connect('cf_aiops'))
    monkeypatch.setattr(project_evidence,'get_connection',lambda **kw:connect('cf_aiops'))
    project=uuid4();foreign=uuid4();incident='release-'+uuid4().hex
    with connect('cf_project') as db:
        for user in ('review-proposer','review-pe','review-outsider'):
            db.execute("INSERT INTO auth_users(username,role,password_hash,password_salt) VALUES(%s,'platform-engineer',decode(repeat('00',32),'hex'),decode(repeat('01',32),'hex')) ON CONFLICT DO NOTHING",(user,))
        for ident,owner in ((project,'review-pe'),(foreign,'review-outsider')):
            db.execute("INSERT INTO projects(id,name,repository_url,created_by) VALUES(%s,%s,'https://example.invalid/repo',%s)",(ident,str(ident),owner))
        db.execute("INSERT INTO project_members VALUES(%s,'review-proposer','maintainer')",(project,))
    with connect('cf_aiops') as db:
        db.execute("""INSERT INTO aiops_incidents(id,fingerprint,alert_name,service,severity,status,summary,probable_cause,created_at,updated_at)
                      VALUES(%s,%s,'Test','deployment-service','warning','open','test','unknown',clock_timestamp(),clock_timestamp())""",(incident,uuid4().hex))
    with connect('cf_migrator') as db:db.execute("INSERT INTO aiops_incident_projects(incident_id,project_id,verified_by) VALUES(%s,%s,'isolated-fixture')",(incident,project))
    return remediation_store.RemediationStore(),incident,str(project),connect


def proposal(store,incident):
    from .remediation_models import RemediationAction,RemediationStatus,PolicyDecision
    return store.create(incident_id=incident,action=RemediationAction.ACKNOWLEDGE_INCIDENT,
        status=RemediationStatus.PENDING_APPROVAL,policy_decision=PolicyDecision.REQUIRES_APPROVAL,
        policy_reason='test',reason='isolated test',target_deployment_id=None,proposed_by='review-proposer')


def test_real_server_membership_unknown_and_cross_project(live_store):
    from .project_evidence import authorize_incident
    _,incident,project,_=live_store
    assert authorize_incident(incident,{'sub':'review-pe','role':'platform-engineer'})==project
    for ident,user in ((incident,'review-outsider'),('unknown','review-pe')):
        with pytest.raises(HTTPException):authorize_incident(ident,{'sub':user,'role':'platform-engineer'})


def test_real_review_rejection_and_immutable_advisory(live_store):
    store,incident,project,connect=live_store
    row=proposal(store,incident)
    with pytest.raises(PermissionError):store.move_to_approved(row.id,'review-proposer','platform-engineer',row.recommendation_version,row.action_fingerprint)
    store.move_to_rejected(row.id,'review-pe','internal only')
    with pytest.raises(PermissionError):proposal(store,incident)
    store.reject_advisory(incident,'review-pe','inspect_memory','internal reason')
    store.reject_advisory(incident,'review-pe','inspect_memory','replacement must not overwrite')
    with connect('cf_aiops') as db:
        assert db.execute('SELECT count(*) AS n FROM aiops_advisory_rejections WHERE incident_id=%s',(incident,)).fetchone()['n']==1
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        with connect('cf_aiops') as db:db.execute('UPDATE aiops_advisory_rejections SET reason=NULL WHERE incident_id=%s',(incident,))


def test_real_atomic_ack_claim_concurrency_and_replay(live_store):
    store,incident,_,connect=live_store;row=proposal(store,incident)
    store.move_to_approved(row.id,'review-pe','platform-engineer',row.recommendation_version,row.action_fingerprint)
    def claim(_):
        try:store.claim_execution(row.id,'review-pe',uuid4().hex,None);return True
        except PermissionError:return False
    with ThreadPoolExecutor(max_workers=4) as pool:assert sum(pool.map(claim,range(4)))==1
    with connect('cf_aiops') as db:
        assert db.execute('SELECT acknowledged_by FROM aiops_incidents WHERE id=%s',(incident,)).fetchone()['acknowledged_by']=='review-pe'
        assert db.execute("SELECT count(*) AS n FROM aiops_remediation_reviews WHERE incident_id=%s AND event_type='execution_claimed'",(incident,)).fetchone()['n']==1
