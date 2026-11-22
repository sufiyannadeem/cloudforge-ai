"""Offline stale-source/digest protection. Synthetic hashes are never release inputs."""
import copy
import json
from pathlib import Path
import runpy
import pytest
ROOT=Path(__file__).resolve().parents[1]
m=runpy.run_path(str(ROOT/'scripts/check-release-readiness.py'))

def candidate():
    p={'repository':'sufiyannadeem/cloudforge-ai','approved_revision':'a'*40,'run_id':'999','run_attempt':'1'}
    release={'revision':p['approved_revision'],'run_id':'999','run_attempt':'1',
             'images':{s:f'ghcr.io/{p["repository"]}/{s}@sha256:'+('b'*64) for s in m['RELEASE']['SERVICES']},
             'provenance':{s:{'image_id':'sha256:'+'c'*64,'archive_sha256':'d'*64,'sbom_sha256':'e'*64} for s in m['RELEASE']['SERVICES']}}
    return p,release

def test_new_manifest_config_digest_can_differ_from_registry_digest():
    p,r=candidate();assert m['validate_candidate'](p,r)['structural_freshness']=='PASS'
    assert m['validate_candidate'](p,r)['cryptographic_verification'].startswith('REQUIRED')

def test_unbound_historical_revision_and_run_mismatches_rejected():
    p,r=candidate()
    for change in ({'approved_revision':None},{'approved_revision':json.loads(m['HISTORY'].read_text())['revision']},{'run_id':'44886817455'},{'run_attempt':None}):
        bad=copy.deepcopy(p);bad.update(change)
        with pytest.raises((ValueError,TypeError)):m['validate_candidate'](bad,r)

@pytest.mark.parametrize('failure',['stale','tag','config_id','wrong_repo','missing','provenance'])
def test_rejects_stale_or_nonregistry_or_unbound_mapping(failure):
    p,r=candidate();service='frontend'
    if failure=='stale':r['images'][service]=json.loads(m['HISTORY'].read_text())['images'][service]
    elif failure=='tag':r['images'][service]='ghcr.io/'+p['repository']+'/frontend:latest'
    elif failure=='config_id':r['images'][service]='sha256:'+'c'*64
    elif failure=='wrong_repo':r['images'][service]='example.invalid/frontend@sha256:'+'b'*64
    elif failure=='missing':r['images'].pop('postgres')
    else:r['provenance'].pop('postgres')
    with pytest.raises(ValueError):m['validate_candidate'](p,r)


def test_ci_does_not_silently_skip_durable_job_database_tests():
    import yaml
    workflow=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    job=workflow['jobs']['infrastructure-service-ci']
    assert job['services']['postgres']['env']['POSTGRES_DB']=='cloudforge'
    checks=[step for step in job['steps'] if 'TerraformJobDurabilityClaimAndNoReplay' in step.get('run','')]
    assert len(checks)==1
    assert checks[0]['env']['CLOUDFORGE_JOB_TEST_DSN']=='${{ env.TEST_DATABASE_URL }}'
    assert '-tags integration' in checks[0]['run'] and './internal/repository' in checks[0]['run']
    assert 'AcquireExecutionLeaseAtomicMutualExclusion' in checks[0]['run']


def test_historical_policy_never_acts_as_current_release_approval(tmp_path,monkeypatch):
    p,r=candidate()
    policy=json.loads(m['HISTORY'].read_text());policy['purpose']='CURRENT_RELEASE'
    file=tmp_path/'invalid-policy.json';file.write_text(json.dumps(policy))
    monkeypatch.setitem(m['validate_candidate'].__globals__,'HISTORY',file)
    with pytest.raises(ValueError,match='deny-only'):
        m['validate_candidate'](p,r)
