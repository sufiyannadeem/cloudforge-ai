"""Targeted offline preview monitoring and failure-scenario contracts."""
import copy
from preflight_fixtures import scenario_inputs
import importlib.util
import json
from pathlib import Path
import pytest
import yaml
ROOT=Path(__file__).resolve().parents[1]
def module(name,file):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
monitor=module('monitor','render-preview-monitoring.py')
safety=module('safety','check-preview-safety.py')
@pytest.fixture
def config():
    c=json.loads((ROOT/'deploy/preview/monitoring-bindings.template.json').read_text())
    c.update(storage_class='fixture-encrypted-ebs',ca_configmap='fixture-ca',api_server_cidrs=['10.40.10.5/32'],
             grafana_admin_secret='fixture-grafana-admin',alertmanager_identity_secret='fixture-alert-identity')
    c['tls_secrets']={n:'fixture-'+n+'-tls' for n in monitor.PORTS}
    c['preseeded_secret_keys']={n:['tls.crt','tls.key'] for n in c['tls_secrets'].values()}
    c['preseeded_secret_keys'].update({'fixture-grafana-admin':['admin-user','admin-password'],'fixture-alert-identity':['CLOUDFORGE_ALERTMANAGER_KEY']})
    return c

def test_unbound_and_insecure_inputs_rejected(config):
    with pytest.raises(ValueError):monitor.render(json.loads((ROOT/'deploy/preview/monitoring-bindings.template.json').read_text()))
    for change in ({'free_plan':False},{'api_server_cidrs':[]},{'api_server_cidrs':['0.0.0.0/0']},{'api_server_cidrs':['8.8.8.8/32']},{'preseeded_secret_keys':{}},{'grafana_admin_secret':config['alertmanager_identity_secret']}):
        c=copy.deepcopy(config);c.update(change)
        with pytest.raises(ValueError):monitor.render(c)

def test_render_preserves_exact_budget_pods_storage_and_security(config):
    docs=monitor.render(config);budget=json.loads(monitor.BUDGET.read_text())
    workloads={d['metadata']['name']:d for d in docs if d['kind']=='Deployment'}
    assert set(workloads)==set(budget) and len(workloads)==4
    assert sum(int(d['spec']['resources']['requests']['storage'][:-2]) for d in docs if d['kind']=='PersistentVolumeClaim')==20
    assert not any(d['kind'] in {'Secret','Ingress','ClusterRole','ClusterRoleBinding'} for d in docs)
    assert max(i for i,d in enumerate(docs) if d['kind']=='NetworkPolicy') < min(i for i,d in enumerate(docs) if d['kind']=='Deployment')
    for n,d in workloads.items():
        assert d['spec']['strategy']=={'type':'Recreate'} and d['spec']['replicas']==1
        pod=d['spec']['template']['spec'];assert len(pod['containers'])==1 and 'initContainers' not in pod
        c=pod['containers'][0];assert c['image']==budget[n]['immutable_image']
        for key in ('cpu','memory'):assert c['resources']['requests'][key]==budget[n]['resources']['requests'][key]
        assert c['securityContext']['readOnlyRootFilesystem'] and c['securityContext']['runAsNonRoot']
        assert not c['securityContext']['allowPrivilegeEscalation']
        assert c['securityContext']['capabilities']=={'drop':['ALL']}
        assert pod['automountServiceAccountToken']==(n=='kube-state-metrics')
        assert c['readinessProbe']['httpGet']['scheme']=='HTTPS'
    assert workloads['kube-state-metrics']['spec']['template']['spec']['containers'][0]['readinessProbe']['httpGet']=={'path':'/readyz','port':8081,'scheme':'HTTPS'}

def test_tls_verified_scrapes_alerts_and_replica_discovery(config):
    docs=monitor.render(config);cms={d['metadata']['name']:d['data'] for d in docs if d['kind']=='ConfigMap'}
    web=yaml.safe_load(cms['monitoring-web']['web.yml']);assert web['tls_server_config']['min_version']=='TLS12'
    prom=yaml.safe_load(cms['preview-prometheus']['prometheus.yml'])
    for job in prom['scrape_configs']:
        if job['job_name']=='deployment-service':
            assert job['dns_sd_configs'][0]['names']==['deployment-metrics.cloudforge.svc']
        else:assert job['scheme']=='https' and job['tls_config']['insecure_skip_verify'] is False
    assert prom['alerting']['alertmanagers'][0]['tls_config']['insecure_skip_verify'] is False
    headless=next(d for d in docs if d['kind']=='Service' and d['metadata']['name']=='deployment-metrics')
    assert headless['spec']['clusterIP']=='None' and headless['metadata']['namespace']=='cloudforge'
    assert all(d['spec'].get('type','ClusterIP')=='ClusterIP' for d in docs if d['kind']=='Service')
    alerts=yaml.safe_load(cms['preview-alertmanager']['alertmanager.yml'])
    assert alerts['receivers'][0]['webhook_configs'][0]['http_config']['authorization']['credentials_file'].endswith('CLOUDFORGE_ALERTMANAGER_KEY')
    assert not any('drift' in k for k in cms['preview-monitoring-rules'])

