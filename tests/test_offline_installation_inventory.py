"""Targeted pinned-installation/schema/placement checks. Never contacts AWS/registries."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess

import jsonschema
import pytest
import yaml

ROOT=Path(__file__).resolve().parents[1]
BUNDLE=ROOT/'deploy/controllers'
scheduler=runpy.run_path(str(ROOT/'scripts/check-two-node-scheduling.py'))


def test_cached_installation_artifacts_match_exact_inventory():
    manifest=json.loads((BUNDLE/'installation-inputs.json').read_text())
    for path,digest in manifest['source_sha256'].items():
        assert hashlib.sha256((BUNDLE/path).read_bytes()).hexdigest()==digest,path
    for name,component in manifest['components'].items():
        if 'schema' not in component:continue
        schema=json.loads((BUNDLE/component['schema']).read_text())
        config=json.loads((BUNDLE/component['configuration']).read_text())
        jsonschema.validators.validator_for(schema)(schema).validate(config)
        assert component['acceptance']=='UNVERIFIED_REQUIRES_LIVE_READBACK'


def test_chart_emits_digest_pin_and_disables_unreviewed_aws_features():
    helm=shutil.which('helm')
    if not helm:pytest.skip('helm required for local pinned-chart render')
    manifest=json.loads((BUNDLE/'installation-inputs.json').read_text())
    lbc=manifest['components']['load-balancer-controller']
    p=subprocess.run([helm,'template','cloudforge-lbc',str(BUNDLE/lbc['chart']['package']),
        '--skip-crds','--namespace','kube-system','--values',str(BUNDLE/lbc['values']),
        '--set','clusterName=offline-fixture','--set','region=eu-west-1',
        '--set','vpcId=vpc-00000000000000000'],capture_output=True,text=True,check=True)
    docs=[d for d in yaml.safe_load_all(p.stdout)if d]
    deployment=next(d for d in docs if d['kind']=='Deployment')
    c=deployment['spec']['template']['spec']['containers'][0]
    assert c['image'].endswith('@'+lbc['image']['amd64_digest'])
    gates=next(x for x in c['args']if x.startswith('--feature-gates='))
    assert 'AGAController=false' in gates and 'EnableServiceController=false' in gates
    assert all(x in c['args']for x in ['--enable-shield=false','--enable-waf=false','--enable-wafv2=false'])
    assert not any(d['kind'] in {'CustomResourceDefinition','Ingress','Gateway'}for d in docs)
    crds=list(yaml.safe_load_all((BUNDLE/lbc['crds']).read_text()))
    assert {d['metadata']['name']for d in crds}=={'ingressclassparams.elbv2.k8s.aws','targetgroupbindings.elbv2.k8s.aws'}


def test_scoped_tgb_policy_cannot_create_albs_or_activate_paid_addons():
    p=json.loads((BUNDLE/'policies/lbc-target-group.template.json').read_text())
    actions=[x for s in p['Statement']for x in s['Action']]
    assert not any(x.startswith(('shield:','waf','globalaccelerator:','iam:'))for x in actions)
    writes=[x for x in actions if ':Describe' not in x]
    assert set(writes)=={'elasticloadbalancing:RegisterTargets','elasticloadbalancing:DeregisterTargets'}
    assert p['Statement'][1]['Resource'] is None # Requires actual target group, no wildcard write scope.


def test_unbound_templates_cannot_become_a_release_or_rendered_deployment():
    release=runpy.run_path(str(ROOT/'scripts/release-images.py'))
    mapping=json.loads((ROOT/'deploy/release/immutable-images.template.json').read_text())
    with pytest.raises((ValueError,TypeError)):release['select_images']({},mapping)
    render=runpy.run_path(str(ROOT/'scripts/render-kubernetes.py'))['render']
    with pytest.raises((ValueError,TypeError)):render(json.loads((ROOT/'deploy/preview/deployment-bindings.template.json').read_text()))


def test_steady_rollout_and_live_migration_infeasibility_is_reported():
    result=scheduler['evaluate'](json.loads((ROOT/'deploy/preview/baseline-scheduling.json').read_text()))
    assert result['verdict']=='NO-GO' and not result['observed_node_allocatable']
    assert result['models']['optimistic_al2023_secondary_ip']['cold_migration_max']['feasible']
    assert not result['models']['optimistic_al2023_secondary_ip']['steady']['feasible']
    raw=result['models']['raw_hardware_upper_bound']
    assert not raw['simultaneous_rollout']['feasible']
    assert not raw['serialized_infrastructure_rollout']['feasible']
    assert not raw['migration_with_old_release_running']['feasible']


def test_placement_detects_fragmentation_even_when_aggregate_fits():
    groups=[{'name':'spread','replicas':2,'spread':True,'cpu_m':600,'memory_mi':100},
            {'name':'large-single','replicas':1,'cpu_m':500,'memory_mi':100}]
    result=scheduler['placement'](groups,{'cpu_m':1000,'memory_mi':1000,'pods':10})
    assert result['demand']['cpu_m']==1700
    assert not result['feasible']


def test_csi_sidecar_requests_match_the_scheduling_budget():
    profile=json.loads((ROOT/'deploy/preview/baseline-scheduling.json').read_text());components={g['name']:g for g in profile['system']}
    def quantity(r):return int(r['requests']['cpu'][:-1]),int(r['requests']['memory'][:-2])
    for prefix,addon,controller_sides in [('efs','aws-efs-csi-driver',['csiProvisioner','livenessProbe']),('ebs','aws-ebs-csi-driver',['attacher','provisioner','resizer','livenessProbe'])]:
        cfg=json.loads((BUNDLE/'config'/f'{addon}-configuration.json').read_text())
        for role,sides in [('controller',controller_sides),('node',['nodeDriverRegistrar','livenessProbe'])]:
            entries=[quantity(cfg[role]['resources'])]+[quantity(cfg['sidecars'][name]['resources'])for name in sides]
            assert tuple(map(sum,zip(*entries)))==(components[f'{prefix}-csi-{role}']['cpu_m'],components[f'{prefix}-csi-{role}']['memory_mi'])
