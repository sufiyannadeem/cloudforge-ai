from pathlib import Path
import hashlib
import copy
import base64
import importlib.util
import json
import os
import pytest
import re
import yaml
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_images',ROOT/'scripts/release-images.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_all_scanned_artifacts_are_bound_before_publish(tmp_path):
    sha='a'*40
    for name in m.SERVICES:
        folder=tmp_path/('image-'+name);folder.mkdir();(folder/'image.tar').write_bytes(b'fixture');(folder/'sbom.json').write_bytes(b'{}')
        (folder/'metadata.json').write_text(json.dumps({'service':name,'revision':sha,'local_image':'cloudforge-'+name+':release','image_id':'sha256:'+'b'*64,'archive_sha256':hashlib.sha256(b'fixture').hexdigest(),'sbom_sha256':hashlib.sha256(b'{}').hexdigest()}))
    assert len(m.artifacts(tmp_path,sha))==7
    (tmp_path/'image-postgres/sbom.json').write_bytes(b'{"tampered":true}')
    with pytest.raises(ValueError):m.artifacts(tmp_path,sha)
    (tmp_path/'image-postgres/sbom.json').write_bytes(b'{}')
    (tmp_path/'image-postgres/image.tar').write_bytes(b'tampered')
    with pytest.raises(ValueError):m.artifacts(tmp_path,sha)


def test_tags_local_ids_and_incomplete_releases_fail_closed():
    manifest={'revision':'a'*40,'images':{name:'example.invalid/'+name+'@sha256:'+'b'*64 for name in m.SERVICES}}
    selected=m.select_images({},manifest)
    assert len(selected['images'])==6 and '@sha256:' in selected['database_client_image']
    for bad in ['latest','postgres:16-alpine','sha256:'+'a'*64]:
        manifest['images']['postgres']=bad
        with pytest.raises(ValueError):m.select_images({},manifest)


def test_local_publish_rejected_before_any_commands(tmp_path,monkeypatch):
    monkeypatch.delenv('GITHUB_ACTIONS',raising=False)
    with pytest.raises(ValueError,match='protected manual'):m.publish(tmp_path,'a'*40,tmp_path/'images.json')


def test_workflow_scan_publish_approval_and_exact_image_handoff():
    data=yaml.safe_load((ROOT/'.github/workflows/release-images.yml').read_text())
    build=data['jobs']['build-scan'];publish=data['jobs']['publish']
    assert len(build['strategy']['matrix']['include'])==7
    assert publish['needs']=='build-scan' and publish['environment']=='release'
    assert "refs/heads/main" in publish['if']
    triggers=data.get('on',data.get(True))
    assert set(triggers)=={'workflow_dispatch'}
    assert triggers['workflow_dispatch']['inputs']['publish']['default'] is False
    assert build.get('permissions',data['permissions'])=={'contents':'read'}
    assert publish['permissions']=={'contents':'read','actions':'read','packages':'write','id-token':'write'}
    installer=next(step for step in publish['steps'] if 'cosign-installer@' in step.get('uses',''))
    assert installer['uses']=='sigstore/cosign-installer@756fe2d284c7292c4e9b62c8a28f1e5629c59532'
    assert installer['with']['cosign-release']=='v3.1.4'
    source=(ROOT/'.github/workflows/release-images.yml').read_text()
    assert 'ignore-unfixed: false' in source and 'docker save' in source
    assert 'push: false' in source and 'Publish without rebuilding' in source
    assert source.index('verify_release_environment') < source.index('docker login')


def test_solo_release_environment_requires_branch_restriction_without_reviewers():
    environment={'name':'release','deployment_branch_policy':{'protected_branches':True,'custom_branch_policies':False},
                 'protection_rules':[{'type':'branch_policy'}]}
    m.verify_release_environment(environment)
    empty_rules=copy.deepcopy(environment);empty_rules['protection_rules']=[]
    m.verify_release_environment(empty_rules)
    empty_reviewers=copy.deepcopy(environment);empty_reviewers['protection_rules'].append({'type':'required_reviewers','reviewers':[]})
    m.verify_release_environment(empty_reviewers)
    for field,value in [('name','other'),('deployment_branch_policy',None)]:
        bad=copy.deepcopy(environment);bad[field]=value
        with pytest.raises(ValueError):m.verify_release_environment(bad)
    bad=copy.deepcopy(environment);bad['deployment_branch_policy']={'protected_branches':False,'custom_branch_policies':True}
    with pytest.raises(ValueError):m.verify_release_environment(bad)
    bad=copy.deepcopy(environment);bad['protection_rules'].append({'type':'required_reviewers','prevent_self_review':True,'reviewers':[{'type':'User','reviewer':{'id':123}}]})
    with pytest.raises(ValueError,match='must not require reviewers'):m.verify_release_environment(bad)
    policy=json.loads((ROOT/'deploy/github/release-environment.example.json').read_text())
    assert policy['reviewers']==[] and policy['prevent_self_review'] is False
    assert policy['deployment_branch_policy']==environment['deployment_branch_policy']


