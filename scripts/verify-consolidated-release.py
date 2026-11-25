#!/usr/bin/env python3
"""Cached/offline release checks. Missing prerequisites BLOCK, skipped tests never PASS."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import yaml

ROOT=Path(__file__).resolve().parents[1]


def run(command,cwd=ROOT,env=None,timeout=120):
    result=subprocess.run([str(v) for v in command],cwd=cwd,env=env,capture_output=True,text=True,timeout=timeout)
    if result.returncode:raise RuntimeError((result.stdout+result.stderr)[-4000:])
    return result.stdout


def native():
    rows=[]; rendered=[]
    def check(name,command,work):
        try:work();rows.append(dict(gate=name,status='PASS',command=command))
        except FileNotFoundError as error:rows.append(dict(gate=name,status='BLOCKED',command=command,reason=str(error)))
        except (RuntimeError,ValueError,subprocess.SubprocessError) as error:rows.append(dict(gate=name,status='FAIL',command=command,reason=str(error)))
    chart=ROOT/'deploy/controllers/charts/aws-load-balancer-controller'
    values=ROOT/'deploy/controllers/lbc-values.yml'
    flags=['-f',values,'--set','clusterName=offline-fixture','--set','region=eu-west-1','--set','vpcId=vpc-00000000000000000']
    def helm():
        run(['helm','lint',chart,*flags])
        output=run(['helm','template','cloudforge-lbc',chart,*flags])
        rendered.append(output)
        docs=[d for d in yaml.safe_load_all(output) if d]
        if not any(d['kind']=='Deployment' for d in docs):raise ValueError('Controller Deployment missing')
    check('native_helm','helm lint/template <vendored chart> -f deploy/controllers/lbc-values.yml --set clusterName=offline-fixture --set region=eu-west-1 --set vpcId=vpc-00000000000000000',helm)
    def kustomize():
        with tempfile.TemporaryDirectory(prefix='cloudforge-offline-kustomize-') as temp:
            folder=Path(temp)
            sources={'base.yml':'deploy/kubernetes/cloudforge-secrets-example.yml',
                     'services.yml':'deploy/kubernetes/services.yml',
                     'worker.yml':'deploy/kubernetes/inference/workload.yaml',
                     'providers.yml':'deploy/kubernetes/inference/secret-providers.yaml',
                     'aiops-patch.yml':'deploy/kubernetes/inference/aiops-patch.yaml'}
            for name,source in sources.items():shutil.copyfile(ROOT/source,folder/name)
            (folder/'kustomization.yaml').write_text(yaml.safe_dump(dict(apiVersion='kustomize.config.k8s.io/v1beta1',kind='Kustomization',
                resources=['base.yml','services.yml','worker.yml','providers.yml'],patches=[{'path':'aiops-patch.yml'}])))
            output=run(['kubectl','kustomize',folder]);rendered.append(output)
            docs=[d for d in yaml.safe_load_all(output) if d]
            aiops=next(d for d in docs if d['kind']=='Deployment' and d['metadata']['name']=='aiops-service')
            containers=aiops['spec']['template']['spec']['containers']
            if len(containers)!=1 or containers[0]['name']!='aiops-service':raise ValueError('AIOps patch did not match exact container')
            env={v['name']:v.get('value') for v in containers[0]['env']}
            if env.get('AI_PROVIDER')!='gemini':raise ValueError('Inference integration patch not applied')
    check('native_kustomize','kubectl kustomize <isolated base+services+inference+strategic-patch directory>',kustomize)
    def prometheus():
        tool=os.getenv('PROMTOOL') or shutil.which('promtool')
        if not tool:raise FileNotFoundError('Cached promtool unavailable; no download/container fallback')
        run([tool,'check','config','--syntax-only',ROOT/'monitoring/prometheus/prometheus.yml'])
        rules=sorted((ROOT/'monitoring/prometheus/rules').glob('*.yml'))
        run([tool,'check','rules',*rules])
        for fixture in sorted((ROOT/'monitoring/prometheus').rglob('*.test.yml')):
            run([tool,'test','rules',fixture.name],cwd=fixture.parent)
    check('native_prometheus','promtool check config --syntax-only monitoring/prometheus/prometheus.yml; promtool check rules monitoring/prometheus/rules/*.yml; promtool test rules <each *.test.yml in its directory>',prometheus)
    def schemas():
        tool=os.getenv('KUBECONFORM') or shutil.which('kubeconform')
        location=os.getenv('KUBERNETES_SCHEMA_LOCATION','')
        if not tool or not location.startswith('/'):
            raise FileNotFoundError('Cached kubeconform and approved offline Kubernetes 1.35/Rollouts/CSI schema bundle required')
        if len(rendered)!=2:raise ValueError('Both native renders must pass before schema validation')
        examples=['deploy/kubernetes/rollout-analysis-template.example.yml',
                  'deploy/kubernetes/project-rollout-rbac-example.yml',
                  'deploy/kubernetes/project-deployment-rbac-example.yml']
        with tempfile.TemporaryDirectory(prefix='cloudforge-schema-check-') as temp:
            path=Path(temp)/'rendered.yaml'
            path.write_text('\n---\n'.join(rendered+[(ROOT/p).read_text() for p in examples]))
            run([tool,'-strict','-summary','-kubernetes-version','1.35.0','-schema-location',location,path])
    check('kubernetes_crd_schema','kubeconform -strict -summary -kubernetes-version 1.35.0 -schema-location <approved absolute local schema bundle template> <native renders and Rollouts/RBAC manifests>',schemas)
    return rows


def postgres():
    required=('AI_TEST_POSTGRES_DSN','REMEDIATION_TEST_DATABASE_URL','RELEASE_TEST_POSTGRES_DSN')
    missing=[name for name in required if not os.getenv(name)]
    if missing:return [dict(gate='real_postgresql',status='BLOCKED',reason='Explicit isolated test database inputs missing: '+','.join(missing),command='AI_TEST_POSTGRES_DSN=<isolated cloudforge_inference_test> REMEDIATION_TEST_DATABASE_URL=<isolated cloudforge_remediation_test> RELEASE_TEST_POSTGRES_DSN=<isolated cloudforge_release_test> RELEASE_TEST_ALLOW_SCHEMA_RESET=yes-disposable-public <python> scripts/verify-consolidated-release.py postgres')]
    # Each test independently verifies local hostname, exact database name and emptiness.
    with tempfile.TemporaryDirectory(prefix='cloudforge-pg-gate-') as temp:
        report=Path(temp)/'postgres.xml'
        pytest_env=dict(os.environ,PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
        pytest_env.pop('PYTEST_ADDOPTS',None)
        run([sys.executable,'-m','pytest','app/test_postgres_inference.py','app/test_release_postgres.py','-q','--junitxml='+str(report)],cwd=ROOT/'services/aiops-service',env=pytest_env,timeout=120)
        suites=ET.parse(report).getroot()
        cases=list(suites.iter('testsuite'))
        if sum(int(s.get('tests','0')) for s in cases)!=8 or any(int(s.get('skipped','0')) or int(s.get('failures','0')) or int(s.get('errors','0')) for s in cases):
            raise ValueError('All eight real database cases must pass without skips or filtering')
    env=dict(os.environ,GOPROXY='off',GOTOOLCHAIN='local')
    output=run([os.getenv('GO','go'),'test','-tags','integration','./internal/repository','-run','TestClaimRemediationApproval','-v','-count=1','-timeout=90s'],cwd=ROOT/'services/deployment-service',env=env,timeout=100)
    if 'SKIP' in output or '--- PASS: TestClaimRemediationApproval' not in output:
        raise ValueError('Required atomic dispatch case did not pass')
    return [dict(gate='real_postgresql',status='PASS',reason='Real migrations/ACL/store/ledger/import tests and native Go dispatch passed without skips')]


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('gate',choices=['native','postgres']);parser.add_argument('--output',type=Path);a=parser.parse_args()
    try:rows=native() if a.gate=='native' else postgres()
    except (OSError,RuntimeError,ValueError,subprocess.SubprocessError) as error:rows=[dict(gate=a.gate,status='FAIL',reason=str(error))]
    output=json.dumps({'release_ready':False,'checks':rows},indent=2)
    if a.output:a.output.write_text(output+'\n')
    print(output)
    sys.exit(1 if any(r['status']=='FAIL' for r in rows) else 2 if any(r['status']=='BLOCKED' for r in rows) else 0)
