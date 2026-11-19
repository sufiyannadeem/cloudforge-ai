#!/usr/bin/env python3
"""Validate exact scanned image artifacts; publish only from a protected manual main run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SERVICES = {'project-service','infrastructure-service','deployment-service','aiops-service','finops-service','frontend','postgres'}
DIGEST = re.compile(r'[a-z0-9][a-z0-9.:/_-]*@sha256:[0-9a-f]{64}')


def verify_release_environment(environment):
    """A named environment alone does not establish independent approval."""
    policy = environment.get('deployment_branch_policy') or {}
    reviews = [rule for rule in environment.get('protection_rules', [])
               if rule.get('type') == 'required_reviewers']
    if (environment.get('name') != 'release' or policy.get('protected_branches') is not True
            or policy.get('custom_branch_policies') is not False or len(reviews) != 1
            or reviews[0].get('prevent_self_review') is not True
            or not reviews[0].get('reviewers')):
        raise ValueError('Release requires protected branches and independent environment reviewers')


def artifacts(root, revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision): raise ValueError('Expected exact Git revision')
    result = []
    for service in sorted(SERVICES):
        folder = root / ('image-' + service)
        meta = json.loads((folder/'metadata.json').read_text())
        archive = folder/'image.tar'
        if archive.is_symlink() or folder.is_symlink(): raise ValueError('Symlink artifact forbidden')
        with archive.open('rb') as stream: checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if (meta['service'] != service or meta['revision'] != revision or meta['archive_sha256'] != checksum
                or meta['local_image'] != 'cloudforge-' + service + ':release'
                or not re.fullmatch(r'sha256:[0-9a-f]{64}',meta['image_id'])):
            raise ValueError('Artifact binding mismatch')
        result.append((archive,meta))
    return result


def select_images(config, manifest):
    if set(manifest['images']) != SERVICES or not re.fullmatch(r'[0-9a-f]{40}',manifest['revision']):
        raise ValueError('Incomplete release image manifest')
    if any(not isinstance(value,str) or not DIGEST.fullmatch(value) for value in manifest['images'].values()):
        raise ValueError('Registry digest references required; tags/local IDs forbidden')
    config['images'] = {name:manifest['images'][name] for name in sorted(SERVICES-{'postgres'})}
    config['database_client_image'] = manifest['images']['postgres']
    return config


def publish(root, revision, output):
    if (os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or os.getenv('GITHUB_REF') != 'refs/heads/main' or os.getenv('RELEASE_PUBLISH_APPROVED') != 'true'):
        raise ValueError('Publishing requires the protected manual main release job')
    repository = os.environ['GITHUB_REPOSITORY'].lower()
    if not re.fullmatch(r'[a-z0-9_.-]+/[a-z0-9_.-]+',repository): raise ValueError('Invalid repository')
    checked = artifacts(root,revision)  # Validate ALL artifacts before any push.
    images = {}
    def docker(*args): return subprocess.check_output(['docker',*args],stderr=subprocess.DEVNULL,text=True).strip()
    for archive, meta in checked:
        docker('load','--input',str(archive))
        if docker('image','inspect',meta['local_image'],'--format','{{.Id}}') != meta['image_id']:
            raise ValueError('Loaded image differs from scanned image')
        repo = 'ghcr.io/' + repository + '/' + meta['service']
        tag = repo + ':' + revision
        docker('tag',meta['image_id'],tag)
        docker('push',tag)
        refs = json.loads(docker('image','inspect',tag,'--format','{{json .RepoDigests}}'))
        matches = [ref for ref in refs if ref.startswith(repo+'@') and DIGEST.fullmatch(ref)]
        if len(matches)!=1: raise ValueError('Published registry digest unavailable')
        images[meta['service']] = matches[0]
    output.write_text(json.dumps({'revision':revision,'images':images},indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Refusing to overwrite an existing output')
    if args.publish: publish(args.artifacts,args.revision,args.output)
    else:
        config=select_images(json.loads(args.config.read_text()),json.loads(args.manifest.read_text()))
        args.output.write_text(json.dumps(config,indent=2)+'\n')