def release_fixture():
    evidence={'image_id':'sha256:'+'b'*64,'archive_sha256':'c'*64,'sbom_sha256':'d'*64}
    return {'revision':'a'*40,'run_id':'42','run_attempt':'1',
            'images':{name:f'ghcr.io/trusted/platform/{name}@sha256:'+'e'*64 for name in m.SERVICES},
            'provenance':{name:dict(evidence) for name in m.SERVICES}}


def envelope(manifest, service):
    statement={'_type':'https://in-toto.io/Statement/v1','predicateType':m.PREDICATE,
               'subject':[{'name':manifest['images'][service].split('@')[0],'digest':{'sha256':'e'*64}}],
               'predicate':m.provenance({'service':service,**manifest['provenance'][service]},'trusted/platform','a'*40,'42','1')}
    return statement


def encoded(statement):
    return json.dumps({'payload':base64.b64encode(json.dumps(statement).encode()).decode()})


def test_exact_signed_claims_and_json_stream_verify(monkeypatch):
    manifest=release_fixture();calls=[]
    def command(*args):
        calls.append(args)
        service=args[-1].split('@')[0].split('/')[-1]
        return encoded(envelope(manifest,service))+'\n'+encoded(envelope(manifest,service)) if args[1]=='verify-attestation' else '[]'
    monkeypatch.setattr(m,'run',command)
    m.verify_manifest(manifest,'trusted/platform','a'*40,'42','1')
    assert len(calls)==14
    for args in calls:
        assert args[args.index('--certificate-identity')+1]==m.workflow_identity('trusted/platform')
        assert args[args.index('--certificate-oidc-issuer')+1]==m.ISSUER
        assert args[args.index('--certificate-github-workflow-sha')+1]=='a'*40
        assert args[args.index('--certificate-github-workflow-ref')+1]=='refs/heads/main'
        assert args[args.index('--certificate-github-workflow-trigger')+1]=='workflow_dispatch'
        assert not any('insecure' in arg or 'regexp' in arg for arg in args)


@pytest.mark.parametrize('field', ['digest','revision','run','attempt','sbom','archive','predicate','subject','service','image_id'])
def test_wrong_signed_provenance_rejected(monkeypatch,field):
    manifest=release_fixture()
    def command(*args):
        if args[1]=='verify':return '[]'
        service=args[-1].split('@')[0].split('/')[-1];statement=envelope(manifest,service)
        if field=='digest':statement['subject'][0]['digest']['sha256']='f'*64
        elif field=='revision':statement['predicate']['source']['revision']='f'*40
        elif field=='run':statement['predicate']['workflow']['run_id']='43'
        elif field=='attempt':statement['predicate']['workflow']['run_attempt']='2'
        elif field in ['sbom','archive']:statement['predicate']['artifact'][field+'_sha256']='f'*64
        elif field=='image_id':statement['predicate']['artifact']['image_id']='sha256:'+'f'*64
        elif field=='service':statement['predicate']['service']='other'
        elif field=='predicate':statement['predicateType']='https://untrusted.invalid/type'
        else:statement['subject'][0]['name']='ghcr.io/other/platform/'+service
        return encoded(statement)
    monkeypatch.setattr(m,'run',command)
    with pytest.raises(ValueError):m.verify_manifest(manifest,'trusted/platform','a'*40,'42','1')


def test_invalid_signature_and_untrusted_manifest_cannot_be_selected(monkeypatch):
    manifest=release_fixture()
    def reject(*args):raise m.subprocess.CalledProcessError(1,args)
    monkeypatch.setattr(m,'run',reject)
    with pytest.raises(m.subprocess.CalledProcessError):m.verify_manifest(manifest,'trusted/platform','a'*40,'42','1')
    for expected in [('other/repository','a'*40,'42','1'),('trusted/platform','b'*40,'42','1'),('trusted/platform','a'*40,'43','1')]:
        with pytest.raises(ValueError):m.verify_manifest(manifest,*expected)


def test_solo_main_requires_pr_exact_checks_without_review_lockout_or_bypass():
    policy=json.loads((ROOT/'deploy/github/main-ruleset.json').read_text())
    rules={rule['type']:rule.get('parameters',{}) for rule in policy['rules']}
    assert policy['bypass_actors']==[] and policy['enforcement']=='active'
    assert policy['conditions']['ref_name']=={'include':['~DEFAULT_BRANCH'],'exclude':[]}
    assert {'deletion','non_fast_forward','pull_request','required_status_checks'}==set(rules)
    reviews=rules['pull_request']
    assert reviews['required_approving_review_count']==0
    assert reviews['require_last_push_approval'] is False and reviews['require_code_owner_review'] is False
    assert reviews['dismiss_stale_reviews_on_push'] and reviews['required_review_thread_resolution']
    checks=rules['required_status_checks']
    assert checks['strict_required_status_checks_policy'] and checks['do_not_enforce_on_create'] is False
    assert checks['required_status_checks']==[{'context':'Security Gate','integration_id':15368},{'context':'All CI Checks Passed','integration_id':15368}]
    ci=yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    security=yaml.safe_load((ROOT/'.github/workflows/security.yml').read_text())
    assert {ci['jobs']['ci-gate']['name'],security['jobs']['security-summary']['name']}=={'All CI Checks Passed','Security Gate'}


