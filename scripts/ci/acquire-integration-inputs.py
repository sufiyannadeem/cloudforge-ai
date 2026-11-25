#!/usr/bin/env python3
"""Reviewed CI-only acquisition; no floating checksums, archive links or local execution."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import urllib.parse
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[2]
TOOLS={'prometheus':'promtool','kubeconform':'kubeconform','helm':'helm','kubectl':'kubectl','terraform':'terraform','go':'go','actionlint':'actionlint'}
EXPECTED={'prometheus':'3.5.0','kubeconform':'0.6.7','helm':'3.20.0','kubectl':'1.35.0','terraform':'1.17.2','go':'1.26.11','actionlint':'1.7.12'}
GROUPS={'native':('prometheus','kubeconform','helm','kubectl','terraform','actionlint'),'postgres':('go',)}
HOSTS={'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com','get.helm.sh',
       'dl.k8s.io','cdn.dl.k8s.io','releases.hashicorp.com','go.dev','dl.google.com',
       'raw.githubusercontent.com','huggingface.co','www.apache.org','cas-bridge.xethub.hf.co',
       'cdn-lfs.huggingface.co','cdn-lfs-us-1.huggingface.co','us.aws.cdn.hf.co'}


def digest(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value) or value=='0'*64:
        raise ValueError('Independent reviewed SHA256 required')
    return value


def load(path,semantic=False):
    approved=ROOT/'ci/integration-acquisition.json'
    if Path(path).absolute()!=approved or approved.is_symlink():
        raise ValueError('Only the checked-in acquisition lock is allowed')
    raw=approved.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest(os.environ['CI_ACQUISITION_LOCK_SHA256']):
        raise ValueError('Acquisition lock differs from environment-approved digest')
    lock=json.loads(raw)
    if (lock.get('schema_version')!=1 or lock.get('status')!='VERIFIED_INPUTS_PENDING_HUMAN_APPROVAL'
        or lock.get('reviewed_by') is not None or lock.get('platform')!='linux-amd64'):
        raise ValueError('Expected verified inputs with no fabricated human attestation')
    if os.getenv('CI_ACQUISITION_APPROVED')!='true':
        raise ValueError('Protected-environment human acquisition approval is still pending')
    if not re.fullmatch(r'postgres:16(?:\.[0-9]+)?(?:-[a-z0-9.-]+)?@sha256:[a-f0-9]{64}',lock.get('postgres_image') or ''):
        raise ValueError('Review an official PostgreSQL 16 image digest')
    digest(lock['postgres_image'].split('@sha256:')[1])
    for name in ('native','postgres'):
        for key in GROUPS[name]:
            item=lock['artifacts'][key];validate(item)
            if key in EXPECTED and item['version']!=EXPECTED[key]:raise ValueError('Unexpected tool version')
    provider=lock['terraform_provider']
    if provider['name']!='registry.terraform.io/hashicorp/aws' or provider['version']!='6.66.0':
        raise ValueError('Unexpected provider dependency')
    digest(provider['linux_amd64_sha256'])
    for relative in ('infrastructure/terraform/bootstrap/.terraform.lock.hcl','infrastructure/terraform/environments/dev/.terraform.lock.hcl'):
        content=(ROOT/relative).read_text()
        if 'zh:'+provider['linux_amd64_sha256'] not in content or not re.search(r'version\s*=\s*"6\.66\.0"',content):
            raise ValueError('Provider lock differs from verified upstream package')
    schemas=lock['schemas']
    digest(schemas['bundle_manifest_sha256'])
    if (schemas.get('kubernetes_version')!='1.35.0' or schemas.get('mode')!='deterministic-official-sources-v1'
        or schemas.get('schema_location')!='{{.ResourceKind}}-{{.Group}}-{{.ResourceAPIVersion}}.json'):
        raise ValueError('Unsupported schema source plan')
    if not all(re.fullmatch(r'v?[0-9]+\.[0-9]+\.[0-9]+',schemas[key]) for key in ('rollouts_version','csi_version')):
        raise ValueError('Pin exact CRD releases')
    for source in schemas['sources']:
        digest(source['sha256'])
        if 'url' in source:validate(source)
        elif source.get('path')!='deploy/controllers/lbc-crds.yaml':raise ValueError('Unapproved local schema source')
        if source['kind'] not in {'openapi','crd'}:raise ValueError('Unknown schema source kind')
    if semantic:
        config=lock['semantic'];prep=config['preparation']
        if prep['revision']!='1110a243fdf4706b3f48f1d95db1a4f5529b4d41':raise ValueError('Unpinned sentence model')
        for item in prep['files'].values():validate(item)
        digest(prep['bootstrap_lock_sha256']);digest(prep['corpus_source_sha256'])
        if not re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}',config.get('glibc_base') or ''):
            raise ValueError('Pinned glibc base required')
        if not 0<int(config['max_rss_mib'])<=1024 or not 0<float(config['max_p95_ms'])<=8000:
            raise ValueError('Reviewed resource policy bounds required')
    return lock


def validate(item):
    digest(item['sha256']); url(item['url'])
    if not item.get('version') or item['format'] not in {'tar.gz','zip','binary'} or not 0<int(item['limit_mib'])<=300:
        raise ValueError('Invalid pinned artifact')


def url(value):
    if not isinstance(value,str) or any(ord(c)<33 or c=='\\' for c in value):
        raise ValueError('Invalid artifact URL characters')
    parsed=urllib.parse.urlsplit(value)
    if (parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password
        or parsed.port not in (None,443) or parsed.fragment or parsed.query):raise ValueError('Artifact URL not allowlisted')
    # Rebuild the authority from a literal allowlist, never the file-supplied URL.
    host=next(host for host in HOSTS if host==parsed.hostname)
    return urllib.parse.urlunsplit(('https',host,parsed.path,'',''))


class ReviewedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        # GitHub assets use signed redirect queries; never log URLs or send auth headers.
        if any(ord(c)<33 or c=='\\' for c in newurl):raise ValueError('Invalid redirect characters')
        p=urllib.parse.urlsplit(newurl)
        if p.scheme!='https' or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,443):
            raise ValueError('Artifact redirect not allowlisted')
        host=next(host for host in HOSTS if host==p.hostname)
        reviewed=urllib.parse.urlunsplit(('https',host,p.path,p.query,''))
        return super().redirect_request(request,fp,code,msg,headers,reviewed)


def fetch(item,target):
    validate(item)
    source_url=url(item['url'])
    sha=hashlib.sha256();count=0;limit=int(item['limit_mib'])*1024*1024
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),ReviewedRedirect())
    with opener.open(source_url,timeout=30) as response,target.open('xb') as output:
        while True:
            chunk=response.read(1024*1024)
            if not chunk:break
            count+=len(chunk)
            if count>limit:raise ValueError('Artifact byte budget exceeded')
            output.write(chunk);sha.update(chunk)
    if sha.hexdigest()!=item['sha256']:raise ValueError('Artifact checksum mismatch')


def unpack(archive,dest,kind):
    dest.mkdir(exist_ok=False)
    def checked(name,size):
        path=dest/name
        if Path(name).is_absolute() or '..' in Path(name).parts or not path.resolve().is_relative_to(dest.resolve()):
            raise ValueError('Archive path escape')
        if size<0 or size>300*1024*1024:raise ValueError('Archive member budget exceeded')
        return path
    expanded=0
    if kind=='tar.gz':
        with tarfile.open(archive,'r:gz') as stream:
            for member in stream:
                if not (member.isfile() or member.isdir()):raise ValueError('Archive links/devices are forbidden')
                path=checked(member.name,member.size);expanded+=member.size
                if expanded>1024*1024*1024:raise ValueError('Archive expansion budget exceeded')
                if member.isdir():path.mkdir(parents=True,exist_ok=True)
                else:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with stream.extractfile(member) as source,path.open('xb') as output:shutil.copyfileobj(source,output)
    elif kind=='zip':
        with zipfile.ZipFile(archive) as stream:
            for member in stream.infolist():
                if stat.S_ISLNK(member.external_attr>>16):raise ValueError('ZIP links forbidden')
                path=checked(member.filename,member.file_size);expanded+=member.file_size
                if expanded>1024*1024*1024:raise ValueError('Archive expansion budget exceeded')
                if member.is_dir():path.mkdir(parents=True,exist_ok=True)
                else:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with stream.open(member) as source,path.open('xb') as output:shutil.copyfileobj(source,output)
    else:shutil.copyfile(archive,dest/'kubectl')


def schema_children(value):
    for key in ('properties','patternProperties','definitions','$defs'):
        if isinstance(value.get(key),dict):yield from value[key].values()
    for key in ('items','additionalProperties','additionalItems','not','contains','propertyNames'):
        child=value.get(key)
        if isinstance(child,dict):yield child
        elif isinstance(child,list):yield from child
    for key in ('allOf','anyOf','oneOf'):
        yield from value.get(key,[])


def strict_schema(value):
    if not isinstance(value,dict):return value
    result=copy.deepcopy(value)
    for key in ('properties','patternProperties','definitions','$defs'):
        if isinstance(result.get(key),dict):result[key]={name:strict_schema(child) for name,child in result[key].items()}
    for key in ('items','additionalProperties','additionalItems','not','contains','propertyNames'):
        if isinstance(result.get(key),dict):result[key]=strict_schema(result[key])
        elif isinstance(result.get(key),list):result[key]=[strict_schema(v) for v in result[key]]
    for key in ('allOf','anyOf','oneOf'):
        if key in result:result[key]=[strict_schema(v) for v in result[key]]
    if result.pop('nullable',False) and isinstance(result.get('type'),str):result['type']=[result['type'],'null']
    if result.get('x-kubernetes-int-or-string'):
        result.pop('type',None);result['anyOf']=[{'type':'integer'},{'type':'string'}]
    if result.get('properties') and not result.get('x-kubernetes-preserve-unknown-fields'):
        result.setdefault('additionalProperties',False)
    return result


def standalone(schema,definitions):
    needed={}
    def refs(value):
        if not isinstance(value,dict):return
        ref=value.get('$ref')
        if ref:
            if not isinstance(ref,str) or not ref.startswith('#/definitions/'):
                raise ValueError('External/unsupported schema reference')
            key=ref.removeprefix('#/definitions/')
            if key not in needed:
                needed[key]=copy.deepcopy(definitions[key])
                refs(needed[key])
        for child in schema_children(value):refs(child)
    result=copy.deepcopy(schema);refs(result)
    if needed:result['definitions']=needed
    result['$schema']='http://json-schema.org/draft-07/schema#'
    return strict_schema(result)


def build_schemas(lock,folder,source_bytes=None):
    """Deterministic closure/strictness over official pinned schemas; no mock schemas."""
    import yaml
    folder.mkdir(exist_ok=False)
    sources=[]
    for record in lock['schemas']['sources']:
        if source_bytes is not None:raw=source_bytes[record['name']]
        elif 'path' in record:raw=(ROOT/record['path']).read_bytes()
        else:
            temp=folder/(record['name']+'.source');fetch(record,temp);raw=temp.read_bytes();temp.unlink()
        if hashlib.sha256(raw).hexdigest()!=record['sha256']:raise ValueError('Schema source integrity failure')
        sources.append((record,raw))
    openapi=[json.loads(raw) for record,raw in sources if record['kind']=='openapi']
    if len(openapi)!=1:raise ValueError('Exactly one official OpenAPI source required')
    definitions=openapi[0]['definitions'];files={}
    def emit(kind,group,version,schema):
        # kubeconform 0.6.7 uses literal local paths (not file://); Group is v1 for core.
        name=kind.lower()+'-'+(group or version)+'-'+version+'.json'
        if not re.fullmatch('[a-z0-9_.-]+',name):raise ValueError('Invalid schema identity')
        schema=copy.deepcopy(schema)
        properties=schema.setdefault('properties',{})
        properties['apiVersion']={'type':'string','enum':[group+'/'+version if group else version]}
        properties['kind']={'type':'string','enum':[kind]}
        schema['required']=sorted(set(schema.get('required',[]))|{'apiVersion','kind'})
        payload=(json.dumps(standalone(schema,definitions),sort_keys=True,separators=(',',':'))+'\n').encode()
        digest_value=hashlib.sha256(payload).hexdigest()
        if name in files and files[name]!=digest_value:raise ValueError('Ambiguous schema GVK')
        (folder/name).write_bytes(payload);files[name]=digest_value
    for schema in definitions.values():
        for gvk in schema.get('x-kubernetes-group-version-kind',[]):
            emit(gvk['kind'],gvk['group'],gvk['version'],schema)
    for record,raw in sources:
        if record['kind']!='crd':continue
        for crd in yaml.safe_load_all(raw):
            if not crd or crd.get('kind')!='CustomResourceDefinition':continue
            spec=crd['spec']
            for version in spec['versions']:
                if not version.get('served'):continue
                schema=copy.deepcopy(version['schema']['openAPIV3Schema'])
                schema.setdefault('properties',{})['metadata']={'$ref':'#/definitions/io.k8s.apimachinery.pkg.apis.meta.v1.ObjectMeta'}
                emit(spec['names']['kind'],spec['group'],version['name'],schema)
    metadata={key:lock['schemas'][key] for key in ('kubernetes_version','rollouts_version','csi_version')}
    metadata.update(generator='deterministic-official-sources-v1',sources={r['name']:r['sha256'] for r,_ in sources},files=files)
    (folder/'bundle.json').write_text(json.dumps(metadata,sort_keys=True,indent=2)+'\n')
    expected=lock['schemas'].get('bundle_manifest_sha256')
    if expected and hashlib.sha256((folder/'bundle.json').read_bytes()).hexdigest()!=expected:
        raise ValueError('Deterministic schema bundle differs from verified source derivation')
    print('Generated',len(files),'strict standalone schemas from verified official inputs')


def acquire(lock,group,dest):
    dest.mkdir(parents=True,exist_ok=False);bin_dir=dest/'bin';bin_dir.mkdir()
    records=lock['artifacts']
    for key in GROUPS[group]:
        item=records[key]; archive=dest/(key+'.download');fetch(item,archive)
        folder=dest/key;unpack(archive,folder,item['format']);archive.unlink()
        print('Verified',key,item['version'],'sha256='+item['sha256'])
        if key in TOOLS:
            if key=='go':
                candidates=list(folder.glob('go/bin/go'))
                if len(candidates)!=1:raise ValueError('Go layout mismatch')
                # Go invokes sibling compile/link tools; preserve and make its verified tree executable.
                for path in (folder/'go').rglob('*'):
                    if path.is_file() and (path.parent.name=='bin' or 'pkg/tool' in str(path)):path.chmod(0o755)
                (bin_dir/'go').symlink_to(candidates[0])
            else:
                matches=[p for p in folder.rglob(TOOLS[key]) if p.is_file()]
                if len(matches)!=1:raise ValueError('Tool archive layout mismatch')
                matches[0].chmod(0o755);(bin_dir/TOOLS[key]).symlink_to(matches[0])
    if group=='native':build_schemas(lock,dest/'schemas')
    if group in {'native','postgres'}:
        commands={'prometheus':['promtool','--version'],'kubeconform':['kubeconform','-v'],
                  'helm':['helm','version','--short'],'kubectl':['kubectl','version','--client','-o','json'],
                  'terraform':['terraform','version','-json'],'go':['go','version'],'actionlint':['actionlint','-version']}
        for key in GROUPS[group]:
            if key not in commands:continue
            command=commands[key];command=[str(bin_dir/command[0]),*command[1:]]
            result=subprocess.run(command,capture_output=True,text=True,timeout=20,check=True)
            if not re.search(r'(?<![0-9.])'+re.escape(EXPECTED[key])+r'(?![0-9.])',result.stdout+result.stderr):
                raise ValueError('Binary version differs from reviewed pin')
    with Path(os.environ['GITHUB_PATH']).open('a') as stream:stream.write(str(bin_dir)+'\n')
    env={}
    if group=='postgres':env['GOROOT']=str(dest/'go/go')
    if group=='native':env['KUBERNETES_SCHEMA_LOCATION']=str(dest/'schemas'/lock['schemas']['schema_location'])
    with Path(os.environ['GITHUB_ENV']).open('a') as stream:
        for key,value in env.items():
            if '\n' in value or '\r' in value:raise ValueError('Invalid environment value')
            stream.write(key+'='+value+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['plan','native','postgres'])
    parser.add_argument('--output',type=Path);args=parser.parse_args()
    if os.getenv('GITHUB_ACTIONS')!='true' or os.getenv('RUNNER_ENVIRONMENT')!='github-hosted':parser.exit(2,'CI-only acquisition; local execution forbidden\n')
    lock=load(ROOT/'ci/integration-acquisition.json')
    if args.mode=='plan':
        with Path(os.environ['GITHUB_OUTPUT']).open('a') as stream:stream.write('postgres_image='+lock['postgres_image']+'\n')
    else:
        if not args.output:parser.error('New output directory required')
        acquire(lock,args.mode,args.output.resolve())
