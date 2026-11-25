"""Gate mechanics only; these checks never stand in for native/DB evidence."""
import runpy
from pathlib import Path
import yaml

ROOT=Path(__file__).resolve().parents[1]


def test_missing_isolated_database_inputs_block_without_connecting(monkeypatch):
    for key in ('AI_TEST_POSTGRES_DSN','REMEDIATION_TEST_DATABASE_URL','RELEASE_TEST_POSTGRES_DSN'):
        monkeypatch.delenv(key,raising=False)
    gate=runpy.run_path(str(ROOT/'scripts/verify-consolidated-release.py'))
    result=gate['postgres']()
    assert result[0]['status']=='BLOCKED'
    assert 'AI_TEST_POSTGRES_DSN' in result[0]['reason']


def test_ci_is_manual_requires_all_real_gates_and_read_only_permissions():
    workflow=yaml.load((ROOT/'.github/workflows/consolidated-release-verification.yml').read_text(),Loader=yaml.BaseLoader)
    assert set(workflow['on'])=={'workflow_dispatch'}
    assert workflow['permissions']=={'contents':'read'}
    jobs=workflow['jobs']
    assert set(jobs['integration-verification']['needs'])=={'plan','native','postgres-hosted','postgres-dedicated'}
    assert jobs['postgres-hosted']['services']['postgres']['image']=='${{ needs.plan.outputs.postgres_image }}'
    assert 'services' not in jobs['postgres-dedicated']
    assert jobs['postgres-hosted']['env']['CI_EPHEMERAL_POSTGRES']=='synthetic-service-only'
    semantic=yaml.load((ROOT/'.github/workflows/semantic-release-verification.yml').read_text(),Loader=yaml.BaseLoader)
    assert set(semantic['on'])=={'workflow_dispatch'} and semantic['permissions']=={'contents':'read'}
    assert semantic['jobs']['semantic-verification']['environment']=='semantic-verification'
    assert 'secrets' not in (ROOT/'.github/workflows/semantic-release-verification.yml').read_text()


def test_semantic_packaging_has_no_unpinned_base_or_network_install():
    text=(ROOT/'services/aiops-service/Dockerfile.rag').read_text()
    assert 'ARG AIOPS_GLIBC_BASE\nFROM ${AIOPS_GLIBC_BASE}' in text
    assert '--require-hashes' in text and '--no-index' in text
    assert 'USER 10001:10001' in text
    worker=(ROOT/'services/aiops-service/Dockerfile.inference').read_text()
    assert 'sentence_embeddings' not in worker and 'COPY knowledge' not in worker


def test_hosted_acquisition_has_no_fabricated_review_and_no_local_download_fallback():
    import json
    template=json.loads((ROOT/'ci/integration-acquisition.template.json').read_text())
    assert template['status']=='UNBOUND_REQUIRES_REVIEW'
    assert template['postgres_image'] is None
    assert all(item['sha256'] is None for item in template['artifacts'].values())
    source=(ROOT/'scripts/ci/acquire-integration-inputs.py').read_text()
    assert "os.getenv('RUNNER_ENVIRONMENT')!='github-hosted'" in source
    assert "os.environ['CI_ACQUISITION_LOCK_SHA256']" in source
    bootstrap=(ROOT/'scripts/ci/bootstrap-integration-postgres.py').read_text()
    assert 'preexist' in bootstrap and 'NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE' in bootstrap
    assert 'cloudforge_inference_test' in bootstrap and 'cloudforge_remediation_test' in bootstrap and 'cloudforge_release_test' in bootstrap


def test_verified_inputs_remain_pending_human_approval(monkeypatch):
    import hashlib,json,pytest
    path=ROOT/'ci/integration-acquisition.json';lock=json.loads(path.read_bytes())
    assert lock['status']=='VERIFIED_INPUTS_PENDING_HUMAN_APPROVAL' and lock['reviewed_by'] is None
    module=runpy.run_path(str(ROOT/'scripts/ci/acquire-integration-inputs.py'))
    monkeypatch.setenv('CI_ACQUISITION_LOCK_SHA256',hashlib.sha256(path.read_bytes()).hexdigest())
    monkeypatch.delenv('CI_ACQUISITION_APPROVED',raising=False)
    with pytest.raises(ValueError,match='approval'):module['load'](path)
    # Unit-only injected approval verifies mechanics; it is not a human review or workflow run.
    monkeypatch.setenv('CI_ACQUISITION_APPROVED','true')
    assert module['load'](path,semantic=True)==lock


