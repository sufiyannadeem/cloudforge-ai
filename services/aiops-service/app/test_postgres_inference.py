"""Opt-in real PostgreSQL tests. Never touch an application/production database.

Set AI_TEST_POSTGRES_DSN to an empty LOCAL database named cloudforge_inference_test.
No server is started or downloaded. Offline CI without a server reports explicit skips.
"""
import os
from pathlib import Path
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
import psycopg
from psycopg.conninfo import conninfo_to_dict


@pytest.fixture(scope='module')
def postgres():
    dsn=os.getenv('AI_TEST_POSTGRES_DSN')
    if not dsn: pytest.skip('Local PostgreSQL server/AI_TEST_POSTGRES_DSN not provisioned')
    config=conninfo_to_dict(dsn)
    if config.get('host') not in {'127.0.0.1','localhost','::1'} or config.get('dbname')!='cloudforge_inference_test':
        pytest.fail('Requires dedicated empty local cloudforge_inference_test database')
    with psycopg.connect(dsn,connect_timeout=2,autocommit=True) as db:
        assert db.execute("SELECT count(*) FROM pg_tables WHERE schemaname='public'").fetchone()[0]==0
        db.execute('CREATE TABLE public.projects(id uuid PRIMARY KEY)')
        db.execute('CREATE TABLE public.aiops_incidents(id varchar(64) PRIMARY KEY)')
        sql=(Path(__file__).resolve().parents[1]/'migrations/004_secure_inference.sql').read_text()
        db.execute(sql)
    yield dsn
    with psycopg.connect(dsn,connect_timeout=2,autocommit=True) as db:
        db.execute('DROP FUNCTION public.cloudforge_reserve_inference(text,text,bigint)')
        db.execute('DROP TABLE public.aiops_incident_projects,public.ai_inference_usage,public.ai_inference_imports,public.ai_inference_budget,public.aiops_incidents,public.projects')


@pytest.fixture
def ledger(postgres):
    with psycopg.connect(postgres) as db:
        db.execute('TRUNCATE public.ai_inference_usage,public.ai_inference_imports')
        db.execute('UPDATE public.ai_inference_budget SET reserved_paise=0,imports_complete=true')
    return postgres


def reserve(dsn,nonce=None):
    with psycopg.connect(dsn,connect_timeout=2,options='-c statement_timeout=3000') as db:
        return db.execute("SELECT public.cloudforge_reserve_inference(%s,%s,extract(epoch FROM clock_timestamp())::bigint+20)",
                          (nonce or uuid4().hex,'a'*64)).fetchone()[0]


def test_postgres_concurrent_replicas_stop_at_360(ledger):
    with psycopg.connect(ledger) as db:
        db.execute('UPDATE public.ai_inference_budget SET reserved_paise=35700')
    with ThreadPoolExecutor(max_workers=12) as pool:
        results=list(pool.map(lambda _:reserve(ledger),range(12)))
    assert sum(results)==3
    with psycopg.connect(ledger) as db:
        assert db.execute('SELECT reserved_paise,cutoff_paise,maximum_paise FROM public.ai_inference_budget').fetchone()==(36000,36000,40000)


def test_postgres_replay_consumed_durably(ledger):
    nonce=uuid4().hex
    assert reserve(ledger,nonce)
    assert not reserve(ledger,nonce)
    with psycopg.connect(ledger) as db:
        assert db.execute('SELECT reserved_paise FROM public.ai_inference_budget').fetchone()[0]==100


def test_postgres_rate_and_migration_gate(ledger):
    with psycopg.connect(ledger) as db:
        db.execute('UPDATE public.ai_inference_budget SET imports_complete=false')
    assert not reserve(ledger)
    with psycopg.connect(ledger) as db:
        db.execute('UPDATE public.ai_inference_budget SET imports_complete=true')
    assert all(reserve(ledger) for _ in range(5))
    assert not reserve(ledger)


def test_postgres_legacy_import_never_refunds_or_duplicates(ledger):
    import importlib.util
    script=Path(__file__).resolve().parents[3]/'scripts/import-ai-budget.py'
    spec=importlib.util.spec_from_file_location('budget_import',script)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with psycopg.connect(ledger) as db:
        db.execute('UPDATE public.ai_inference_budget SET imports_complete=false')
        module.import_rows(db,'original-ledger',[(1,1.0,35000),(2,2.0,0)],'b'*64)
        module.import_rows(db,'original-ledger',[(1,1.0,35000),(2,2.0,0)],'b'*64)
        assert db.execute('SELECT reserved_paise FROM public.ai_inference_budget').fetchone()[0]==35000
        assert db.execute('SELECT count(*) FROM public.ai_inference_usage').fetchone()[0]==2
    with psycopg.connect(ledger) as db:
        with pytest.raises(ValueError): module.import_rows(db,'original-ledger',[],'c'*64)
