#!/usr/bin/env python3
"""Render reviewed, non-secret deployment inputs. Never applies resources."""
import argparse
import ipaddress
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
PORTS = dict(zip(('project-service', 'infrastructure-service', 'deployment-service',
                  'aiops-service', 'finops-service', 'frontend'), (8080, 8081, 8082, 8090, 8091, 3000)))


def checked(pattern, value, field):
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ValueError('Invalid or missing ' + field)
    return value


def document(kind, name, spec, api='v1'):
    return {'apiVersion': api, 'kind': kind,
            'metadata': {'name': name, 'namespace': 'cloudforge'}, 'spec': spec}


def peer(app, namespace='cloudforge'):
    return {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': namespace}},
            'podSelector': {'matchLabels': {'app': app}}}


def tcp(port):
    return {'protocol': 'TCP', 'port': port}


def render(config):
    account = checked(r'[0-9]{12}', config['account_id'], 'account_id')
    region = checked(r'[a-z]{2}-[a-z]+-[0-9]', config['region'], 'region')
    role_pattern = rf'arn:aws:iam::{account}:role/[A-Za-z0-9+=,.@_/-]+'
    roles = config['roles']
    for name in ('infrastructure-service', 'finops-service', 'secret-sync'):
        checked(role_pattern, roles[name], 'roles.' + name)
    checked(role_pattern, config['provisioner_role_arn'], 'provisioner_role_arn')
    ai = config.get('ai', {'provider': 'disabled'})
    if ai['provider'] not in {'disabled', 'bedrock'}:
        raise ValueError('Only disabled or explicitly configured Bedrock is supported')
    if ai['provider'] == 'bedrock':
        checked(role_pattern, roles['aiops-service'], 'roles.aiops-service')
        checked(r'[A-Za-z0-9.:/_-]+', ai['model'], 'ai.model')
    if set(roles) != {'infrastructure-service', 'finops-service', 'secret-sync'} | ({'aiops-service'} if ai['provider'] == 'bedrock' else set()):
        raise ValueError('Unexpected workload role')
    if len(set(roles.values()) | {config['provisioner_role_arn']}) != len(roles) + 1:
        raise ValueError('Workload, sync and provisioner roles must be distinct')
    rollouts = config.get('rollouts', {'enabled': False})
    if not isinstance(rollouts['enabled'], bool):
        raise ValueError('rollouts.enabled must be a boolean')
    if rollouts['enabled']:
        checked(r'[a-z0-9][a-z0-9-]*', rollouts['analysis_template'], 'rollouts.analysis_template')
    bucket = checked(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', config['state_bucket'], 'state_bucket')
    storage = config['storage']
    checked(r'[a-z0-9][a-z0-9.-]*', storage['class'], 'storage.class')
    checked(r'[1-9][0-9]*(Gi|Ti)', storage['size'], 'storage.size')
    monitor_ns = checked(r'[a-z0-9][a-z0-9-]*', config['monitoring_namespace'], 'monitoring_namespace')
    ingress_ns = checked(r'[a-z0-9][a-z0-9-]*', config['ingress_namespace'], 'ingress_namespace')
    ingress_app = checked(r'[a-z0-9][a-z0-9-]*', config['ingress_app'], 'ingress_app')
    networks = {}
    for key in ('database', 'kubernetes_api', 'aws_https'):
        networks[key] = []
        if not config['egress_cidrs'][key]:
            raise ValueError('Required approved egress: ' + key)
        for cidr in config['egress_cidrs'][key]:
            network = ipaddress.ip_network(cidr, strict=True)
            if network.prefixlen == 0:
                raise ValueError('Unrestricted egress is not permitted')
            networks[key].append({'ipBlock': {'cidr': str(network)}})
    docs = [d for d in yaml.safe_load_all((ROOT / 'deploy/kubernetes/cloudforge-secrets-example.yml').read_text())
            if d and d['kind'] != 'Secret']
    secret_keys = {}
    for d in docs:
        if d['kind'] == 'ServiceAccount':
            d['metadata'].pop('annotations', None)
            service = d['metadata']['name'].removeprefix('cloudforge-')
            if service in roles:
                d['metadata']['annotations'] = {'eks.amazonaws.com/role-arn': roles[service]}
            d['automountServiceAccountToken'] = service == 'deployment-service'
        if d['kind'] != 'Deployment':
            continue
        name = d['metadata']['name']
        spec = d['spec']['template']['spec']
        # IRSA admission injects its own projected token; no default API token needed.
        spec['automountServiceAccountToken'] = name == 'deployment-service'
        d['spec']['template']['metadata'].pop('annotations', None)
        container = spec['containers'][0]
        container['image'] = checked(r'[a-z0-9][a-z0-9.:/_-]*@sha256:[0-9a-f]{64}', config['images'][name], 'images.' + name)
        container['imagePullPolicy'] = 'Always'
        container['securityContext'].update({'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}})
        spec['securityContext']['seccompProfile'] = {'type': 'RuntimeDefault'}
        spec['terminationGracePeriodSeconds'] = 30
        for env in container.get('env', []):
            if env['name'] in {'AWS_REGION', 'AWS_DEFAULT_REGION'}:
                env['value'] = region
            if 'secretKeyRef' in env.get('valueFrom', {}):
                ref = env['valueFrom']['secretKeyRef']
                secret_keys.setdefault(ref['name'], set()).add(ref['key'])
        for source in container.get('envFrom', []):
            name_ref = source['secretRef']['name']
            secret_keys.setdefault(name_ref, set())
        # All service connections use their actual ClusterIP Services.
        additional = {'AWS_STS_REGIONAL_ENDPOINTS': 'regional'}
        if name in {'frontend', 'deployment-service', 'aiops-service', 'finops-service'}:
            additional['PROMETHEUS_URL'] = f'http://prometheus.{monitor_ns}.svc:9090'
        if name == 'deployment-service':
            additional['ARGO_ROLLOUTS_ENABLED'] = str(rollouts['enabled']).lower()
            if rollouts['enabled']:
                additional['ARGO_ANALYSIS_TEMPLATE'] = rollouts['analysis_template']
        if name == 'aiops-service':
            additional['DEPLOYMENT_SERVICE_URL'] = 'http://deployment-service:8082'
            additional['AI_PROVIDER'] = ai['provider']
            if ai['provider'] == 'bedrock':
                additional['AI_MODEL'] = ai['model']
        if name == 'frontend':
            additional['GRAFANA_URL'] = f'http://grafana.{monitor_ns}.svc:3000'
        container['env'] = [e for e in container.get('env', []) if e['name'] not in additional]
        container['env'] += [{'name': k, 'value': v} for k, v in additional.items()]
    # envFrom must be explicitly mapped, not unrestricted extraction of remote JSON.
    required = {'cloudforge-postgres-credentials': {'DATABASE_URL'},
                'cloudforge-frontend-credentials': {'CLOUDFORGE_SESSION_SECRET'}}
    secret_keys = {name: keys | required.get(name, set()) for name, keys in secret_keys.items()}
    sa = document('ServiceAccount', 'cloudforge-secret-sync', {})
    sa.pop('spec')
    sa['automountServiceAccountToken'] = False
    sa['metadata']['annotations'] = {'eks.amazonaws.com/role-arn': roles['secret-sync']}
    docs += [sa, document('SecretStore', 'cloudforge', {'provider': {'aws': {
        'service': 'SecretsManager', 'region': region,
        'auth': {'jwt': {'serviceAccountRef': {'name': 'cloudforge-secret-sync'}}}}}}, 'external-secrets.io/v1')]
    secret_pattern = rf'arn:aws:secretsmanager:{region}:{account}:secret:[A-Za-z0-9/_+=.@-]+'
    if set(config['secrets']) != set(secret_keys):
        raise ValueError('secrets must map exactly the referenced Kubernetes Secret names')
    for name, keys in secret_keys.items():
        entry = config['secrets'][name]
        checked(secret_pattern, entry['arn'], 'secret ARN')
        if set(entry['properties']) != keys:
            raise ValueError('Secret property mapping mismatch for ' + name)
        data = []
        for key in sorted(keys):
            prop = checked(r'[A-Za-z0-9_-]+', entry['properties'][key], 'secret property')
            data.append({'secretKey': key, 'remoteRef': {'key': entry['arn'], 'property': prop}})
        docs.append(document('ExternalSecret', name, {'refreshInterval': '1h',
            'secretStoreRef': {'name': 'cloudforge', 'kind': 'SecretStore'},
            'target': {'name': name, 'creationPolicy': 'Owner', 'deletionPolicy': 'Retain'},
            'data': data}, 'external-secrets.io/v1'))
    cm = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'cloudforge-terraform', 'namespace': 'cloudforge'},
          'data': {'TERRAFORM_STATE_BUCKET': bucket, 'TERRAFORM_STATE_REGION': region,
                   'TERRAFORM_PROVISIONER_ROLE_ARN': config['provisioner_role_arn']}}
    docs += [cm, document('PersistentVolumeClaim', 'cloudforge-terraform-workspaces', {
        'accessModes': ['ReadWriteMany'], 'storageClassName': storage['class'],
        'resources': {'requests': {'storage': storage['size']}}})]
    docs += list(yaml.safe_load_all((ROOT / 'deploy/kubernetes/services.yml').read_text()))
    def policy(name, selector, ingress=None, egress=None):
        spec = {'podSelector': selector, 'policyTypes': []}
        for direction, rules in [('Ingress', ingress), ('Egress', egress)]:
            if rules is not None:
                spec['policyTypes'].append(direction)
                spec[direction.lower()] = rules
        docs.append(document('NetworkPolicy', name, spec, 'networking.k8s.io/v1'))
    policy('default-deny', {}, [], [])
    dns = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
           'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}
    policy('dns', {}, egress=[{'to': [dns], 'ports': [tcp(53), {'protocol': 'UDP', 'port': 53}]}])
    for name, port in PORTS.items():
        sources = [peer('frontend')] if name != 'frontend' else [peer(ingress_app, ingress_ns)]
        if name == 'deployment-service':
            sources += [peer('aiops-service'), peer('prometheus', monitor_ns)]
        if name == 'aiops-service':
            sources += [peer('alertmanager', monitor_ns)]
        policy(name + '-ingress', {'matchLabels': {'app': name}}, ingress=[{'from': sources, 'ports': [tcp(port)]}])
        egress = []
        if name == 'frontend':
            egress += [{'to': [peer(service)], 'ports': [tcp(p)]} for service, p in PORTS.items() if service != name]
        if name == 'aiops-service':
            egress += [{'to': [peer('deployment-service')], 'ports': [tcp(8082)]}]
        if name in {'frontend', 'deployment-service', 'aiops-service', 'finops-service'}:
            egress += [{'to': [peer('prometheus', monitor_ns)], 'ports': [tcp(9090)]}]
        if name == 'frontend':
            egress += [{'to': [peer('grafana', monitor_ns)], 'ports': [tcp(3000)]}]
        if name != 'frontend':
            egress += [{'to': networks['database'], 'ports': [tcp(5432)]}]
        if name in {'infrastructure-service', 'finops-service', 'aiops-service'}:
            egress += [{'to': networks['aws_https'], 'ports': [tcp(443)]}]
        if name == 'deployment-service':
            egress += [{'to': networks['kubernetes_api'], 'ports': [tcp(443)]}]
        policy(name + '-egress', {'matchLabels': {'app': name}}, egress=egress)
    return docs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True, type=Path)
    args = parser.parse_args()
    try:
        result = render(json.loads(args.config.read_text()))
    except (ValueError, KeyError, TypeError) as exc:
        parser.exit(2, 'Deployment inputs invalid; check required fields and formats.\n')
    print(yaml.safe_dump_all(result, sort_keys=False), end='')
