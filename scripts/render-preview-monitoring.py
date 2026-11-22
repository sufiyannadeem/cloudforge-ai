#!/usr/bin/env python3
"""Offline preview monitoring integration. Unbound inputs fail; never creates secrets."""
import argparse
import copy
import ipaddress
import json
from pathlib import Path
import re
import yaml

ROOT=Path(__file__).resolve().parents[1]
BUDGET=ROOT/'deploy/preview/monitoring-budget.json'
PORTS={'prometheus':9090,'grafana':3000,'alertmanager':9093,'kube-state-metrics':8080}

def name(value):
    if not isinstance(value,str) or len(value)>63 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]*[a-z0-9])?',value):
        raise ValueError('A bound Kubernetes name is required')
    return value

def render(config):
    if config.get('free_plan') is not True or config.get('app_namespace')!='cloudforge':
        raise ValueError('Only the reviewed cloudforge free-plan preview is supported')
    ns=name(config['namespace']);storage=name(config['storage_class']);ca=name(config['ca_configmap'])
    if ns!='monitoring':raise ValueError('Namespace must match the reviewed monitoring budget')
    cidrs=config['api_server_cidrs']
    if not cidrs:raise ValueError('Bound API server private CIDRs required')
    for cidr in cidrs:
        net=ipaddress.ip_network(cidr,strict=True)
        if net.version!=4 or net.prefixlen==0 or not net.is_private:raise ValueError('Private IPv4 API CIDRs required')
    required={name(config['grafana_admin_secret']):{'admin-user','admin-password'},
              name(config['alertmanager_identity_secret']):{'CLOUDFORGE_ALERTMANAGER_KEY'}}
    tls={n:name(config['tls_secrets'][n]) for n in PORTS}
    if len(set(tls.values()) | {config['grafana_admin_secret'],config['alertmanager_identity_secret']})!=6:
        raise ValueError('Keep service TLS, Grafana admin and alert identities in distinct secrets')
    for secret in tls.values():required.setdefault(secret,set()).update({'tls.crt','tls.key'})
    for secret,keys in required.items():
        if not keys.issubset(set(config.get('preseeded_secret_keys',{}).get(secret,[]))):
            raise ValueError('Missing preseeded secret keys: '+secret)
    docs=[]
    def doc(kind,n,spec,api='v1',namespace=ns):
        d={'apiVersion':api,'kind':kind,'metadata':{'name':n,'namespace':namespace},'spec':spec}
        docs.append(d);return d
    def cm(n,data):
        d=doc('ConfigMap',n,{});d.pop('spec');d['data']=data
    def peer(app,namespace=ns):
        return {'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':namespace}},'podSelector':{'matchLabels':{'app':app}}}
    def tcp(port):return {'protocol':'TCP','port':port}
    def policy(n,selector,ingress,egress):
        doc('NetworkPolicy',n,{'podSelector':selector,'policyTypes':['Ingress','Egress'],'ingress':ingress,'egress':egress},'networking.k8s.io/v1')
    # Four native TLS listeners, no proxy/sidecar/pod or extra resource request.
    web=yaml.safe_dump({'tls_server_config':{'cert_file':'/etc/cloudforge/tls/tls.crt','key_file':'/etc/cloudforge/tls/tls.key','min_version':'TLS12'}})
    cm('monitoring-web',{'web.yml':web})
    tls_client={'ca_file':'/etc/cloudforge/ca/ca.crt','min_version':'TLS12','insecure_skip_verify':False}
    scrape=[]
    for n in ('prometheus','alertmanager','kube-state-metrics'):
        scrape.append({'job_name':n,'scheme':'https','tls_config':copy.deepcopy(tls_client),
                       'sample_limit':10000,'static_configs':[{'targets':[f'{n}.{ns}.svc:{PORTS[n]}']} ]})
    scrape.append({'job_name':'deployment-service','scheme':'http','metrics_path':'/metrics','sample_limit':10000,
                   'dns_sd_configs':[{'names':['deployment-metrics.cloudforge.svc'],'type':'A','port':8082,'refresh_interval':'30s'}],
                   'relabel_configs':[{'target_label':'service','replacement':'deployment-service'},
                                     {'target_label':'environment','replacement':'preview'}]})
    prom={'global':{'scrape_interval':'30s','evaluation_interval':'30s','scrape_timeout':'10s'},
          'rule_files':['/etc/cloudforge/rules/*.yml'],'scrape_configs':scrape,
          'alerting':{'alertmanagers':[{'scheme':'https','tls_config':tls_client,'static_configs':[{'targets':[f'alertmanager.{ns}.svc:9093']}]}]}}
    cm('preview-prometheus',{'prometheus.yml':yaml.safe_dump(prom)})
    rules={p.name:p.read_text() for p in (ROOT/'monitoring/prometheus/rules').glob('*.yml') if 'drift' not in p.name}
    cm('preview-monitoring-rules',rules)
    alerts={'global':{'resolve_timeout':'5m'},'route':{'receiver':'aiops','group_by':['alertname','service'],'group_wait':'30s','group_interval':'5m','repeat_interval':'4h'},
            'receivers':[{'name':'aiops','webhook_configs':[{'url':'http://aiops-service.cloudforge.svc:8090/api/v1/alerts',
                         'send_resolved':True,'http_config':{'authorization':{'credentials_file':'/etc/cloudforge/alert-identity/CLOUDFORGE_ALERTMANAGER_KEY'}}}]}]}
    cm('preview-alertmanager',{'alertmanager.yml':yaml.safe_dump(alerts)})
    # Default Go CA verification uses the mounted CA; no tlsSkipVerify exception.
    ds={'apiVersion':1,'datasources':[{'name':'Prometheus','uid':'prometheus','type':'prometheus','access':'proxy',
        'url':f'https://prometheus.{ns}.svc:9090','isDefault':True,'editable':False,'jsonData':{'tlsSkipVerify':False}}]}
    cm('preview-grafana-datasources',{'datasources.yml':yaml.safe_dump(ds)})
    cm('preview-grafana-dashboard-provider',{'dashboards.yml':yaml.safe_dump({'apiVersion':1,'providers':[{'name':'CloudForge','type':'file','disableDeletion':True,'editable':False,'options':{'path':'/etc/cloudforge/dashboards'}}]})})
    cm('preview-grafana-dashboards',{p.name:p.read_text() for p in (ROOT/'monitoring/grafana/dashboards').glob('*.json')})
    # Read-only KSM access is namespace-scoped and excludes Secrets and cluster resources.
    sa=doc('ServiceAccount','kube-state-metrics',{});sa.pop('spec');sa['automountServiceAccountToken']=False
    role=doc('Role','preview-metrics-reader',{},'rbac.authorization.k8s.io/v1','cloudforge');role.pop('spec')
    role['rules']=[{'apiGroups':[group],'resources':resources,'verbs':['list','watch']} for group,resources in [('apps',['deployments']),('batch',['jobs','cronjobs']),('autoscaling',['horizontalpodautoscalers'])]]
    rb=doc('RoleBinding','preview-metrics-reader',{},'rbac.authorization.k8s.io/v1','cloudforge');rb.pop('spec')
    rb.update(roleRef={'apiGroup':'rbac.authorization.k8s.io','kind':'Role','name':'preview-metrics-reader'},subjects=[{'kind':'ServiceAccount','name':'kube-state-metrics','namespace':ns}])
    for n,b in json.loads(BUDGET.read_text()).items():
        port=PORTS[n];uid=472 if n=='grafana' else 65534
        volumes=[{'name':'tls','secret':{'secretName':tls[n],'defaultMode':0o440}},
                 {'name':'ca','configMap':{'name':ca}}, {'name':'web','configMap':{'name':'monitoring-web'}},
                 {'name':'tmp','emptyDir':{'sizeLimit':'128Mi'}}]
        mounts=[{'name':key,'mountPath':path,'readOnly':True} for key,path in [('tls','/etc/cloudforge/tls'),('ca','/etc/cloudforge/ca'),('web','/etc/cloudforge/web')]]
        mounts.append({'name':'tmp','mountPath':'/tmp'})
        def config_mount(key,path):
            volumes.append({'name':key,'configMap':{'name':key}});mounts.append({'name':key,'mountPath':path,'readOnly':True})
        container={'name':n,'image':b['immutable_image'],'imagePullPolicy':'Always','resources':copy.deepcopy(b['resources']),
                   'ports':[{'name':'https','containerPort':port}], 'volumeMounts':mounts,
                   'securityContext':{'runAsNonRoot':True,'runAsUser':uid,'allowPrivilegeEscalation':False,'readOnlyRootFilesystem':True,'capabilities':{'drop':['ALL']}},
                   'env':[{'name':'AWS_EC2_METADATA_DISABLED','value':'true'}]}
        container['resources']['requests']['ephemeral-storage']='128Mi'
        container['resources']['limits']={'memory':{'prometheus':'1Gi','grafana':'512Mi','alertmanager':'256Mi','kube-state-metrics':'256Mi'}[n],'ephemeral-storage':'256Mi'}
        if b['storage_gi']:
            doc('PersistentVolumeClaim',n,{'accessModes':['ReadWriteOnce'],'storageClassName':storage,'resources':{'requests':{'storage':f"{b['storage_gi']}Gi"}}})
            volumes.append({'name':'data','persistentVolumeClaim':{'claimName':n}})
            mounts.append({'name':'data','mountPath':'/var/lib/monitoring'})
        if n=='prometheus':
            config_mount('preview-prometheus','/etc/cloudforge/config');config_mount('preview-monitoring-rules','/etc/cloudforge/rules')
            container['args']=['--config.file=/etc/cloudforge/config/prometheus.yml','--web.config.file=/etc/cloudforge/web/web.yml','--storage.tsdb.path=/var/lib/monitoring',
                               '--storage.tsdb.retention.time=5d','--storage.tsdb.retention.size=12GB','--query.max-concurrency=2','--query.max-samples=1000000']
        elif n=='alertmanager':
            config_mount('preview-alertmanager','/etc/cloudforge/config')
            volumes.append({'name':'alert-identity','secret':{'secretName':config['alertmanager_identity_secret'],'defaultMode':0o440}})
            mounts.append({'name':'alert-identity','mountPath':'/etc/cloudforge/alert-identity','readOnly':True})
            container['args']=['--config.file=/etc/cloudforge/config/alertmanager.yml','--web.config.file=/etc/cloudforge/web/web.yml','--storage.path=/var/lib/monitoring','--data.retention=120h','--cluster.listen-address=']
        elif n=='kube-state-metrics':
            allow=yaml.safe_load((ROOT/'deploy/kubernetes/kube-state-metrics-values.example.yml').read_text())
            container['args']=['--namespaces=cloudforge','--resources='+','.join(allow['collectors']),'--metric-allowlist='+','.join(allow['metricAllowlist']),'--tls-config=/etc/cloudforge/web/web.yml','--telemetry-host=0.0.0.0']
        else:
            config_mount('preview-grafana-datasources','/etc/grafana/provisioning/datasources')
            config_mount('preview-grafana-dashboard-provider','/etc/grafana/provisioning/dashboards')
            config_mount('preview-grafana-dashboards','/etc/cloudforge/dashboards')
            env={'GF_SERVER_PROTOCOL':'https','GF_SERVER_HTTP_PORT':'3000','GF_SERVER_MIN_TLS_VERSION':'TLS1.2','GF_SERVER_CERTS_WATCH_INTERVAL':'1m','GF_SERVER_CERT_FILE':'/etc/cloudforge/tls/tls.crt','GF_SERVER_CERT_KEY':'/etc/cloudforge/tls/tls.key',
                 'GF_PATHS_DATA':'/var/lib/monitoring','GF_PATHS_LOGS':'/tmp','GF_PATHS_PLUGINS':'/var/lib/monitoring/plugins',
                 'GF_AUTH_ANONYMOUS_ENABLED':'false','GF_USERS_ALLOW_SIGN_UP':'false','GF_SECURITY_COOKIE_SECURE':'true',
                 'GF_ANALYTICS_REPORTING_ENABLED':'false','GF_ANALYTICS_CHECK_FOR_UPDATES':'false','GF_ANALYTICS_CHECK_FOR_PLUGIN_UPDATES':'false',
                 'SSL_CERT_FILE':'/etc/cloudforge/ca/ca.crt'}
            container['env'] += [{'name':k,'value':v} for k,v in env.items()]
            container['env'] += [{'name':k,'valueFrom':{'secretKeyRef':{'name':config['grafana_admin_secret'],'key':key}}} for k,key in [('GF_SECURITY_ADMIN_USER','admin-user'),('GF_SECURITY_ADMIN_PASSWORD','admin-password')]]
        path='/api/health' if n=='grafana' else '/readyz' if n=='kube-state-metrics' else '/-/ready'
        container['readinessProbe']={'httpGet':{'path':path,'port':8081 if n=='kube-state-metrics' else port,'scheme':'HTTPS'},'periodSeconds':10,'timeoutSeconds':5,'failureThreshold':3}
        container['startupProbe']={'tcpSocket':{'port':port},'periodSeconds':10,'failureThreshold':60}
        # Do not restart busy processes during startup/TSDB recovery; readiness gates traffic.
        pod={'automountServiceAccountToken':n=='kube-state-metrics','terminationGracePeriodSeconds':60,
             'securityContext':{'runAsNonRoot':True,'fsGroup':uid,'fsGroupChangePolicy':'OnRootMismatch','seccompProfile':{'type':'RuntimeDefault'}},'containers':[container],'volumes':volumes}
        if n=='kube-state-metrics':pod['serviceAccountName']=n
        labels={'app':n}
        doc('Deployment',n,{'replicas':1,'strategy':{'type':'Recreate'},'minReadySeconds':10,'progressDeadlineSeconds':900,'selector':{'matchLabels':labels},'template':{'metadata':{'labels':labels},'spec':pod}},'apps/v1')
        doc('Service',n,{'type':'ClusterIP','selector':labels,'ports':[{'name':'https','port':port,'targetPort':port}]})
    doc('Service','deployment-metrics',{'clusterIP':'None','selector':{'app':'deployment-service'},'ports':[{'name':'metrics','port':8082,'targetPort':8082}]},namespace='cloudforge')
    policy('preview-default-deny',{},[],[])
    dns={'namespaceSelector':{'matchLabels':{'kubernetes.io/metadata.name':'kube-system'}},'podSelector':{'matchLabels':{'k8s-app':'kube-dns'}}}
    for n in PORTS:
        ingress=[{'from':[peer('prometheus')],'ports':[tcp(PORTS[n])]}]
        if n=='prometheus':ingress[0]['from'] += [peer(x,'cloudforge') for x in ['frontend','deployment-service','aiops-service','finops-service']]+[peer('grafana')]
        if n=='grafana':ingress[0]['from']=[peer('frontend','cloudforge')]
        egress=[{'to':[dns],'ports':[tcp(53),{'protocol':'UDP','port':53}]}]
        if n=='prometheus':egress += [{'to':[peer(x)],'ports':[tcp(PORTS[x])]} for x in ('prometheus','alertmanager','kube-state-metrics')]+[{'to':[peer('deployment-service','cloudforge')],'ports':[tcp(8082)]}]
        if n=='grafana':egress += [{'to':[peer('prometheus')],'ports':[tcp(9090)]}]
        if n=='alertmanager':egress += [{'to':[peer('aiops-service','cloudforge')],'ports':[tcp(8090)]}]
        if n=='kube-state-metrics':egress += [{'to':[{'ipBlock':{'cidr':cidr}} for cidr in cidrs],'ports':[tcp(443)]}]
        policy(n,{'matchLabels':{'app':n}},ingress,egress)
    # Install isolation before workloads; no interval with unrestricted pods.
    waves={'NetworkPolicy':-20,'ConfigMap':-10,'ServiceAccount':-10,'Role':-10,'RoleBinding':-10,'PersistentVolumeClaim':-10,'Service':-5,'Deployment':0}
    for d in docs:d['metadata']['annotations']={'argocd.argoproj.io/sync-wave':str(waves[d['kind']])}
    return sorted(docs,key=lambda d:waves[d['kind']])

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True);args=parser.parse_args()
    try:docs=render(json.loads(args.config.read_text()))
    except (KeyError,TypeError,ValueError,OSError) as error:parser.exit(2,'NO-GO: '+str(error)+'\n')
    print(yaml.safe_dump_all(docs,sort_keys=False))
