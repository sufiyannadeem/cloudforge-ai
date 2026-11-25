#!/usr/bin/env python3
"""Protected hosted preparation only: pinned model + hashed wheels + synthetic corpus.

This orchestrates existing artifact/index preparation; it grants no approval and
produces a candidate requiring a separate human hash review before verification.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import runpy
import re
import stat
import shutil
import subprocess
import sys
import tarfile

ROOT=Path(__file__).resolve().parents[2]
ACQUIRE=runpy.run_path(str(ROOT/'scripts/ci/acquire-integration-inputs.py'))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def command(args,**kwargs):subprocess.run([str(v) for v in args],check=True,timeout=600,**kwargs)


def archive_candidate(candidate,archive):
    """Write only confined regular files with validated relative archive names."""
    candidate=Path(candidate)
    if candidate.is_symlink():raise ValueError('Linked candidate root')
    with archive.open('xb') as output,gzip.GzipFile(filename='',mode='wb',fileobj=output,mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as tar:
        for path in sorted(candidate.rglob('*')):
            if path.is_symlink():raise ValueError('Candidate links forbidden')
            if path.is_dir():continue
            name=path.relative_to(candidate).as_posix()
            if (not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*',name)
                or any(part in {'.','..'} for part in Path(name).parts)
                or not path.resolve().is_relative_to(candidate.resolve())):
                raise ValueError('Unsafe candidate archive path')
            if any(parent.is_symlink() for parent in path.parents):raise ValueError('Linked candidate parent')
            fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
            with os.fdopen(fd,'rb') as data:
                metadata=os.fstat(data.fileno())
                if not stat.S_ISREG(metadata.st_mode):raise ValueError('Candidate must contain regular files')
                info=tarfile.TarInfo(name)
                info.size=metadata.st_size
                info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;info.mode=0o644
                tar.addfile(info,data)


def prepare(folder):
    if (os.getenv('GITHUB_ACTIONS')!='true' or os.getenv('RUNNER_ENVIRONMENT')!='github-hosted'
        or os.getenv('SEMANTIC_PREPARATION_APPROVED')!='true'):
        raise ValueError('Protected hosted semantic preparation approval required')
    reviewer=os.environ['SEMANTIC_ARTIFACT_REVIEWER'].strip()
    if not reviewer or reviewer.lower() in {'ci','pending','github-actions','repository-maintainers'}:
        raise ValueError('Explicit human review statement required; no inferred actor attestation')
    lock=ACQUIRE['load'](ROOT/'ci/integration-acquisition.json',semantic=True)
    prep=lock['semantic']['preparation'];folder.mkdir(parents=True,exist_ok=False)
    bootstrap=ROOT/'ci/semantic-preparation.lock'
    if sha(bootstrap)!=prep['bootstrap_lock_sha256']:raise ValueError('Bootstrap lock mismatch')
    source=ROOT/'ci/semantic-corpus/source-manifest.json'
    if sha(source)!=prep['corpus_source_sha256']:raise ValueError('Synthetic corpus source mismatch')
    corpus_source=json.loads(source.read_bytes())
    if corpus_source['purpose']!='SYNTHETIC_CI_ONLY':raise ValueError('Synthetic inputs only')
    corpus=folder/'candidate/corpus';corpus.mkdir(parents=True)
    entries={}
    for name,expected in corpus_source['files'].items():
        path=ROOT/'ci/semantic-corpus'/name
        if not path.resolve().is_relative_to((ROOT/'ci/semantic-corpus').resolve()) or path.is_symlink() or sha(path)!=expected:
            raise ValueError('Corpus integrity failed')
        output=corpus/name;output.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,output)
        # This statement is supplied explicitly by the human-approved environment, never fabricated in source.
        entries[name]=dict(sha256=expected,projects=['*'],signals=[],reviewed_by=reviewer)
    (corpus/'manifest.json').write_text(json.dumps(dict(schema_version=2,documents=entries),sort_keys=True,indent=2)+'\n')
    wheels=folder/'candidate/wheels';wheels.mkdir()
    combined=wheels/'requirements-embeddings.lock'
    command([sys.executable,'-m','piptools','compile','--generate-hashes','--allow-unsafe',
        '--no-header','--no-annotate','--no-emit-index-url','--no-emit-trusted-host','--pip-args=--only-binary=:all:',
        '--output-file',combined,ROOT/'services/aiops-service/requirements.lock',ROOT/'services/aiops-service/requirements-embeddings.txt'])
    wheelhouse=wheels/'wheelhouse';wheelhouse.mkdir()
    command([sys.executable,'-m','pip','download','--only-binary=:all:','--require-hashes','--dest',wheelhouse,'-r',combined])
    # Separate model runtime from the pinned pip-tools bootstrap environment.
    runtime=folder/'runtime';command([sys.executable,'-m','venv',runtime]);python=runtime/'bin/python'
    command([python,'-m','pip','install','--no-index','--find-links',wheelhouse,'--only-binary=:all:',
        '--require-hashes','-r',combined])
    staging=folder/'model-source';staging.mkdir()
    for name,item in prep['files'].items():ACQUIRE['fetch'](item,staging/name)
    model=folder/'candidate/model'
    command([python,ROOT/'scripts/prepare-embedding-artifact.py','--source',staging,'--output',model,
        '--source-revision',prep['revision'],'--reviewed-by',reviewer])
    index=folder/'candidate/index.json'
    env=dict(os.environ,AI_KNOWLEDGE_DIR=str(corpus),AI_EMBEDDING_ARTIFACT_DIR=str(model),AI_EMBEDDING_MANIFEST_SHA256=sha(model/'manifest.json'),
             AI_KNOWLEDGE_MANIFEST_SHA256=sha(corpus/'manifest.json'),OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',TOKENIZERS_PARALLELISM='false')
    # Artifact/index generation is local-only after acquisition; no embedding/network provider.
    offline="import runpy,socket,sys; deny=lambda *a,**k: (_ for _ in ()).throw(OSError('offline embedding preparation')); socket.socket.connect=deny; socket.create_connection=deny; script=sys.argv.pop(1); runpy.run_path(script,run_name='__main__')"
    command([python,'-c',offline,ROOT/'scripts/prepare-knowledge-embeddings.py','--knowledge-dir',corpus,'--output',index],env=env)
    config=dict(AIOPS_GLIBC_BASE=lock['semantic']['glibc_base'],RAG_EMBEDDING_LOCK_SHA256=sha(combined),
        AI_EMBEDDING_MODE='pretrained-onnx',AI_EMBEDDING_MANIFEST_SHA256=sha(model/'manifest.json'),
        AI_KNOWLEDGE_MANIFEST_SHA256=sha(corpus/'manifest.json'),AI_KNOWLEDGE_INDEX_SHA256=sha(index),
        RAG_MAX_RSS_MIB=str(lock['semantic']['max_rss_mib']),RAG_MAX_P95_MS=str(lock['semantic']['max_p95_ms']))
    candidate=folder/'candidate'
    (candidate/'configuration.json').write_text(json.dumps(config,sort_keys=True,indent=2)+'\n')
    provenance=dict(source_sha=os.environ['GITHUB_SHA'],repository=os.environ['GITHUB_REPOSITORY'],
        run_id=os.environ['GITHUB_RUN_ID'],run_attempt=os.environ['GITHUB_RUN_ATTEMPT'],
        acquisition_lock_sha256=sha(ROOT/'ci/integration-acquisition.json'),corpus_source_sha256=sha(source),
        status='CANDIDATE_REQUIRES_SEPARATE_HUMAN_HASH_APPROVAL',human_review_statement=reviewer)
    (candidate/'provenance.json').write_text(json.dumps(provenance,sort_keys=True,indent=2)+'\n')
    archive=folder/'semantic-candidate.tar.gz'
    archive_candidate(candidate,archive)
    if archive.stat().st_size>400*1024*1024:raise ValueError('Candidate artifact budget exceeded')
    (folder/'semantic-candidate.sha256').write_text(sha(archive)+'  semantic-candidate.tar.gz\n')
    print('Candidate SHA256:',sha(archive),'separate reviewer approval required; no production artifact approval granted')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    prepare(args.output.resolve())
