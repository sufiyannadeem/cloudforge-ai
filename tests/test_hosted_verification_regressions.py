"""Lightweight gate regressions; not evidence of native Terraform/PostgreSQL success."""
import json
import os
from pathlib import Path
import re
import runpy
import sqlite3
import subprocess
import sys

import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]


def workflow():
    return yaml.load((ROOT/'.github/workflows/consolidated-release-verification.yml').read_text(),
                     Loader=yaml.BaseLoader)


def test_hosted_module_acquisition_precedes_every_provider_mirror(tmp_path):
    steps=workflow()['jobs']['native']['steps']
    step=next(s for s in steps if s.get('name')=='Acquire only lockfile-verified Terraform providers (hosted CI only)')
    assert step['if']=="inputs.runner_profile == 'hosted'"
    script=tmp_path/'terraform'
    script.write_text('#!'+sys.executable+'\n'+'''import json, os, pathlib, sys
trace=pathlib.Path(os.environ['CF_TERRAFORM_TRACE'])
calls=json.loads(trace.read_text()) if trace.exists() else []
args=sys.argv[1:]
root=args[0].removeprefix('-chdir=')
if args[1]=='get':
    assert args[2:]==['-no-color','-update=false']
elif args[1:3]==['providers','mirror']:
    assert any(c[0]==args[0] and c[1]=='get' for c in calls), 'Module not installed'
    assert args[3]=='-platform=linux_amd64'
else:
    raise AssertionError('Unexpected Terraform/backend/provider initialization')
calls.append(args)
trace.write_text(json.dumps(calls))
''')
    script.chmod(0o755)
    trace=tmp_path/'trace.json'
    env=dict(os.environ,PATH=str(tmp_path)+os.pathsep+os.environ['PATH'],
             CF_TERRAFORM_TRACE=str(trace),RUNNER_TEMP=str(tmp_path),GITHUB_ENV=str(tmp_path/'github-env'))
    subprocess.run(['bash','-euo','pipefail','-c',step['run']],cwd=ROOT,env=env,check=True,capture_output=True)
    calls=json.loads(trace.read_text())
    roots={'-chdir=infrastructure/terraform/bootstrap','-chdir=infrastructure/terraform/environments/dev'}
    assert len(calls)==4
    assert {c[0] for c in calls[:2]}=={c[0] for c in calls[2:]}==roots
    assert all(c[1]=='get' for c in calls[:2])
    assert 'TF_OFFLINE_PROVIDER_MIRROR='+str(tmp_path/'terraform-mirror') in (tmp_path/'github-env').read_text()


def test_offline_validation_never_downloads_modules(tmp_path,monkeypatch):
    module=runpy.run_path(str(ROOT/'tests/test_ci_pipeline_hardening.py'))
    mirror=tmp_path/'mirror';mirror.mkdir()
    monkeypatch.setenv('TF_OFFLINE_PROVIDER_MIRROR',str(mirror))
    calls=[]
    def fake_run(args,**kwargs):
        calls.append(args)
        if args[1]=='init':
            assert {'-backend=false','-lockfile=readonly','-input=false','-get=false'}<=set(args)
            config=Path(kwargs['env']['TF_CLI_CONFIG_FILE']).read_text()
            assert 'filesystem_mirror' in config and 'direct' not in config
        else:
            assert args==['terraform','validate']
        return subprocess.CompletedProcess(args,0,'','')
    monkeypatch.setattr(subprocess,'run',fake_run)
    module['test_terraform_validate_bootstrap_and_dev'](tmp_path)
    assert len(calls)==4


@pytest.mark.parametrize('grant_kind',['table','column','sequence'])
def test_actual_acl_predicates_guard_mixed_relation_types(grant_kind):
    """Execute actual CASE predicates with SQLite type-checking UDFs, not PostgreSQL."""
    source=(ROOT/'deploy/postgres/003_inference_grants.sql').read_text()
    predicates=re.findall(r'AND (CASE WHEN c\.relkind.*?END)',source,re.S)
    assert len(predicates)==2, 'Both type-sensitive privilege expressions need CASE guards'
    table_kinds={'r','p','v','m','f'}
    kinds=['r','p','v','m','f','S','i','I','c','t']
    relation_kinds=dict(enumerate(kinds,1))
    grants=set()
    db=sqlite3.connect(':memory:')
    try:
        db.execute('CREATE TABLE relations(oid integer,relkind text)')
        db.executemany('INSERT INTO relations VALUES (?,?)',relation_kinds.items())
        def privilege(kind,allowed,expected):
            def check(role,oid,privileges):
                assert role=='cf_inference' and privileges==expected
                if relation_kinds[oid] not in allowed:
                    raise ValueError('WrongObjectType')
                return (kind,oid) in grants
            return check
        for name,kind,allowed,privileges in (
            ('has_table_privilege','table',table_kinds,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'),
            ('has_any_column_privilege','column',table_kinds,'SELECT,INSERT,UPDATE,REFERENCES'),
            ('has_sequence_privilege','sequence',{'S'},'USAGE,SELECT,UPDATE'),
        ):
            db.create_function(name,3,privilege(kind,allowed,privileges))
        def violations():
            return {row[0] for p in predicates for row in db.execute('SELECT c.oid FROM relations c WHERE '+p)}
        assert violations()==set()
        target=6 if grant_kind=='sequence' else 1
        grants.add((grant_kind,target))
        assert violations()=={target}
    finally:
        db.close()


@pytest.mark.parametrize('profile',['hosted','dedicated'])
@pytest.mark.parametrize('failure',['none','native','postgres','plan','inactive','missing'])
def test_aggregate_keeps_all_active_jobs_mandatory(profile,failure,monkeypatch):
    step=workflow()['jobs']['integration-verification']['steps'][0]
    script=step['run'].split("python3 - <<'PY'\n",1)[1].rsplit('\nPY',1)[0]
    results={key:{'result':'success'} for key in ('plan','native','postgres-'+profile)}
    inactive='postgres-'+('dedicated' if profile=='hosted' else 'hosted')
    results[inactive]={'result':'skipped'}
    if failure=='inactive':results[inactive]['result']='success'
    elif failure=='missing':results.pop('native')
    elif failure!='none':results['postgres-'+profile if failure=='postgres' else failure]['result']='failure'
    monkeypatch.setenv('PROFILE',profile)
    monkeypatch.setenv('RESULTS',json.dumps(results))
    if failure=='none':
        exec(compile(script,'aggregate-workflow','exec'),{})
    else:
        with pytest.raises(AssertionError):exec(compile(script,'aggregate-workflow','exec'),{})
