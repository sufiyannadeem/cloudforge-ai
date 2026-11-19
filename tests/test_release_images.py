from pathlib import Path
import hashlib
import copy
import importlib.util
import json
import pytest
import yaml
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('release_images',ROOT/'scripts/release-images.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_all_scanned_artifacts_are_bound_before_publish(tmp_path):
    sha='a'*40
    for name in m.SERVICES:
        folder=tmp_path/('image-'+name);folder.mkdir();(folder/'image.tar').write_bytes(b'fixture')
        (folder/'metadata.json').write_text(json.dumps({'service':name,'revision':sha,'local_image':'cloudforge-'+name+':release','image_id':'sha256:'+'b'*64,'archive_sha256':hashlib.sha256(b'fixture').hexdigest()}))
    assert len(m.artifacts(tmp_path,sha))==7
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
    assert build.get('permissions',data['permissions'])=={'contents':'read'}
    source=(ROOT/'.github/workflows/release-images.yml').read_text()
    assert 'ignore-unfixed: false' in source and 'docker save' in source
    assert 'push: false' in source and 'Publish without rebuilding' in source
    assert source.index('verify_release_environment') < source.index('docker login')


def test_release_environment_requires_independent_review_and_branch_restriction():
    environment={'name':'release','deployment_branch_policy':{'protected_branches':True,'custom_branch_policies':False},
                 'protection_rules':[{'type':'required_reviewers','prevent_self_review':True,
                                      'reviewers':[{'type':'User','reviewer':{'id':123}}]}]}
    m.verify_release_environment(environment)
    for field,value in [('name','other'),('deployment_branch_policy',None),('protection_rules',[])]:
        bad=copy.deepcopy(environment);bad[field]=value
        with pytest.raises(ValueError):m.verify_release_environment(bad)
    for field,value in [('prevent_self_review',False),('reviewers',[])]:
        bad=copy.deepcopy(environment);bad['protection_rules'][0][field]=value
        with pytest.raises(ValueError):m.verify_release_environment(bad)
    bad=copy.deepcopy(environment);bad['deployment_branch_policy']={'protected_branches':False,'custom_branch_policies':True}
    with pytest.raises(ValueError):m.verify_release_environment(bad)
