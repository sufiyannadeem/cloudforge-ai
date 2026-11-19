"""Offline deployment rendering: fixtures are synthetic, never deployment inputs."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('render_kubernetes', ROOT / 'scripts/render-kubernetes.py')
renderer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(renderer)


@pytest.fixture
def config():
    c = json.loads((ROOT / 'deploy/kubernetes/deployment-inputs.example.json').read_text())
    c.update(account_id='123456789012', region='eu-west-1',
             state_bucket='fixture-private-state',
             provisioner_role_arn='arn:aws:iam::123456789012:role/fixture-provisioner',
             monitoring_namespace='monitoring', ingress_namespace='ingress', ingress_app='gateway')
    c['database_ca_configmap'] = 'fixture-db-ca'
    c['storage'] = {'class': 'fixture-rwx', 'size': '10Gi'}
    c['images'] = {name: 'example.invalid/' + name + '@sha256:' + 'a' * 64 for name in c['images']}
    c['roles'] = {name: 'arn:aws:iam::123456789012:role/fixture-' + name for name in c['roles']}
    c['egress_cidrs'] = {'database': ['192.0.2.1/32'], 'kubernetes_api': ['192.0.2.2/32'], 'aws_https': ['192.0.2.3/32']}
    for name, entry in c['secrets'].items():
        entry['arn'] = 'arn:aws:secretsmanager:eu-west-1:123456789012:secret:fixture-' + name + '-Abcdef'
    return c


def test_all_services_probes_and_secret_references_resolve(config):
    docs = renderer.render(config)
    by_kind = lambda kind: {d['metadata']['name']: d for d in docs if d['kind'] == kind}
    services, secrets = by_kind('Service'), by_kind('ExternalSecret')
    assert len(services) == 6
    assert not by_kind('Secret')
    for name, dep in by_kind('Deployment').items():
        pod = dep['spec']['template']['spec']
        container = pod['containers'][0]
        assert services[name]['spec']['selector'] == dep['spec']['selector']['matchLabels']
        assert services[name]['spec']['type'] == 'ClusterIP'
        for probe in ['startupProbe', 'readinessProbe', 'livenessProbe']:
            assert container[probe].get('httpGet', container[probe].get('tcpSocket'))['port'] == renderer.PORTS[name]
        assert '@sha256:' in container['image']
        assert container['securityContext']['allowPrivilegeEscalation'] is False
        assert pod['automountServiceAccountToken'] == (name == 'deployment-service')
        for env in container.get('env', []):
            ref = env.get('valueFrom', {}).get('secretKeyRef')
            if ref:
                assert ref['key'] in {entry['secretKey'] for entry in secrets[ref['name']]['spec']['data']}
        for source in container.get('envFrom', []):
            assert source['secretRef']['name'] in secrets
    infra_env = by_kind('Deployment')['infrastructure-service']['spec']['template']['spec']['containers'][0]['env']
    assert {'name': 'TERRAFORM_READ_ONLY', 'value': 'true'} in infra_env
    store = by_kind('SecretStore')['cloudforge']['spec']['provider']['aws']
    assert store['auth'] == {'jwt': {'serviceAccountRef': {'name': 'cloudforge-secret-sync'}}}
    assert all(d['apiVersion'] == 'external-secrets.io/v1' for d in secrets.values())
    for secret in secrets.values():
        assert secret['spec']['target']['deletionPolicy'] == 'Retain'
        assert 'dataFrom' not in secret['spec']
    pvc = by_kind('PersistentVolumeClaim')['cloudforge-terraform-workspaces']['spec']
    assert pvc['accessModes'] == ['ReadWriteMany']
    assert pvc['storageClassName'] == config['storage']['class']


@pytest.mark.parametrize('field,value', [
    ('image', 'example.invalid/frontend:prod'),
    ('image', 'example.invalid/frontend@sha256:short'),
    ('role', 'arn:aws:iam::999999999999:role/foreign'),
    ('secret', 'arn:aws:secretsmanager:us-east-1:123456789012:secret:wrong'),
    ('secret', 'arn:aws:secretsmanager:eu-west-1:123456789012:secret:*'),
    ('storage', None), ('egress', ['0.0.0.0/0']), ('egress', []),
])
def test_invalid_external_inputs_fail_closed(config, field, value):
    if field == 'image': config['images']['frontend'] = value
    if field == 'role': config['roles']['infrastructure-service'] = value
    if field == 'secret': config['secrets']['cloudforge-frontend-project']['arn'] = value
    if field == 'storage': config['storage']['class'] = value
    if field == 'egress': config['egress_cidrs']['aws_https'] = value
    with pytest.raises(ValueError): renderer.render(config)


def test_networks_do_not_grant_developers_direct_backend_access(config):
    docs = renderer.render(config)
    policies = {d['metadata']['name']: d['spec'] for d in docs if d['kind'] == 'NetworkPolicy'}
    assert policies['default-deny'] == {'podSelector': {}, 'policyTypes': ['Ingress', 'Egress'], 'ingress': [], 'egress': []}
    assert policies['infrastructure-service-ingress']['ingress'][0]['from'] == [renderer.peer('frontend')]
    assert policies['frontend-ingress']['ingress'][0]['from'] == [renderer.peer('gateway', 'ingress')]
    assert not any('ipBlock' in peer for rule in policies['frontend-egress']['egress'] for peer in rule['to'])
    api_rules = policies['deployment-service-egress']['egress']
    assert {'to': [{'ipBlock': {'cidr': '192.0.2.2/32'}}], 'ports': [renderer.tcp(443)]} in api_rules
    assert not any(rule.get('ports') == [renderer.tcp(443)] for rule in policies['frontend-egress']['egress'])


def test_secret_mapping_is_exact_and_no_raw_values_can_be_rendered(config):
    bad = copy.deepcopy(config)
    bad['secrets']['cloudforge-project-db']['properties']['EXTRA_ADMIN_PASSWORD'] = 'password'
    with pytest.raises(ValueError): renderer.render(bad)
    bad = copy.deepcopy(config)
    del bad['secrets']['cloudforge-finops-audit-db']
    with pytest.raises(ValueError): renderer.render(bad)


def test_unconfigured_template_produces_no_partial_manifest():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/render-kubernetes.py'), '--config',
                             str(ROOT / 'deploy/kubernetes/deployment-inputs.example.json')], capture_output=True, text=True)
    assert result.returncode == 2
    assert result.stdout == ''
    assert 'invalid' in result.stderr


def test_bedrock_requires_explicit_identity_and_model(config):
    config['ai'] = {'provider': 'bedrock', 'model': 'fixture.model'}
    with pytest.raises(KeyError): renderer.render(config)
    config['roles']['aiops-service'] = 'arn:aws:iam::123456789012:role/fixture-aiops'
    docs = renderer.render(config)
    aiops = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'aiops-service')
    env = aiops['spec']['template']['spec']['containers'][0]['env']
    assert {'name': 'AI_PROVIDER', 'value': 'bedrock'} in env
    assert {'name': 'AI_MODEL', 'value': 'fixture.model'} in env


def test_roles_cannot_share_privileges(config):
    config['roles']['secret-sync'] = config['roles']['infrastructure-service']
    with pytest.raises(ValueError): renderer.render(config)


def test_finops_keeps_bounded_monitoring_access(config):
    docs = renderer.render(config)
    policy = next(d for d in docs if d['kind'] == 'NetworkPolicy' and d['metadata']['name'] == 'finops-service-egress')
    assert {'to': [renderer.peer('prometheus', 'monitoring')], 'ports': [renderer.tcp(9090)]} in policy['spec']['egress']


def test_progressive_delivery_is_an_explicit_configured_opt_in(config):
    config['rollouts'] = {'enabled': True, 'analysis_template': 'cloudforge-release-health'}
    docs = renderer.render(config)
    worker = next(d for d in docs if d['kind'] == 'Deployment' and d['metadata']['name'] == 'deployment-service')
    env = worker['spec']['template']['spec']['containers'][0]['env']
    assert {'name': 'ARGO_ROLLOUTS_ENABLED', 'value': 'true'} in env
    assert {'name': 'ARGO_ANALYSIS_TEMPLATE', 'value': 'cloudforge-release-health'} in env
    config['rollouts']['analysis_template'] = None
    with pytest.raises(ValueError): renderer.render(config)


def test_hpa_disruption_topology_and_shutdown_are_coherent(config):
    docs = renderer.render(config)
    by_kind = lambda kind: {d['metadata']['name']: d for d in docs if d['kind'] == kind}
    deployments, hpas, budgets = by_kind('Deployment'), by_kind('HorizontalPodAutoscaler'), by_kind('PodDisruptionBudget')
    assert len(deployments) == len(hpas) == len(budgets) == 6
    for name, deployment in deployments.items():
        pod = deployment['spec']['template']['spec']
        container = pod['containers'][0]
        assert 'replicas' not in deployment['spec']  # No conflict with an existing HPA's scale.
        hpa = hpas[name]['spec']
        assert hpa['scaleTargetRef'] == {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'name': name}
        assert 2 == hpa['minReplicas'] <= hpa['maxReplicas'] == 4
        assert hpa['metrics'][0]['resource']['target']['averageUtilization'] == 70
        assert hpa['behavior']['scaleDown']['stabilizationWindowSeconds'] >= 300
        assert budgets[name]['spec']['selector'] == deployment['spec']['selector']
        assert deployment['spec']['strategy']['rollingUpdate']['maxUnavailable'] == 0
        assert {rule['topologyKey'] for rule in pod['topologySpreadConstraints']} == {'kubernetes.io/hostname', 'topology.kubernetes.io/zone'}
        for rule in pod['topologySpreadConstraints']:
            assert rule['minDomains'] == 2 and rule['maxSkew'] == 1 and rule['whenUnsatisfiable'] == 'DoNotSchedule'
            assert rule['labelSelector'] == deployment['spec']['selector']
        assert container['lifecycle']['preStop']['exec']['command'] == ['/bin/sh', '-c', 'sleep 5']
        assert container['resources']['requests']['cpu'] and container['resources']['limits']['memory']
        assert container['resources']['limits']['ephemeral-storage'] == '4Gi'
        if name != 'frontend':
            assert container['readinessProbe']['httpGet']['path'] == '/ready'
    infrastructure = deployments['infrastructure-service']['spec']['template']
    assert infrastructure['metadata']['annotations']['cluster-autoscaler.kubernetes.io/safe-to-evict'] == 'false'
    assert budgets['infrastructure-service']['spec']['maxUnavailable'] == 0
    assert hpas['infrastructure-service']['spec']['behavior']['scaleDown']['selectPolicy'] == 'Disabled'
    assert infrastructure['spec']['terminationGracePeriodSeconds'] == 120


@pytest.mark.parametrize('profile', [
    {'min_replicas': 1}, {'min_replicas': 5, 'max_replicas': 4},
    {'max_replicas': 100}, {'cpu_utilization': 0}, {'min_replicas': True},
])
def test_invalid_scaling_profiles_do_not_render(config, profile):
    config['reliability'] = profile
    with pytest.raises(ValueError): renderer.render(config)


def test_database_principals_are_not_shared_in_rendered_workloads(config):
    docs = renderer.render(config)
    db_refs = []
    for item in docs:
        if item['kind'] != 'Deployment': continue
        name = item['metadata']['name']
        pod = item['spec']['template']['spec']
        if name != 'frontend':
            assert any(v.get('configMap', {}).get('name') == 'fixture-db-ca' for v in pod['volumes'])
        if name in ['project-service','infrastructure-service','deployment-service','aiops-service']:
            db_refs.extend(x['secretRef']['name'] for x in pod['containers'][0]['envFrom'])
    assert set(db_refs) == {'cloudforge-'+s+'-db' for s in ['project','infrastructure','deployment','aiops']}


def test_migrations_are_ordered_isolated_hooks_with_no_runtime_credentials(config):
    docs=renderer.render(config)
    jobs=[d for d in docs if d['kind']=='Job']
    assert len(jobs)==5
    assert [d['metadata']['annotations']['argocd.argoproj.io/sync-wave'] for d in jobs]==['-5','-4','-3','-2','-1']
    for job in jobs:
        pod=job['spec']['template']['spec']; c=pod['containers'][0]
        assert pod['automountServiceAccountToken'] is False
        assert 'app' not in job['spec']['template']['metadata']['labels']
        assert c['envFrom']==[{'secretRef':{'name':'cloudforge-migration-db'}}]
        assert job['spec']['activeDeadlineSeconds']==300
    for doc in docs:
        if doc['kind']=='Deployment':
            assert 'cloudforge-migration-db' not in str(doc)
        if doc['kind']=='NetworkPolicy':
            assert doc['metadata']['annotations']['argocd.argoproj.io/sync-wave']=='-10'


def test_scheduled_drift_has_no_provisioner_or_human_signing_key(config):
    config['drift']={'enabled':True};config['roles']['drift']='arn:aws:iam::123456789012:role/fixture-drift-reader'
    config['secrets']['cloudforge-drift-db']={'arn':'arn:aws:secretsmanager:eu-west-1:123456789012:secret:fixture-drift-db-Abcdef','properties':{'DATABASE_URL':'DATABASE_URL'}}
    docs=renderer.render(config)
    job=next(d for d in docs if d['kind']=='CronJob')
    assert job['spec']['concurrencyPolicy']=='Forbid'
    pod=job['spec']['jobTemplate']['spec']['template']['spec'];c=pod['containers'][0]
    assert pod['serviceAccountName']=='cloudforge-drift' and pod['automountServiceAccountToken'] is False
    assert c['args']==['drift-scan']
    assert not any(e['name'] in ['TERRAFORM_PROVISIONER_ROLE_ARN','CLOUDFORGE_FRONTEND_KEY'] for e in c['env'])
    assert c['envFrom']==[{'secretRef':{'name':'cloudforge-drift-db'}}]
    assert job['spec']['jobTemplate']['spec']['activeDeadlineSeconds']==120
