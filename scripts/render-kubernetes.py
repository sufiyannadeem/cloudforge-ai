#!/usr/bin/env python3
"""Render reviewed, non-secret deployment inputs. Never applies resources."""
import copy
import argparse
import ipaddress
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

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


def monitoring_endpoint(value, service, namespace):
    """Only reviewed native-TLS monitoring Services; no invented HTTPS fallback."""
    if not isinstance(value, str) or any(ord(char) <= 32 for char in value):
        raise ValueError('Configure a reviewed TLS endpoint for ' + service)
    endpoint = urlsplit(value)
    try:
        port = endpoint.port if endpoint.port is not None else 443
    except ValueError as exc:
        raise ValueError('Invalid monitoring TLS port') from exc
    if (endpoint.scheme != 'https' or endpoint.hostname not in {f'{service}.{namespace}.svc', f'{service}.{namespace}.svc.cluster.local'}
            or endpoint.username or endpoint.password or endpoint.path not in {'', '/'}
            or endpoint.query or endpoint.fragment or not 1 <= port <= 65535):
        raise ValueError('Monitoring requires the approved Service HTTPS origin')
    return value.rstrip('/'), port


def render(config):
    account = checked(r'[0-9]{12}', config['account_id'], 'account_id')
    region = checked(r'[a-z]{2}-[a-z]+-[0-9]', config['region'], 'region')
    image_pull_secret = config.get('image_pull_secret')
    if image_pull_secret is not None:
        checked(r'[a-z0-9][a-z0-9.-]*', image_pull_secret, 'image_pull_secret')
    role_pattern = rf'arn:aws:iam::{account}:role/[A-Za-z0-9+=,.@_/-]+'
    free_plan = config.get('free_plan', False)
    if type(free_plan) is not bool:
        raise ValueError('free_plan must be boolean')
    rollout_mode = config.get('preview_rollout_mode', 'surge')
    if rollout_mode not in {'surge', 'serialized-no-surge'} or (rollout_mode != 'surge' and not free_plan):
        raise ValueError('serialized-no-surge is restricted to the free-plan preview')
    delivery = config.get('secret_delivery', 'external-secrets')
    if delivery not in {'external-secrets', 'preseeded'}:
        raise ValueError('Unknown secret_delivery')
    if free_plan and (delivery != 'preseeded' or config.get('ai', {}).get('provider', 'disabled') != 'disabled'
                      or config.get('drift', {}).get('enabled', False) or config.get('rollouts', {}).get('enabled', False)):
        raise ValueError('Free-plan preview requires preseeded secrets and disables AI, drift and Rollouts')
    roles = config['roles']
    base_roles = set() if free_plan else {'infrastructure-service', 'finops-service'}
    if delivery == 'external-secrets':
        base_roles.add('secret-sync')
    scheduled_drift = config.get('drift', {}).get('enabled', False)
    if type(scheduled_drift) is not bool:
        raise ValueError('drift.enabled must be boolean')
    if scheduled_drift:
        checked(role_pattern, roles.get('drift'), 'roles.drift')
    for name in base_roles:
        checked(role_pattern, roles[name], 'roles.' + name)
    if not free_plan:
        checked(role_pattern, config['provisioner_role_arn'], 'provisioner_role_arn')
    elif config.get('provisioner_role_arn') or roles:
        raise ValueError('Free-plan preview has no application AWS roles or tenant provisioning')
    ai = config.get('ai', {'provider': 'disabled'})
    if ai['provider'] not in {'disabled', 'bedrock'}:
        raise ValueError('Only disabled or explicitly configured Bedrock is supported')
    if ai['provider'] == 'bedrock':
        checked(role_pattern, roles['aiops-service'], 'roles.aiops-service')
        checked(r'[A-Za-z0-9.:/_-]+', ai['model'], 'ai.model')
        checked(r'[a-z0-9]{1,64}', ai.get('guardrail_id'), 'ai.guardrail_id')
        checked(r'[1-9][0-9]{0,7}', ai.get('guardrail_version'), 'ai.guardrail_version')
    if set(roles) != base_roles | ({'aiops-service'} if ai['provider'] == 'bedrock' else set()) | ({'drift'} if scheduled_drift else set()):
        raise ValueError('Unexpected workload role')
    if len(set(roles.values()) | {config['provisioner_role_arn']}) != len(roles) + 1:
        raise ValueError('Workload, sync and provisioner roles must be distinct')
    rollouts = config.get('rollouts', {'enabled': False})
    if not isinstance(rollouts['enabled'], bool):
        raise ValueError('rollouts.enabled must be a boolean')
    if rollouts['enabled']:
        checked(r'[a-z0-9][a-z0-9-]*', rollouts['analysis_template'], 'rollouts.analysis_template')
    reliability = config.get('reliability', {})
    minimum = reliability.get('min_replicas', 2)
    maximum = reliability.get('max_replicas', 4)
    cpu = reliability.get('cpu_utilization', 70)
    if free_plan and (minimum != 2 or maximum != 2):
        raise ValueError('Free-plan preview uses exactly two replicas; scale-out requires a new budget')
    if any(type(v) is not int for v in (minimum, maximum, cpu)) or not (2 <= minimum <= maximum <= 10) or not (30 <= cpu <= 90):
        raise ValueError('Invalid reliability replica bounds or CPU target')
    database_ca = checked(r'[a-z0-9][a-z0-9.-]*', config.get('database_ca_configmap'), 'database_ca_configmap')
    bucket = checked(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', config['state_bucket'], 'state_bucket')
    storage = config['storage']
    checked(r'[a-z0-9][a-z0-9.-]*', storage['class'], 'storage.class')
    checked(r'[1-9][0-9]*(Gi|Ti)', storage['size'], 'storage.size')
    monitor_ns = checked(r'[a-z0-9][a-z0-9-]*', config['monitoring_namespace'], 'monitoring_namespace')
    monitoring_tls = config.get('monitoring_tls', {})
    ca_name = checked(r'[a-z0-9][a-z0-9.-]*', monitoring_tls.get('ca_configmap'), 'monitoring_tls.ca_configmap')
    prometheus_url, _ = monitoring_endpoint(monitoring_tls.get('prometheus_url'), 'prometheus', monitor_ns)
    grafana_url, _ = monitoring_endpoint(monitoring_tls.get('grafana_url'), 'grafana', monitor_ns)
    prometheus_port = monitoring_tls.get('prometheus_pod_port')
    grafana_port = monitoring_tls.get('grafana_pod_port')
    if any(type(port) is not int or not 1 <= port <= 65535 for port in (prometheus_port, grafana_port)):
        raise ValueError('Configure reviewed monitoring Service target pod TLS ports')
    ingress_ns = checked(r'[a-z0-9][a-z0-9-]*', config['ingress_namespace'], 'ingress_namespace')
    ingress_app = checked(r'[a-z0-9][a-z0-9-]*', config['ingress_app'], 'ingress_app')
    # ALB data-plane packets originate at ALB ENIs, never controller pods.
    public_origin = config.get('public_origin')
    if public_origin is not None:
        origin = urlsplit(public_origin)
        if (origin.scheme != 'https' or not origin.hostname or origin.username or origin.password
                or origin.path not in {'', '/'} or origin.query or origin.fragment):
            raise ValueError('Configure an HTTPS public_origin without a path')
    if 'alb_subnet_cidrs' in config and not public_origin:
        raise ValueError('ALB deployments require public_origin for authentication')
    alb_sources = []
    if 'alb_subnet_cidrs' in config:
        if not isinstance(config['alb_subnet_cidrs'], list) or not config['alb_subnet_cidrs']:
            raise ValueError('Required ALB source subnet CIDRs')
        for cidr in config['alb_subnet_cidrs']:
            network = ipaddress.ip_network(cidr, strict=True)
            if network.version != 4 or not network.is_private or network.prefixlen == 0:
                raise ValueError('ALB sources must be private IPv4 subnets')
            alb_sources.append({'ipBlock': {'cidr': str(network)}})
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
    for d in list(docs):
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
        if image_pull_secret:
            spec['imagePullSecrets'] = [{'name': image_pull_secret}]
        d['spec']['template']['metadata'].pop('annotations', None)
        container = spec['containers'][0]
        container['image'] = checked(r'[a-z0-9][a-z0-9.:/_-]*@sha256:[0-9a-f]{64}', config['images'][name], 'images.' + name)
        container['imagePullPolicy'] = 'Always'
        container['securityContext'].update({'allowPrivilegeEscalation': False, 'capabilities': {'drop': ['ALL']}})
        spec['securityContext']['seccompProfile'] = {'type': 'RuntimeDefault'}
        spec['terminationGracePeriodSeconds'] = 120 if name == 'infrastructure-service' else 60
        # HPA owns scale after creation; reapplying a release must not reset it.
        d['spec'].pop('replicas', None)
        d['spec']['minReadySeconds'] = 10
        d['spec']['progressDeadlineSeconds'] = 600
        d['spec']['strategy'] = {'type': 'RollingUpdate', 'rollingUpdate': {'maxSurge': 0 if rollout_mode == 'serialized-no-surge' else 1, 'maxUnavailable': 1 if rollout_mode == 'serialized-no-surge' else 0}}
        spec['topologySpreadConstraints'] = [
            {'maxSkew': 1, 'minDomains': 2, 'topologyKey': key, 'whenUnsatisfiable': 'DoNotSchedule',
             'labelSelector': {'matchLabels': {'app': name}}}
            for key in ('kubernetes.io/hostname', 'topology.kubernetes.io/zone')
        ]
        container['lifecycle'] = {'preStop': {'exec': {'command': ['/bin/sh', '-c', 'sleep 5']}}}
        container['resources']['requests']['ephemeral-storage'] = '128Mi'
        container['resources']['limits']['ephemeral-storage'] = '4Gi'
        if name != 'frontend':
            container['readinessProbe']['httpGet']['path'] = '/ready'
            container['readinessProbe']['timeoutSeconds'] = 8 if name == 'finops-service' else 4
            if name == 'finops-service':
                container['readinessProbe']['periodSeconds'] = 10
        behavior = {
            'scaleUp': {'stabilizationWindowSeconds': 60, 'policies': [{'type': 'Pods', 'value': 1, 'periodSeconds': 60}]},
            'scaleDown': {'stabilizationWindowSeconds': 300, 'policies': [{'type': 'Pods', 'value': 1, 'periodSeconds': 60}]},
        }
        if name == 'infrastructure-service':
            # Terraform runs in synchronous HTTP requests. Never terminate those
            # pods automatically; planned drain/reconciliation remains required.
            behavior['scaleDown']['selectPolicy'] = 'Disabled'
            d['spec']['template']['metadata'].setdefault('annotations', {})['cluster-autoscaler.kubernetes.io/safe-to-evict'] = 'false'
        docs.extend([
            document('HorizontalPodAutoscaler', name, {
                'scaleTargetRef': {'apiVersion': 'apps/v1', 'kind': 'Deployment', 'name': name},
                'minReplicas': minimum, 'maxReplicas': maximum,
                'metrics': [{'type': 'Resource', 'resource': {'name': 'cpu', 'target': {'type': 'Utilization', 'averageUtilization': cpu}}}],
                'behavior': behavior,
            }, 'autoscaling/v2'),
            document('PodDisruptionBudget', name, {
                'maxUnavailable': 0 if name == 'infrastructure-service' else 1,
                'selector': {'matchLabels': {'app': name}},
            }, 'policy/v1'),
        ])
        if name != 'frontend':
            spec.setdefault('volumes', []).append({'name': 'database-ca', 'configMap': {'name': database_ca}})
            container.setdefault('volumeMounts', []).append({'name': 'database-ca', 'mountPath': '/etc/cloudforge/db-ca', 'readOnly': True})
        if name in {'project-service','infrastructure-service','deployment-service','aiops-service'}:
            for source in container.get('envFrom', []):
                if source.get('secretRef', {}).get('name') == 'cloudforge-postgres-credentials':
                    source['secretRef']['name'] = 'cloudforge-' + name.removesuffix('-service') + '-db'
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
        if free_plan:
            additional['AWS_EC2_METADATA_DISABLED'] = 'true'
        if free_plan and name == 'infrastructure-service':
            additional['TERRAFORM_READ_ONLY'] = 'true'
        if free_plan and name == 'finops-service':
            additional['CLOUDFORGE_AWS_BILLING_ENABLED'] = 'false'
        if name == 'frontend' and public_origin:
            additional['CLOUDFORGE_PUBLIC_ORIGIN'] = public_origin.rstrip('/')
        if name != 'frontend':
            additional['PGSSLROOTCERT'] = '/etc/cloudforge/db-ca/ca.crt'
        if name in {'project-service', 'deployment-service', 'infrastructure-service'}:
            additional['SHUTDOWN_TIMEOUT_SECONDS'] = '90' if name == 'infrastructure-service' else '20'
        if name in {'frontend', 'deployment-service', 'aiops-service', 'finops-service'}:
            additional['PROMETHEUS_URL'] = prometheus_url
            ca_file = '/etc/cloudforge/monitoring-ca/ca.crt'
            additional['NODE_EXTRA_CA_CERTS' if name == 'frontend' else 'SSL_CERT_FILE'] = ca_file
            spec.setdefault('volumes', []).append({'name': 'monitoring-ca', 'configMap': {'name': ca_name}})
            container.setdefault('volumeMounts', []).append({'name': 'monitoring-ca', 'mountPath': '/etc/cloudforge/monitoring-ca', 'readOnly': True})
        if name == 'deployment-service':
            additional['ARGO_ROLLOUTS_ENABLED'] = str(rollouts['enabled']).lower()
            if rollouts['enabled']:
                additional['ARGO_ANALYSIS_TEMPLATE'] = rollouts['analysis_template']
        if name == 'aiops-service':
            additional['DEPLOYMENT_SERVICE_URL'] = 'http://deployment-service:8082'
            additional['AI_PROVIDER'] = ai['provider']
            if ai['provider'] == 'bedrock':
                additional['AI_MODEL'] = ai['model']
                additional['AI_BEDROCK_GUARDRAIL_ID'] = ai['guardrail_id']
                additional['AI_BEDROCK_GUARDRAIL_VERSION'] = ai['guardrail_version']
        if name == 'frontend':
            additional['GRAFANA_URL'] = grafana_url
        container['env'] = [e for e in container.get('env', []) if e['name'] not in additional]
        container['env'] += [{'name': k, 'value': v} for k, v in additional.items()]
    # envFrom must be explicitly mapped, not unrestricted extraction of remote JSON.
    required = {'cloudforge-migration-db': {'DATABASE_URL'}, **{'cloudforge-' + name + '-db': {'DATABASE_URL'} for name in ['project','infrastructure','deployment','aiops']},
                'cloudforge-frontend-credentials': {'CLOUDFORGE_SESSION_SECRET'}}
    secret_keys = {name: keys | required.get(name, set()) for name, keys in secret_keys.items()}
    secret_keys['cloudforge-migration-db'] = {'DATABASE_URL'}
    if scheduled_drift: secret_keys['cloudforge-drift-db'] = {'DATABASE_URL'}
    if delivery == 'external-secrets':
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
    if delivery == 'preseeded':
        reviewed_keys = config.get('preseeded_secret_keys', {})
        if set(reviewed_keys) != set(secret_keys) or any(
                not isinstance(reviewed_keys[name], list) or set(reviewed_keys[name]) != keys
                for name, keys in secret_keys.items()):
            raise ValueError('Review exact preseeded Secret names/keys before rendering')
        docs = [d for d in docs if d['kind'] not in {'SecretStore', 'ExternalSecret'}
                and not (d['kind'] == 'ServiceAccount' and d['metadata']['name'] == 'cloudforge-secret-sync')]
    migration_sa = document('ServiceAccount', 'cloudforge-migrator', {})
    migration_sa.pop('spec')
    migration_sa['automountServiceAccountToken'] = False
    docs.append(migration_sa)
    grants = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'cloudforge-database-grants', 'namespace': 'cloudforge'},
              'data': {'runtime.sql': (ROOT / 'deploy/postgres/002_runtime_grants.sql').read_text()}}
    docs.append(grants)
    workloads = {d['metadata']['name']: d for d in docs if d['kind'] == 'Deployment'}
    grant_code = "import os,psycopg\nfrom app.service_identity import production_database\ndsn=os.environ['DATABASE_URL']\nproduction_database(dsn,'cf_migrator')\nwith psycopg.connect(dsn) as c:\n c.execute(open('/database-grants/runtime.sql').read(),prepare=False)\n"
    for wave, name in enumerate(['project-service','infrastructure-service','deployment-service','aiops-service','database-grants']):
        source = workloads['aiops-service' if name == 'database-grants' else name]['spec']['template']['spec']
        original = source['containers'][0]
        container = {key: copy.deepcopy(original[key]) for key in ['name','image','imagePullPolicy','resources','securityContext']}
        container['name'] = 'migrate'
        container['args'] = ['migrate']
        if name == 'aiops-service':
            container['command'] = ['python','-m','app.database']; container.pop('args')
        if name == 'database-grants':
            container['command'] = ['python','-c',grant_code]; container.pop('args')
        container['env'] = [{'name':'APP_ENV','value':'production'}, {'name':'PGSSLROOTCERT','value':'/etc/cloudforge/db-ca/ca.crt'},
                            {'name':'PYTHONDONTWRITEBYTECODE','value':'1'}, {'name':'TMPDIR','value':'/var/run/cloudforge'}, {'name':'TERRAFORM_READ_ONLY','value':'true'}]
        container['envFrom'] = [{'secretRef': {'name':'cloudforge-migration-db'}}]
        container['volumeMounts'] = [{'name':'database-ca','mountPath':'/etc/cloudforge/db-ca','readOnly':True}, {'name':'tmp','mountPath':'/var/run/cloudforge'}]
        volumes = [{'name':'database-ca','configMap':{'name':database_ca}}, {'name':'tmp','emptyDir':{'sizeLimit':'128Mi'}}]
        if name == 'database-grants':
            volumes.append({'name':'grants','configMap':{'name':'cloudforge-database-grants'}})
            container['volumeMounts'].append({'name':'grants','mountPath':'/database-grants','readOnly':True})
        pod = {'serviceAccountName':'cloudforge-migrator','automountServiceAccountToken':False,
               'restartPolicy':'Never','terminationGracePeriodSeconds':30,'securityContext':copy.deepcopy(source['securityContext']),
               'containers':[container],'volumes':volumes}
        if image_pull_secret:
            pod['imagePullSecrets'] = [{'name': image_pull_secret}]
        job = document('Job','cloudforge-'+name+'-migrate',{'backoffLimit':0,'activeDeadlineSeconds':300,
                        'template':{'metadata':{'labels':{'cloudforge.ai/component':'database-migration'}},'spec':pod}},'batch/v1')
        job['metadata']['annotations'] = {'argocd.argoproj.io/hook':'Sync','argocd.argoproj.io/sync-wave':str(wave-5),
            'argocd.argoproj.io/hook-delete-policy':'HookSucceeded,BeforeHookCreation'}
        docs.append(job)
    for item in docs:
        if item['kind'] in {'SecretStore','ExternalSecret','ServiceAccount','ConfigMap','NetworkPolicy'}:
            item['metadata'].setdefault('annotations',{})['argocd.argoproj.io/sync-wave']='-10'
        if item['kind']=='Deployment':
            item['metadata'].setdefault('annotations',{})['argocd.argoproj.io/sync-wave']='0'
    cm = {'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'cloudforge-terraform', 'namespace': 'cloudforge'},
          'data': {'TERRAFORM_STATE_BUCKET': bucket, 'TERRAFORM_STATE_REGION': region,
                   'TERRAFORM_PROVISIONER_ROLE_ARN': config.get('provisioner_role_arn', '')}}
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
    policy('database-migrations-egress', {'matchLabels': {'cloudforge.ai/component':'database-migration'}}, egress=[{'to': networks['database'], 'ports':[tcp(5432)]}])
    policy('default-deny', {}, [], [])
    dns = {'namespaceSelector': {'matchLabels': {'kubernetes.io/metadata.name': 'kube-system'}},
           'podSelector': {'matchLabels': {'k8s-app': 'kube-dns'}}}
    policy('dns', {}, egress=[{'to': [dns], 'ports': [tcp(53), {'protocol': 'UDP', 'port': 53}]}])
    for name, port in PORTS.items():
        sources = [peer('frontend')] if name != 'frontend' else (alb_sources or [peer(ingress_app, ingress_ns)])
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
            egress += [{'to': [peer('prometheus', monitor_ns)], 'ports': [tcp(prometheus_port)]}]
        if name == 'frontend':
            egress += [{'to': [peer('grafana', monitor_ns)], 'ports': [tcp(grafana_port)]}]
        if name != 'frontend':
            egress += [{'to': networks['database'], 'ports': [tcp(5432)]}]
        if name in {'infrastructure-service', 'finops-service', 'aiops-service'}:
            egress += [{'to': networks['aws_https'], 'ports': [tcp(443)]}]
        if name == 'deployment-service':
            egress += [{'to': networks['kubernetes_api'], 'ports': [tcp(443)]}]
        policy(name + '-egress', {'matchLabels': {'app': name}}, egress=egress)
    if scheduled_drift:
        sa = document('ServiceAccount','cloudforge-drift',{})
        sa.pop('spec');sa['automountServiceAccountToken']=False
        sa['metadata']['annotations']={'eks.amazonaws.com/role-arn':roles['drift']}
        docs.append(sa)
        original=workloads['infrastructure-service']['spec']['template']['spec']
        source=original['containers'][0]
        container={key:copy.deepcopy(source[key]) for key in ['name','image','imagePullPolicy','resources','securityContext']}
        container['name']='drift';container['args']=['drift-scan']
        container['envFrom']=[{'secretRef':{'name':'cloudforge-drift-db'}}]
        container['env']=[{'name':key,'value':value} for key,value in {
            'APP_ENV':'production','TERRAFORM_READ_ONLY':'true','AWS_REGION':region,'AWS_DEFAULT_REGION':region,
            'AWS_STS_REGIONAL_ENDPOINTS':'regional','AWS_EC2_METADATA_DISABLED':'true','CLOUDFORGE_DRIFT_ROLE_ARN':roles['drift'],'TERRAFORM_STATE_BUCKET':bucket,'TERRAFORM_STATE_REGION':region,
            'PGSSLROOTCERT':'/etc/cloudforge/db-ca/ca.crt','TERRAFORM_WORKSPACE_ROOT':'/var/lib/cloudforge/terraform','TMPDIR':'/var/lib/cloudforge'}.items()]
        container['volumeMounts']=[{'name':'database-ca','mountPath':'/etc/cloudforge/db-ca','readOnly':True},{'name':'tmp','mountPath':'/var/lib/cloudforge'}]
        pod={'serviceAccountName':'cloudforge-drift','automountServiceAccountToken':False,'restartPolicy':'Never',
             'terminationGracePeriodSeconds':15,'securityContext':copy.deepcopy(original['securityContext']),
             'containers':[container],'volumes':[{'name':'database-ca','configMap':{'name':database_ca}}, {'name':'tmp','emptyDir':{'sizeLimit':'2Gi'}}]}
        if image_pull_secret:
            pod['imagePullSecrets'] = [{'name': image_pull_secret}]
        docs.append(document('CronJob','cloudforge-drift',{'schedule':'0 * * * *','concurrencyPolicy':'Forbid',
            'startingDeadlineSeconds':300,'successfulJobsHistoryLimit':1,'failedJobsHistoryLimit':1,
            'jobTemplate':{'spec':{'backoffLimit':0,'activeDeadlineSeconds':120,'ttlSecondsAfterFinished':7200,
                'template':{'metadata':{'labels':{'cloudforge.ai/component':'scheduled-drift'}},'spec':pod}}}},'batch/v1'))
        policy('drift-reader-egress',{'matchLabels':{'cloudforge.ai/component':'scheduled-drift'}},egress=[
            {'to':networks['database'],'ports':[tcp(5432)]},{'to':networks['aws_https'],'ports':[tcp(443)]}])
    for item in docs:
        if item['kind'] in {'SecretStore','ExternalSecret','ServiceAccount','ConfigMap','NetworkPolicy'}:
            item['metadata'].setdefault('annotations',{})['argocd.argoproj.io/sync-wave']='-10'
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