def test_actions_are_pinned_and_privileges_remain_limited_to_release_publish():
    for filename in ['ci.yml','security.yml','sonarqube.yml','release-images.yml']:
        workflow=yaml.safe_load((ROOT/'.github/workflows'/filename).read_text())
        assert workflow['permissions']=={'contents':'read'}
        for name,job in workflow['jobs'].items():
            assert not job.get('continue-on-error',False)
            permissions=job.get('permissions',workflow['permissions'])
            if filename=='release-images.yml' and name=='publish':
                assert permissions=={'contents':'read','actions':'read','packages':'write','id-token':'write'}
            else:
                assert permissions=={'contents':'read'}
            for step in job['steps']:
                if 'uses' in step:
                    assert re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}',step['uses']),step['uses']
                    if step['uses'].startswith('actions/checkout@'):
                        assert step['with']['persist-credentials'] is False


def test_release_scan_failures_cannot_be_ignored():
    workflow=yaml.safe_load((ROOT/'.github/workflows/release-images.yml').read_text())
    build=workflow['jobs']['build-scan']
    scans=[step for step in build['steps'] if step.get('uses','').startswith('aquasecurity/trivy-action@') and step.get('with',{}).get('scanners')]
    assert len(scans)==1
    scan=scans[0]
    assert scan['with']['exit-code']=='1' and scan['with']['ignore-unfixed'] is False
    assert not scan.get('continue-on-error',False)
    assert workflow['jobs']['publish']['needs']=='build-scan'


@pytest.mark.parametrize('filename,gate_name',[('ci.yml','ci-gate'),('security.yml','security-summary')])
@pytest.mark.parametrize('status',['success','failure','cancelled','skipped','missing'])
def test_required_pr_checks_execute_real_gate_and_fail_closed(filename,gate_name,status):
    workflow=yaml.safe_load((ROOT/'.github/workflows'/filename).read_text())
    gate=workflow['jobs'][gate_name]
    assert gate['if']=='always()'
    results={name:{'result':'success'} for name in gate['needs']}
    first=gate['needs'][0]
    if status=='missing':del results[first]
    else:results[first]['result']=status
    step=next(step for step in gate['steps'] if 'run' in step)
    response=m.subprocess.run(['bash','-e','-o','pipefail','-c',step['run']],cwd=ROOT,
        env=dict(os.environ,EVENT_NAME='pull_request',COMMIT_MSG='PR [skip ci]',RESULTS=json.dumps(results)),
        capture_output=True,text=True,timeout=10)
    assert (response.returncode==0)==(status=='success'),response.stdout+response.stderr


def test_failed_signing_never_emits_release_manifest(tmp_path,monkeypatch):
    meta={'service':'postgres','image_id':'sha256:'+'b'*64,'archive_sha256':'c'*64,'sbom_sha256':'d'*64,'local_image':'cloudforge-postgres:release'}
    monkeypatch.setattr(m,'artifacts',lambda *_:[(tmp_path/'image.tar',meta)])
    for key,value in {'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REF':'refs/heads/main',
                      'RELEASE_PUBLISH_APPROVED':'true','GITHUB_REPOSITORY':'trusted/platform','GITHUB_RUN_ID':'42','GITHUB_RUN_ATTEMPT':'1'}.items():
        monkeypatch.setenv(key,value)
    commands=[]
    def docker(args,**kwargs):
        commands.append(args)
        if '{{.Id}}' in args:return meta['image_id']
        if '{{json .RepoDigests}}' in args:return json.dumps(['ghcr.io/trusted/platform/postgres@sha256:'+'e'*64])
        return ''
    monkeypatch.setattr(m.subprocess,'check_output',docker)
    def reject(*args):raise m.subprocess.CalledProcessError(1,args)
    monkeypatch.setattr(m,'run',reject)
    with pytest.raises(m.subprocess.CalledProcessError):m.publish(tmp_path,'a'*40,tmp_path/'images.json')
    assert not (tmp_path/'images.json').exists()
    assert next(args for args in commands if args[1]=='tag')[-1].endswith(':candidate-'+'a'*40+'-42-1')


def test_cli_selection_requires_trusted_release_coordinates(tmp_path):
    result=m.subprocess.run(['python3',str(ROOT/'scripts/release-images.py'),'--config','unused','--manifest','unused','--output',str(tmp_path/'out.json')],capture_output=True)
    assert result.returncode!=0 and b'Trusted --repository' in result.stderr
    assert not (tmp_path/'out.json').exists()
