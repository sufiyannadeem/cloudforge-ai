#!/usr/bin/env python3
"""Offline packaging/artifact/quality/resource gate; never downloads or calls inference providers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'services/aiops-service'))


def packaging():
    base=os.environ['AIOPS_GLIBC_BASE']
    if not re.fullmatch(r'[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}',base):
        raise ValueError('Reviewed digest-pinned glibc Python base required')
    # Provenance/architecture/glibc compatibility are independently approved, not guessed from a name.
    wheelhouse=Path(os.environ['RAG_WHEELHOUSE']).resolve()
    lock=Path(os.environ['RAG_EMBEDDING_LOCK']).resolve()
    expected=os.environ['RAG_EMBEDDING_LOCK_SHA256']
    if hashlib.sha256(lock.read_bytes()).hexdigest()!=expected:raise ValueError('Unreviewed dependency lock')
    text=lock.read_text()
    for name in ('onnxruntime','tokenizers','numpy'):
        if not re.search(r'^'+name+r'==[^\n]+',text,re.M):raise ValueError('Missing pinned embedding dependency')
    subprocess.run([sys.executable,'-m','pip','install','--dry-run','--ignore-installed','--no-index',
        '--find-links='+str(wheelhouse),'--only-binary=:all:','--require-hashes',
        '-r',str(ROOT/'services/aiops-service/requirements.lock'),'-r',str(lock)],
        check=True,timeout=120,stdout=subprocess.DEVNULL)
    return {'base':base,'wheel_resolution':'PASS','lock_sha256':expected,
            'image_build_scan':'REQUIRED_SEPARATELY'}


def benchmark():
    import socket
    def offline(*args,**kwargs): raise OSError("Benchmark network access denied")
    socket.socket.connect=offline
    socket.create_connection=offline
    from app.knowledge_config import load_knowledge
    from app.sentence_embeddings import configured_encoder
    if os.environ['AI_EMBEDDING_MODE']!='pretrained-onnx':raise ValueError('Pretrained mode required')
    # Require explicit reviewed resource acceptance limits; no synthetic default success.
    max_rss=int(os.environ['RAG_MAX_RSS_MIB']);max_p95=float(os.environ['RAG_MAX_P95_MS'])
    if not 0<max_rss<=1024 or not 0<max_p95<=8000:raise ValueError('Invalid reviewed resource limits')
    started=time.perf_counter();kb,_,mode=load_knowledge(os.getenv('RAG_TEST_PROJECT_ID'))
    encoder=configured_encoder()
    left=encoder('requests take too long to respond')
    positive=sum(a*b for a,b in zip(left,encoder('high service response latency')))
    negative=sum(a*b for a,b in zip(left,encoder('gardening orchard apple trees')))
    if positive<.45 or positive<=negative+.1:raise ValueError('Pretrained paraphrase quality failed')
    fixtures=json.loads((ROOT/'services/aiops-service/app/fixtures/retrieval-quality.json').read_text())
    timings=[]
    for _ in range(5):
        for case in fixtures:
            start=time.perf_counter();hits=kb.search(case['query']);timings.append((time.perf_counter()-start)*1000)
            paths=[h.chunk.path for h in hits]
            if case['expected'] is None and paths:raise ValueError('Irrelevant knowledge accepted')
            if case['expected'] and case['expected'] not in paths:raise ValueError('Retrieval quality failed')
    rss=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
    p95=sorted(timings)[int(.95*(len(timings)-1))]
    if rss>max_rss or p95>max_p95:raise ValueError('Resource budget exceeded')
    return {'backend':mode,'queries':len(timings),'rss_mib':rss,'p95_ms':p95,
            'median_ms':statistics.median(timings),'total_seconds':time.perf_counter()-started,
            'quality':'PASS','note':'Linux process RSS; run under reviewed EKS-equivalent CPU/memory limits'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('gate',choices=['packaging','benchmark']);a=parser.parse_args()
    try:print(json.dumps(packaging() if a.gate=='packaging' else benchmark(),sort_keys=True))
    except KeyError as error:
        name=str(error.args[0])
        print(json.dumps(dict(gate=a.gate,status='BLOCKED',reason='Missing approved input: '+name if re.fullmatch('[A-Z_]+',name) else 'Required artifact metadata missing')))
        sys.exit(2)
    except (ImportError,FileNotFoundError):
        print(json.dumps(dict(gate=a.gate,status='BLOCKED',reason='Required cached runtime, wheelhouse or reviewed local artifact unavailable')))
        sys.exit(2)
    except (ValueError,OSError,subprocess.SubprocessError):
        print(json.dumps(dict(gate=a.gate,status='FAIL',reason='Artifact, dependency, quality or resource verification failed; no release authorization')))
        sys.exit(1)
