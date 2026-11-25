#!/usr/bin/env python3
"""Select only a manually hash-approved same-SHA synthetic preparation candidate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy

ROOT=Path(__file__).resolve().parents[2]
acquire=runpy.run_path(str(ROOT/'scripts/ci/acquire-integration-inputs.py'))
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--archive',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
if os.getenv('GITHUB_ACTIONS')!='true' or os.getenv('RUNNER_ENVIRONMENT')!='github-hosted':parser.exit(2,'Hosted candidate selection only\n')
lock=acquire['load'](ROOT/'ci/integration-acquisition.json',semantic=True)
expected=acquire['digest'](os.environ['SEMANTIC_CANDIDATE_SHA256'])
fingerprint=hashlib.sha256()
with args.archive.open('rb') as stream:
    for chunk in iter(lambda:stream.read(1024*1024),b''):fingerprint.update(chunk)
if args.archive.stat().st_size>400*1024*1024 or fingerprint.hexdigest()!=expected:
    raise ValueError('Independent candidate hash approval mismatch')
acquire['unpack'](args.archive,args.output,'tar.gz')
provenance=json.loads((args.output/'provenance.json').read_bytes())
checks={'source_sha':os.environ['GITHUB_SHA'],'repository':os.environ['GITHUB_REPOSITORY'],
        'run_id':os.environ['PREPARATION_RUN_ID'],'run_attempt':os.environ['PREPARATION_RUN_ATTEMPT'],
        'acquisition_lock_sha256':os.environ['CI_ACQUISITION_LOCK_SHA256'],
        'corpus_source_sha256':lock['semantic']['preparation']['corpus_source_sha256']}
if any(provenance.get(k)!=v for k,v in checks.items()):raise ValueError('Candidate source/run/lock binding mismatch')
for name,item in lock['semantic']['preparation']['files'].items():
    path=args.output/'model'/name
    if hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Candidate model source pin mismatch')
source=json.loads((ROOT/'ci/semantic-corpus/source-manifest.json').read_bytes())
manifest=json.loads((args.output/'corpus/manifest.json').read_bytes())
if manifest.get('schema_version')!=2 or set(manifest['documents'])!=set(source['files']):raise ValueError('Synthetic corpus inventory changed')
for name,sha in source['files'].items():
    entry=manifest['documents'][name];path=args.output/'corpus'/name
    if entry['projects']!=['*'] or entry['sha256']!=sha or hashlib.sha256(path.read_bytes()).hexdigest()!=sha:
        raise ValueError('Synthetic corpus content changed')
config=json.loads((args.output/'configuration.json').read_bytes())
if config['AIOPS_GLIBC_BASE']!=lock['semantic']['glibc_base'] or config['AI_EMBEDDING_MODE']!='pretrained-onnx':raise ValueError('Candidate profile mismatch')
config.update(RAG_WHEELHOUSE=str(args.output/'wheels/wheelhouse'),RAG_EMBEDDING_LOCK=str(args.output/'wheels/requirements-embeddings.lock'),
    AI_EMBEDDING_ARTIFACT_DIR=str(args.output/'model'),AI_KNOWLEDGE_DIR=str(args.output/'corpus'),AI_KNOWLEDGE_INDEX_FILE=str(args.output/'index.json'))
if float(config['RAG_MAX_P95_MS'])!=float(lock['semantic']['max_p95_ms']) or int(config['RAG_MAX_RSS_MIB'])!=int(lock['semantic']['max_rss_mib']):raise ValueError('Resource policy changed')
with Path(os.environ['GITHUB_ENV']).open('a') as output:
    for key,value in config.items():
        if key not in {'AIOPS_GLIBC_BASE','RAG_WHEELHOUSE','RAG_EMBEDDING_LOCK','RAG_EMBEDDING_LOCK_SHA256',
            'AI_EMBEDDING_MODE','AI_EMBEDDING_ARTIFACT_DIR','AI_EMBEDDING_MANIFEST_SHA256','AI_KNOWLEDGE_DIR',
            'AI_KNOWLEDGE_MANIFEST_SHA256','AI_KNOWLEDGE_INDEX_FILE','AI_KNOWLEDGE_INDEX_SHA256','RAG_MAX_RSS_MIB','RAG_MAX_P95_MS'}:
            raise ValueError('Unexpected candidate configuration')
        if not isinstance(value,str) or '\n' in value or '\r' in value:raise ValueError('Invalid candidate value')
        output.write(key+'='+value+'\n')
