#!/usr/bin/env python3
"""Offline source inventory/candidate gate. Never signs, publishes or calls AWS."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess

ROOT=Path(__file__).resolve().parents[1]
RELEASE=runpy.run_path(str(ROOT/'scripts/release-images.py'))
HISTORY=ROOT/'deploy/security/retired-release-denylist.json'
EXCLUDED_PREFIXES=('deploy/evidence/', 'deploy/preflight-')

def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,env=dict(os.environ,GIT_OPTIONAL_LOCKS='0'))

def inventory():
    paths=sorted(set(git('ls-files','-z','--cached','--others','--exclude-standard').decode().split('\0'))-{''})
    files=[]
    for path in paths:
        if path.startswith(EXCLUDED_PREFIXES):continue # Generated review evidence, excluded to avoid self-hashing.
        source=ROOT/path
        if source.is_symlink():
            value=os.readlink(source).encode();mode='symlink'
        elif source.is_file():
            value=source.read_bytes();mode='executable' if source.stat().st_mode&0o111 else 'regular'
        else:
            files.append({'path':path,'mode':'missing','sha256':None});continue
        files.append({'path':path,'mode':mode,'sha256':hashlib.sha256(value).hexdigest()})
    digest=hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    status=git('status','--porcelain=v1','-z','--untracked-files=all').decode().split('\0')
    return {'head':git('rev-parse','HEAD').decode().strip(),'clean':not any(status),'status_entries':[v for v in status if v],
            'snapshot_sha256':digest,'excluded_generated_evidence':list(EXCLUDED_PREFIXES),'files':files,
            'release_ready':False,'reason':'A content snapshot is not a clean approved main commit or a signed release'}

def validate_candidate(policy,manifest):
    """Only structural/source freshness checks. Cosign verification remains mandatory."""
    revision=policy.get('approved_revision')
    history=json.loads(HISTORY.read_text())
    if history.get('purpose') != 'DENY_ONLY_NOT_CURRENT_RELEASE':
        raise ValueError('Retired release policy must be deny-only')
    if not isinstance(revision,str) or not re.fullmatch(r'[0-9a-f]{40}',revision) or revision==history['revision']:
        raise ValueError('Bind a new independently approved current-source revision; historical HEAD is stale')
    if policy.get('repository')!='sufiyannadeem/cloudforge-ai':raise ValueError('Unexpected repository')
    for key in ('run_id','run_attempt'):
        if not isinstance(policy.get(key),str) or not re.fullmatch(r'[1-9][0-9]*',policy[key]):raise ValueError('Bind exact hosted run and attempt')
    if (manifest.get('revision')!=revision or any(manifest.get(k)!=policy[k] for k in ('run_id','run_attempt'))):
        raise ValueError('Manifest does not match approved source/run')
    RELEASE['select_images']({},manifest)
    stale={value.split('@')[1] for value in history['images'].values()}
    for service,image in manifest['images'].items():
        repository,digest=image.split('@')
        if repository!=f"ghcr.io/{policy['repository']}/{service}" or digest in stale:
            raise ValueError('Wrong repository or stale historical registry digest')
    if set(manifest.get('provenance',{}))!=RELEASE['SERVICES']:raise ValueError('Seven scanned-image artifact bindings required')
    for service,meta in manifest['provenance'].items():
        if set(meta)!={'image_id','archive_sha256','sbom_sha256'}:raise ValueError('Unexpected scanned-image evidence')
        RELEASE['provenance']({'service':service,**meta},policy['repository'],revision,policy['run_id'],policy['run_attempt'])
    return {'structural_freshness':'PASS','cryptographic_verification':'REQUIRED separately; not performed offline',
            'deployment_verdict':'NO-GO until all independent deployment gates pass'}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--inventory',action='store_true')
    parser.add_argument('--policy',type=RELEASE['read_review_json']);parser.add_argument('--manifest',type=RELEASE['read_review_json']);a=parser.parse_args()
    try:
        snapshot=inventory()
        if a.inventory:print(json.dumps(snapshot,indent=2))
        else:
            if not a.policy or not a.manifest:raise ValueError('Policy and manifest required')
            policy=a.policy;manifest=a.manifest
            result=validate_candidate(policy,manifest)
            if not snapshot['clean'] or snapshot['head']!=policy['approved_revision'] or git('branch','--show-current').decode().strip()!='main':
                raise ValueError('Candidate verification requires clean independently approved main source')
            if snapshot['snapshot_sha256']!=policy.get('source_snapshot_sha256'):raise ValueError('Approved source content changed')
            print(json.dumps(result,indent=2))
    except (OSError,ValueError,TypeError,KeyError) as error:parser.exit(2,'NO-GO: '+str(error)+'\n')