def test_network_and_rbac_scopes_match_existing_application_paths(config):
    docs=monitor.render(config)
    roles=[d for d in docs if d['kind']=='Role'];assert len(roles)==1 and roles[0]['metadata']['namespace']=='cloudforge'
    assert all(set(r['verbs'])=={'list','watch'} and 'secrets' not in r['resources'] for r in roles[0]['rules'])
    policies={d['metadata']['name']:d['spec'] for d in docs if d['kind']=='NetworkPolicy'}
    assert policies['preview-default-deny']['ingress']==policies['preview-default-deny']['egress']==[]
    for p in policies.values():
        for rule in p['ingress']:
            assert rule['from'] and all('namespaceSelector' in v and 'podSelector' in v for v in rule['from'])
        assert '0.0.0.0/0' not in json.dumps(p)
    assert any(r['ports']==[{'protocol':'TCP','port':443}] for r in policies['kube-state-metrics']['egress'])

def test_failure_phases_credit_arithmetic_cost_and_reserve():
    r=safety.evaluate(*scenario_inputs());assert r['deployment_verdict']=='NO-GO'
    for o in r['options']:
        assert o['scheduling_headroom_cpu_m']==150 and o['request_occupancy_percent']==96.11
        assert not o['sensitivity_100m_spare_per_node']['feasible']
        assert o['cold_migration']['feasible'] and not o['live_migration']['feasible']
        assert not o['node_failure']['fits_full_replacement']
        assert o['five_day']['arithmetic_within_cap'] and float(o['five_day']['credit_remaining'])>=29
    m=r['options'][2];assert m['instance_type']=='m6a.large'
    assert m['five_day']['envelope_total']=='97.03' and m['five_day']['credit_remaining']=='37.86'
    assert m['credit_sustainability']['guaranteed_total_vcpu_baseline']==4


def test_terraform_credit_mode_expression_uses_standard_only_for_burstable(tmp_path):
    import re
    import subprocess
    text=(ROOT/'infrastructure/terraform/environments/dev/eks.tf').read_text().split('resource "aws_launch_template" "nodes" {',1)[1]
    expression=re.search(r'for_each = (.*)',text).group(1)
    # Execute the actual HCL expression in a provider-free temporary console.
    (tmp_path/'main.tf').write_text('variable "eks_node_instance_types" { type = list(string) }\n')
    for instances,expected in [(['t3.medium'],1),(['t3a.large'],1),(['t3.large'],1),(['m6a.large'],0)]:
        query=expression.replace('var.eks_node_instance_types',json.dumps(instances))
        p=subprocess.run(['terraform',f'-chdir={tmp_path}','console','-no-color'],input='length('+query+')\n',text=True,capture_output=True,check=True)
        assert int(p.stdout.strip())==expected
    condition=re.search(r'condition = (.*?)\n      error_message',text,re.S).group(1).strip()
    for instances,expected in [(['t3a.large'],True),(['m6a.large'],True),([],False),(['t3a.large','m6a.large'],False)]:
        query=condition.replace('var.eks_node_instance_types',json.dumps(instances)).replace('\n',' ')
        p=subprocess.run(['terraform',f'-chdir={tmp_path}','console','-no-color'],input=query+'\n',text=True,capture_output=True,check=True)
        assert p.stdout.strip()==str(expected).lower()