def test_schema_derivation_is_strict_reproducible_and_reference_closed(tmp_path):
    import hashlib,json,pytest,jsonschema
    module=runpy.run_path(str(ROOT/'scripts/ci/acquire-integration-inputs.py'))
    original={'type':'object','properties':{'properties':{'type':'string'},'nullable':{'type':'boolean'},'$ref':{'type':'string'}}}
    result=module['strict_schema'](original)
    assert set(result['properties'])=={'properties','nullable','$ref'} and result['additionalProperties'] is False
    with pytest.raises(ValueError,match='External'):module['standalone']({'$ref':'https://example.invalid/schema'}, {})
    # Small synthetic fixture for derivation mechanics, never used as a production schema.
    meta='io.k8s.apimachinery.pkg.apis.meta.v1.ObjectMeta'
    document={'definitions':{meta:{'type':'object','properties':{'name':{'type':'string'}}},
       'Fixture':{'type':'object','properties':{'metadata':{'$ref':'#/definitions/'+meta}},
                  'x-kubernetes-group-version-kind':[{'kind':'Fixture','group':'','version':'v1'}]}}}
    raw=json.dumps(document).encode();source={'name':'fixture','kind':'openapi','sha256':hashlib.sha256(raw).hexdigest()}
    lock={'schemas':{'sources':[source],'kubernetes_version':'1.35.0','rollouts_version':'1.10.2','csi_version':'1.6.2'}}
    first=tmp_path/'first';second=tmp_path/'second'
    module['build_schemas'](lock,first,source_bytes={'fixture':raw})
    module['build_schemas'](lock,second,source_bytes={'fixture':raw})
    assert (first/'bundle.json').read_bytes()==(second/'bundle.json').read_bytes()
    schema=json.loads((first/'fixture-v1-v1.json').read_bytes())
    jsonschema.Draft7Validator.check_schema(schema)
    jsonschema.validate({'apiVersion':'v1','kind':'Fixture','metadata':{'name':'synthetic'}},schema)
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate({'apiVersion':'v1','kind':'Fixture','invented':1},schema)


def test_archive_formats_and_link_traversal_rejection(tmp_path):
    import io,tarfile,zipfile,pytest
    module=runpy.run_path(str(ROOT/'scripts/ci/acquire-integration-inputs.py'))
    tar=tmp_path/'go.tar.gz'
    with tarfile.open(tar,'w:gz') as output:
        item=tarfile.TarInfo('go/bin/go');item.size=4;output.addfile(item,io.BytesIO(b'test'))
    module['unpack'](tar,tmp_path/'go','tar.gz')
    assert (tmp_path/'go/go/bin/go').read_bytes()==b'test'
    archive=tmp_path/'terraform.zip'
    with zipfile.ZipFile(archive,'w') as output:output.writestr('terraform',b'test')
    module['unpack'](archive,tmp_path/'tf','zip')
    assert (tmp_path/'tf/terraform').read_bytes()==b'test'
    module['unpack'](tmp_path/'tf/terraform',tmp_path/'kubectl','binary')
    assert (tmp_path/'kubectl/kubectl').read_bytes()==b'test'
    for name,link in (('../escape',False),('link',True)):
        bad=tmp_path/'bad.tar.gz'
        with tarfile.open(bad,'w:gz') as output:
            item=tarfile.TarInfo(name)
            if link:item.type=tarfile.SYMTYPE;item.linkname='../../escape'
            output.addfile(item)
        with pytest.raises(ValueError):module['unpack'](bad,tmp_path/('bad-link' if link else 'bad-path'),'tar.gz')


def test_same_sha_evidence_rejects_stale_or_wrong_jobs(monkeypatch):
    import io,json,pytest,urllib.request
    module=runpy.run_path(str(ROOT/'scripts/ci/require-same-sha.py'))
    monkeypatch.setenv('GITHUB_REPOSITORY','owner/repo');monkeypatch.setenv('GITHUB_SHA','a'*40);monkeypatch.setenv('GITHUB_TOKEN','synthetic-test-only')
    run={'head_sha':'a'*40,'head_repository':{'full_name':'owner/repo'},'event':'workflow_dispatch',
         'path':'.github/workflows/consolidated-release-verification.yml','conclusion':'success','status':'completed','run_attempt':1}
    jobs={'jobs':[{'name':'integration-verification','conclusion':'success'}]}
    class Opener:
        def open(self,request,timeout):
            assert request.full_url.startswith('https://api.github.com/repos/owner/repo/')
            return io.BytesIO(json.dumps(jobs if '/jobs?' in request.full_url else run).encode())
    monkeypatch.setattr(urllib.request,'build_opener',lambda *args:Opener())
    module['require']('123','1',run['path'],'integration-verification')
    run['head_sha']='b'*40
    with pytest.raises(ValueError,match='same-SHA'):module['require']('123','1',run['path'],'integration-verification')
    run['head_sha']='a'*40;jobs['jobs'][0]['conclusion']='skipped'
    with pytest.raises(ValueError,match='gate'):module['require']('123','1',run['path'],'integration-verification')


def test_preparation_cannot_satisfy_semantic_release_status():
    semantic=yaml.load((ROOT/'.github/workflows/semantic-release-verification.yml').read_text(),Loader=yaml.BaseLoader)
    gate=semantic['jobs']['semantic-gate']
    assert 'candidate-preparation-only' in gate['name'] and "inputs.operation == 'verify'" in gate['name']
    assert 'semantic-preparation' in gate['needs']
    assert semantic['jobs']['semantic-preparation']['environment']=='semantic-preparation'
    for name in ('semantic-preparation','semantic-verification'):
        job=semantic['jobs'][name]
        assert job['permissions']=={'contents':'read','actions':'read'}
        assert any('require-same-sha.py --kind integration' in step.get('run','') for step in job['steps'])
    selected=next(step for step in semantic['jobs']['semantic-verification']['steps'] if step.get('name','').startswith('Select independently'))
    assert selected['env']['SEMANTIC_CANDIDATE_SHA256']=='${{ vars.SEMANTIC_CANDIDATE_SHA256 }}'
