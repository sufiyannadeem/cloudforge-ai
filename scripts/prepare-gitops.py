#!/usr/bin/env python3
"""Prepare restricted Argo CD resources offline. Never installs or applies them."""
import argparse
import json
from pathlib import Path
import re
from urllib.parse import urlparse
import yaml


def prepare(config):
    url=config['repo_url']; parsed=urlparse(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError('Credential-free HTTPS repository required')
    revision=config['revision']
    if not re.fullmatch('[0-9a-f]{40}',revision):raise ValueError('Exact reviewed Git commit required')
    path=config['path']
    if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9/_.-]*',path) or '..' in path.split('/'):
        raise ValueError('Repository-relative manifest directory required')
    namespace=config['argocd_namespace']
    if not re.fullmatch('[a-z0-9][a-z0-9-]*',namespace):raise ValueError('Invalid Argo namespace')
    groups=config['operator_groups']
    if not isinstance(groups,list) or not groups or any(not isinstance(g,str) or not re.fullmatch('[A-Za-z0-9@_.:/-]{1,128}',g) for g in groups):
        raise ValueError('Verified operator IdP groups required; no frontend role-header mapping')
    project={'apiVersion':'argoproj.io/v1alpha1','kind':'AppProject','metadata':{'name':'cloudforge-platform','namespace':namespace},'spec':{
        'sourceRepos':[url], 'destinations':[{'server':'https://kubernetes.default.svc','namespace':'cloudforge'}],
        'clusterResourceWhitelist':[],
        'namespaceResourceWhitelist':[{'group':group,'kind':kind} for group,kind in [
            ('','Service'),('','ServiceAccount'),('','ConfigMap'),('','PersistentVolumeClaim'),
            ('apps','Deployment'),('autoscaling','HorizontalPodAutoscaler'),('policy','PodDisruptionBudget'),
            ('batch','Job'),('batch','CronJob'),('networking.k8s.io','NetworkPolicy'),
            ('external-secrets.io','SecretStore'),('external-secrets.io','ExternalSecret')]],
        'roles':[{'name':'operator','groups':groups,'description':'Explicit trusted IdP deployment operators',
                  'policies':['p, proj:cloudforge-platform:operator, applications, get, cloudforge-platform/*, allow',
                              'p, proj:cloudforge-platform:operator, applications, sync, cloudforge-platform/*, allow']}],
    }}
    application={'apiVersion':'argoproj.io/v1alpha1','kind':'Application','metadata':{'name':'cloudforge-platform','namespace':namespace},'spec':{
        'project':'cloudforge-platform','source':{'repoURL':url,'targetRevision':revision,'path':path},
        'destination':{'server':'https://kubernetes.default.svc','namespace':'cloudforge'},
        'syncPolicy':{'automated':{'prune':False,'selfHeal':True,'allowEmpty':False},
                      'syncOptions':['RespectIgnoreDifferences=true'],
                      'retry':{'limit':3,'backoff':{'duration':'5s','factor':2,'maxDuration':'1m'}}},
        'ignoreDifferences':[{'group':'apps','kind':'Deployment','jsonPointers':['/spec/replicas']}],
    }}
    return [project,application]

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--config',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    docs=prepare(json.loads(args.config.read_text()))
    with args.output.open('x') as stream:yaml.safe_dump_all(docs,stream,sort_keys=False)
