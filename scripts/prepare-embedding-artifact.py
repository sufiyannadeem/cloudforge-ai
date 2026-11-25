#!/usr/bin/env python3
"""Package pre-staged, reviewed MiniLM files. No Hub client, network or inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'services/aiops-service'))
from app.sentence_embeddings import MODEL_ID,MODEL_REVISION,DIMENSION,MAX_TOKENS


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--source-revision',required=True)
    parser.add_argument('--reviewed-by',required=True)
    args=parser.parse_args()
    if args.source_revision!=MODEL_REVISION or not args.reviewed_by.strip():
        parser.error('Exact pinned source revision and reviewer are required')
    # Validate everything before creating an output. No untrusted Python/pickle code.
    files={}
    for name,limit in [('model.onnx',128*1024*1024),('tokenizer.json',2*1024*1024),('LICENSE',65536)]:
        path=args.source/name
        if path.is_symlink() or not 0<path.stat().st_size<=limit: raise ValueError('Invalid local artifact')
        files[name]=path.read_bytes()
    manifest=dict(schema_version=1,model_id=MODEL_ID,revision=MODEL_REVISION,
                  dimension=DIMENSION,max_tokens=MAX_TOKENS,pooling='attention_mask_mean_l2',
                  license='Apache-2.0',reviewed_by=args.reviewed_by.strip(),
                  files={n:hashlib.sha256(raw).hexdigest() for n,raw in files.items()})
    args.output.mkdir(exist_ok=False)
    for name,raw in files.items():(args.output/name).write_bytes(raw)
    raw=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    (args.output/'manifest.json').write_bytes(raw)
    print('Model manifest SHA256: '+hashlib.sha256(raw).hexdigest())


if __name__=='__main__':main()
