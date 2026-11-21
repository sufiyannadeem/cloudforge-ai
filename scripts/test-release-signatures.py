#!/usr/bin/env python3
"""Disposable, offline Cosign crypto drill; never signs/pushes a container.

Only this local-key fixture omits transparency: empty signing/trust configurations
and --insecure-ignore-tlog isolate signature/DSSE tamper checks from public services.
Production release-images.py never uses these flags or fixture keys.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile


def write_tampered_attestation(root):
    """Mutate data only; both filenames are fixed in a caller-owned test directory."""
    attestation=root/'attestation.json'
    if attestation.is_symlink() or not attestation.resolve(strict=True).is_relative_to(root):
        raise ValueError('Attestation must be a regular fixture file')
    bundle=json.loads(attestation.read_text())
    envelope=bundle['dsseEnvelope']
    statement=json.loads(base64.b64decode(envelope['payload']))
    statement['predicate']['revision']='b'*40
    envelope['payload']=base64.b64encode(json.dumps(statement).encode()).decode()
    # Content is serialized to an exclusive, fixed fixture path, never used as a filename.
    with (root/'tampered-attestation.json').open('x') as stream:
        json.dump(bundle, stream)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cosign',type=Path,required=True)
    args=parser.parse_args()
    binary=str(args.cosign.resolve(strict=True))
    with tempfile.TemporaryDirectory(prefix='cloudforge-signature-drill-') as directory:
        root=Path(directory)
        env=dict(os.environ,COSIGN_PASSWORD='')
        def command(*arguments, reject=False):
            result=subprocess.run([binary,*arguments],cwd=root,env=env,capture_output=True,timeout=30)
            if (result.returncode==0)==reject:
                raise RuntimeError('Unexpected crypto result: '+arguments[0])
        command('signing-config','create','--out','local-config.json')
        command('trusted-root','create','--out','local-root.json')
        command('generate-key-pair','--output-key-prefix','fixture')
        command('generate-key-pair','--output-key-prefix','wrong')
        payload=root/'payload';payload.write_bytes(b'local fixture only\n')
        command('sign-blob','--yes','--key','fixture.key','--signing-config','local-config.json','--bundle','signature.json','payload')
        verify=['verify-blob','--trusted-root','local-root.json','--insecure-ignore-tlog','--key','fixture.pub','--bundle','signature.json','payload']
        command(*verify)
        payload.write_bytes(b'changed fixture\n');command(*verify,reject=True)
        payload.write_bytes(b'local fixture only\n')
        wrong=verify.copy();wrong[wrong.index('fixture.pub')]='wrong.pub';command(*wrong,reject=True)
        predicate_type='https://github.com/sufiyannadeem/cloudforge-ai/attestations/scanned-image-release/v1'
        (root/'predicate.json').write_text(json.dumps({'revision':'a'*40}))
        command('attest-blob','--yes','--key','fixture.key','--signing-config','local-config.json','--bundle','attestation.json','--type',predicate_type,'--predicate','predicate.json','payload')
        attest=['verify-blob-attestation','--trusted-root','local-root.json','--insecure-ignore-tlog','--key','fixture.pub','--bundle','attestation.json','--type',predicate_type,'payload']
        command(*attest)
        write_tampered_attestation(root)
        tampered = attest.copy()
        tampered[tampered.index('attestation.json')] = 'tampered-attestation.json'
        command(*tampered,reject=True)
    print('PASS: valid signature/attestation; changed payload, wrong key and changed signed provenance rejected; temporary keys removed')


if __name__=='__main__':main()
