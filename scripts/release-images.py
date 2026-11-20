#!/usr/bin/env python3
"""Validate exact scanned image artifacts; publish only from a protected manual main run."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

SERVICES = {'project-service','infrastructure-service','deployment-service','aiops-service','finops-service','frontend','postgres'}
DIGEST = re.compile(r'[a-z0-9][a-z0-9.:/_-]*@sha256:[0-9a-f]{64}')
PREDICATE = 'https://github.com/sufiyannadeem/cloudforge-ai/attestations/scanned-image-release/v1'
ISSUER = 'https://token.actions.githubusercontent.com'


def workflow_identity(repository):
    if not re.fullmatch(r'[a-z0-9_.-]+/[a-z0-9_.-]+', repository):
        raise ValueError('Invalid trusted repository')
    return f'https://github.com/{repository}/.github/workflows/release-images.yml@refs/heads/main'


def provenance(meta, repository, revision, run_id, run_attempt):
    if (not re.fullmatch(r'[0-9a-f]{40}', revision) or not re.fullmatch(r'[1-9][0-9]*', run_id)
            or not re.fullmatch(r'[1-9][0-9]*', run_attempt)):
        raise ValueError('Exact revision and hosted run/attempt required')
    artifact = {key: meta[key] for key in ['image_id','archive_sha256','sbom_sha256']}
    if (not re.fullmatch(r'sha256:[0-9a-f]{64}', artifact['image_id'])
            or any(not re.fullmatch(r'[0-9a-f]{64}', artifact[key]) for key in ['archive_sha256','sbom_sha256'])):
        raise ValueError('Invalid artifact evidence')
    return {'service':meta['service'], 'source':{'repository':repository,'revision':revision},
            'workflow':{'identity':workflow_identity(repository),'run_id':run_id,'run_attempt':run_attempt},
            'artifact':artifact}


def run(*args):
    return subprocess.check_output(list(args), stderr=subprocess.DEVNULL, text=True, timeout=180).strip()


def verify_manifest(manifest, repository, revision, run_id, run_attempt):
    """Verify registry signatures, then only inspect cryptographically verified claims.

    Expected repository/revision/run come from operator policy, never the manifest.
    No offline/insecure/log-skipping flags are permitted on this production path.
    """
    select_images({}, manifest)
    if (manifest['revision'] != revision or manifest.get('run_id') != run_id
            or manifest.get('run_attempt') != run_attempt or set(manifest.get('provenance', {})) != SERVICES):
        raise ValueError('Release invocation mismatch')
    identity = workflow_identity(repository)
    options = ['--certificate-identity',identity,'--certificate-oidc-issuer',ISSUER,
               '--certificate-github-workflow-sha',revision,
               '--certificate-github-workflow-repository',repository,
               '--certificate-github-workflow-ref','refs/heads/main',
               '--certificate-github-workflow-trigger','workflow_dispatch']
    for service in sorted(SERVICES):
        image = manifest['images'][service]
        name, digest = image.split('@sha256:')
        if name != f'ghcr.io/{repository}/{service}':
            raise ValueError('Image is outside the trusted repository')
        evidence = manifest['provenance'][service]
        if set(evidence) != {'image_id','archive_sha256','sbom_sha256'}:
            raise ValueError('Unexpected provenance fields')
        expected = provenance({'service':service, **evidence},repository,revision,run_id,run_attempt)
        run('cosign','verify',*options,image)
        # Cosign emits a JSON stream of DSSE envelopes, not necessarily an array.
        remaining = run('cosign','verify-attestation',*options,'--type',PREDICATE,image).strip()
        envelopes = []
        while remaining:
            value, end = json.JSONDecoder().raw_decode(remaining)
            envelopes.extend(value if isinstance(value,list) else [value])
            remaining = remaining[end:].lstrip()
        matched = False
        for envelope in envelopes:
            statement = json.loads(base64.b64decode(envelope['payload'],validate=True))
            if (statement.get('_type') in ['https://in-toto.io/Statement/v1','https://in-toto.io/Statement/v0.1']
                    and statement.get('predicateType') == PREDICATE and statement.get('predicate') == expected
                    and statement.get('subject') == [{'name':name,'digest':{'sha256':digest}}]):
                matched = True
        if not matched: raise ValueError('Signed provenance does not match the release')


def verify_release_environment(environment):
    """Require branch protection without claiming a solo release has peer approval."""
    if environment.get('can_admins_bypass') is not False:
        raise ValueError('Release environment must explicitly disable administrator bypass')
    policy = environment.get('deployment_branch_policy') or {}
    reviews = [rule for rule in environment.get('protection_rules', [])
               if rule.get('type') == 'required_reviewers']
    if (environment.get('name') != 'release' or policy.get('protected_branches') is not True
            or policy.get('custom_branch_policies') is not False):
        raise ValueError('Release requires a protected-branches-only environment')
    if any(rule.get('reviewers') != [] for rule in reviews):
        raise ValueError('Solo release environment must not require reviewers')


def artifacts(root, revision):
    if not re.fullmatch(r'[0-9a-f]{40}', revision): raise ValueError('Expected exact Git revision')
    result = []
    for service in sorted(SERVICES):
        folder = root / ('image-' + service)
        meta = json.loads((folder/'metadata.json').read_text())
        archive = folder/'image.tar'
        sbom = folder/'sbom.json'
        if any(path.is_symlink() for path in [archive,sbom,folder,folder/'metadata.json']): raise ValueError('Symlink artifact forbidden')
        with archive.open('rb') as stream: checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
        if (meta['service'] != service or meta['revision'] != revision or meta['archive_sha256'] != checksum
                or meta.get('sbom_sha256') != hashlib.sha256(sbom.read_bytes()).hexdigest()
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
    evidence = {}
    run_id, run_attempt = os.environ['GITHUB_RUN_ID'], os.environ['GITHUB_RUN_ATTEMPT']
    def docker(*args): return subprocess.check_output(['docker',*args],stderr=subprocess.DEVNULL,text=True).strip()
    for archive, meta in checked:
        predicate = provenance(meta,repository,revision,run_id,run_attempt)
        docker('load','--input',str(archive))
        if docker('image','inspect',meta['local_image'],'--format','{{.Id}}') != meta['image_id']:
            raise ValueError('Loaded image differs from scanned image')
        repo = 'ghcr.io/' + repository + '/' + meta['service']
        tag = repo + ':candidate-' + revision + '-' + run_id + '-' + run_attempt
        docker('tag',meta['image_id'],tag)
        docker('push',tag)
        refs = json.loads(docker('image','inspect',tag,'--format','{{json .RepoDigests}}'))
        matches = [ref for ref in refs if ref.startswith(repo+'@') and DIGEST.fullmatch(ref)]
        if len(matches)!=1: raise ValueError('Published registry digest unavailable')
        images[meta['service']] = matches[0]
        predicate_file = archive.parent/'provenance.json'
        predicate_file.write_text(json.dumps(predicate))
        run('cosign','sign','--yes',matches[0])
        run('cosign','attest','--yes','--type',PREDICATE,'--predicate',str(predicate_file),matches[0])
        evidence[meta['service']] = predicate['artifact']
    manifest = {'revision':revision,'run_id':run_id,'run_attempt':run_attempt,'images':images,'provenance':evidence}
    verify_manifest(manifest,repository,revision,run_id,run_attempt)
    # No consumable release manifest until every signature and claim verifies.
    output.write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts',type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--repository')
    parser.add_argument('--run-id')
    parser.add_argument('--run-attempt')
    parser.add_argument('--publish',action='store_true')
    parser.add_argument('--config',type=Path)
    parser.add_argument('--manifest',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Refusing to overwrite an existing output')
    if args.publish: publish(args.artifacts,args.revision,args.output)
    else:
        if not all([args.repository,args.revision,args.run_id,args.run_attempt]):
            parser.error('Trusted --repository, --revision, --run-id and --run-attempt are required')
        manifest=json.loads(args.manifest.read_text())
        verify_manifest(manifest,args.repository,args.revision,args.run_id,args.run_attempt)
        config=select_images(json.loads(args.config.read_text()),manifest)
        args.output.write_text(json.dumps(config,indent=2)+'\n')
