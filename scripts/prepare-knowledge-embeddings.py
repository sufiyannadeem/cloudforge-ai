#!/usr/bin/env python3
"""Offline preparation from already reviewed local artifacts. Never downloads."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/aiops-service'))
from app.knowledge_config import reviewed_knowledge
from app.rag import OperationalKnowledgeBase
from app.sentence_embeddings import configured_encoder


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--knowledge-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): parser.error('Output already exists; explicit new version required')
    # Final artifact includes all manifest scopes; runtime filters BEFORE vector access.
    if not os.getenv('AI_KNOWLEDGE_MANIFEST_SHA256'): raise ValueError('Reviewed corpus digest required')
    raw,_,_=reviewed_knowledge(args.knowledge_dir)
    manifest=json.loads(raw)
    scopes={None}
    if manifest.get('schema_version')==2:
        scopes.update(p for entry in manifest['documents'].values() for p in entry['projects'] if p!='*')
    documents={}
    for scope in sorted(scopes,key=lambda x:x or ''):
        raw,docs,_=reviewed_knowledge(args.knowledge_dir,scope)
        documents.update({d.path:d for d in docs})
    kb=OperationalKnowledgeBase(args.knowledge_dir,documents=list(documents.values()))
    if len(kb.chunks)>512: raise ValueError('Chunk budget exceeded')
    encoder=configured_encoder()
    chunks={c.chunk_id:dict(sha256=hashlib.sha256(c.content.encode()).hexdigest(),embedding=encoder(c.content)) for c in kb.chunks}
    bundle=dict(schema_version=1,corpus_sha256=hashlib.sha256(raw).hexdigest(),
                model_manifest_sha256=os.environ['AI_EMBEDDING_MANIFEST_SHA256'],chunks=chunks)
    data=(json.dumps(bundle,sort_keys=True,allow_nan=False)+'\n').encode()
    if len(data)>8*1024*1024: raise ValueError('Index budget exceeded')
    with args.output.open('xb') as stream: stream.write(data)
    print('Index SHA256: '+hashlib.sha256(data).hexdigest())
    print('Corpus SHA256: '+bundle['corpus_sha256'])


if __name__=='__main__': main()
