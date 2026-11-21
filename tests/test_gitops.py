import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('gitops',ROOT/'scripts/prepare-gitops.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture():return {'repo_url':'https://example.invalid/platform.git','revision':'a'*40,'path':'releases/cloudforge','argocd_namespace':'argocd','operator_groups':['verified-platform-operators']}


def test_gitops_is_pinned_namespaced_and_cannot_change_approvals_or_hpa():
    project,app=m.prepare(fixture())
    assert project['spec']['clusterResourceWhitelist']==[]
    assert all(x['namespace']=='cloudforge' for x in project['spec']['destinations'])
    allowed={x['kind'] for x in project['spec']['namespaceResourceWhitelist']}
    assert not allowed & {'Secret','Role','RoleBinding','ClusterRole','Namespace','Rollout'}
    assert app['spec']['source']['targetRevision']=='a'*40
    assert app['spec']['syncPolicy']['automated']=={'prune':False,'selfHeal':True,'allowEmpty':False}
    assert app['spec']['ignoreDifferences'][0]['jsonPointers']==['/spec/replicas']
    assert 'finalizers' not in app['metadata']


@pytest.mark.parametrize('field,value',[('revision','main'),('path','../secrets'),('repo_url','https://token@example.invalid/x'),('operator_groups',[])])
def test_unverified_gitops_inputs_rejected(field,value):
    c=fixture();c[field]=value
    with pytest.raises((ValueError,TypeError)):m.prepare(c)