def test_native_monitoring_configs_and_kubernetes_schema(config,tmp_path):
    """Optional cached official tools; never downloads or contacts a target."""
    import os
    import subprocess
    import jsonschema
    paths={key:os.environ.get(key) for key in ('PROMTOOL','AMTOOL','KUBERNETES_OPENAPI')}
    if not all(paths.values()):pytest.skip('Set paths to cached pinned native tools and official Kubernetes OpenAPI')
    docs=monitor.render(config);schema=json.loads(Path(paths['KUBERNETES_OPENAPI']).read_text())
    # OpenAPI v2 represents Kubernetes IntOrString as string plus a format.
    # Draft4 needs its documented integer|string union normalized explicitly.
    for definition in schema['definitions'].values():
        if definition.get('format')=='int-or-string':definition['type']=['integer','string']
    for d in docs:
        group_version=d['apiVersion'].split('/')
        group,version=group_version if len(group_version)==2 else ('core',group_version[0])
        group = '' if group == 'core' else group
        definition=next(key for key,value in schema['definitions'].items()
                        if {'group':group,'version':version,'kind':d['kind']} in value.get('x-kubernetes-group-version-kind',[]))
        jsonschema.Draft4Validator({'$ref':'#/definitions/'+definition,'definitions':schema['definitions']}).validate(d)
    cms={d['metadata']['name']:d['data'] for d in docs if d['kind']=='ConfigMap'}
    rules=tmp_path/'rules';rules.mkdir()
    for n,value in cms['preview-monitoring-rules'].items():(rules/n).write_text(value)
    prom=yaml.safe_load(cms['preview-prometheus']['prometheus.yml'])
    prom['rule_files']=[str(rules/'*.yml')]
    (tmp_path/'prometheus.yml').write_text(yaml.safe_dump(prom))
    subprocess.run([paths['PROMTOOL'],'check','config','--syntax-only',str(tmp_path/'prometheus.yml')],check=True,capture_output=True,text=True)
    subprocess.run([paths['PROMTOOL'],'check','rules',*[str(p) for p in rules.glob('*.yml')]],check=True,capture_output=True,text=True)
    alerts=yaml.safe_load(cms['preview-alertmanager']['alertmanager.yml'])
    identity=tmp_path/'identity';identity.write_text('synthetic-offline-fixture-only')
    alerts['receivers'][0]['webhook_configs'][0]['http_config']['authorization']['credentials_file']=str(identity)
    (tmp_path/'alertmanager.yml').write_text(yaml.safe_dump(alerts))
    subprocess.run([paths['AMTOOL'],'check-config',str(tmp_path/'alertmanager.yml')],check=True,capture_output=True,text=True)
    # A synthetic CA/leaf exists solely in tmp_path; no deployment certificates invented.
    subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-subj','/CN=synthetic-offline-fixture',
        '-keyout',str(tmp_path/'key.pem'),'-out',str(tmp_path/'cert.pem'),'-days','1'],check=True,capture_output=True)
    web=yaml.safe_load(cms['monitoring-web']['web.yml'])
    web['tls_server_config'].update(cert_file=str(tmp_path/'cert.pem'),key_file=str(tmp_path/'key.pem'))
    (tmp_path/'web.yml').write_text(yaml.safe_dump(web))
    subprocess.run([paths['PROMTOOL'],'check','web-config',str(tmp_path/'web.yml')],check=True,capture_output=True,text=True)


def test_all_six_apps_and_monitoring_have_matching_tls_peers_and_budgets(config):
    foundation=module('foundation_fixture','../tests/test_deployment_foundation.py')
    a=foundation.config.__wrapped__()
    a.update(free_plan=True,secret_delivery='preseeded',roles={},provisioner_role_arn='',preview_rollout_mode='serialized-no-surge')
    a['reliability']={'min_replicas':2,'max_replicas':2}
    a['preseeded_secret_keys']={n:list(v['properties']) for n,v in a['secrets'].items()}
    a['monitoring_tls']['ca_configmap']=config['ca_configmap']
    docs=foundation.renderer.render(a)
    workloads={d['metadata']['name']:d for d in docs if d['kind']=='Deployment'}
    profile=json.loads((ROOT/'deploy/preview/scheduling-profile.json').read_text())
    assert set(workloads)=={g['name'] for g in profile['applications']}
    for g in profile['applications']:
        c=workloads[g['name']]['spec']['template']['spec']['containers'][0]
        assert c['resources']['requests']['cpu']==str(g['cpu_m'])+'m'
        assert c['resources']['requests']['memory']==str(g['memory_mi'])+'Mi'
    app_policies={d['metadata']['name']:d['spec'] for d in docs if d['kind']=='NetworkPolicy'}
    for policy,source in [('deployment-service-ingress','prometheus'),('aiops-service-ingress','alertmanager')]:
        peers=[p for rule in app_policies[policy]['ingress'] for p in rule['from']]
        assert any(p.get('podSelector',{}).get('matchLabels',{}).get('app')==source
                   and p.get('namespaceSelector',{}).get('matchLabels',{}).get('kubernetes.io/metadata.name')=='monitoring' for p in peers)
    assert a['monitoring_tls']['prometheus_url']=='https://prometheus.monitoring.svc:9090'
    assert a['monitoring_tls']['grafana_url']=='https://grafana.monitoring.svc:3000'
    for d in docs:
        if d['kind']=='HorizontalPodAutoscaler':assert d['spec']['minReplicas']==d['spec']['maxReplicas']==2
