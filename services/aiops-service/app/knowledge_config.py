"""Reviewed local retrieval; no network, provider prompts, history or mutation tools."""
import hashlib
import json
import os
import re
from pathlib import Path
from uuid import UUID
from .rag import OperationalKnowledgeBase
from .rag_models import KnowledgeDocument
from .sentence_embeddings import configured_encoder, verified_bytes, vector

CONCEPTS=(
    {'latency','slow','delay','response','p95','p99'},
    {'error','errors','failure','failed','5xx','fault'},
    {'availability','outage','unavailable','downtime','healthy'},
    {'deployment','rollout','release','change','revision'},
    {'slo','budget','burn','reliability'},
)
SIGNALS=frozenset({'latency','error_rate','availability','deployment_health','cpu_pressure',
                  'memory_pressure','oom','restart_loop','image_pull_failure',
                  'scheduling_failure','startup_configuration','dependency_health','slo_violation'})
# Defense in depth, not an instruction interpreter. Reviewed hashes are the trust root.
UNSAFE=re.compile(r'ignore\s+(?:all\s+|previous\s+|prior\s+)?instructions|system\s*prompt|'
                  r'\[/?INST\]|<\|(?:system|assistant)|(?:reveal|exfiltrate|disclose)\s+(?:all\s+)?(?:secret|credential)|'
                  r'-----BEGIN .*PRIVATE KEY-----|(?:api[_-]?key|password|token)\s*[=:]\s*\S+',re.I)


def concept_embedding(text):
    words=set(re.findall('[a-z0-9]+',text.lower()))
    return [float(len(words & group)) for group in CONCEPTS]


def reviewed_knowledge(root, project_id=None):
    if project_id is not None: project_id=str(UUID(project_id))
    if (root/'manifest.json').is_symlink() or (root/'manifest.json').stat().st_size>131072:
        raise ValueError('Manifest too large or linked')
    raw=(root/'manifest.json').read_bytes()
    if len(raw)>131072: raise ValueError('Manifest too large')
    expected=os.getenv('AI_KNOWLEDGE_MANIFEST_SHA256')
    if expected and hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('Manifest mismatch')
    manifest=json.loads(raw)
    versioned=manifest.get('schema_version')==2
    entries=manifest['documents'] if versioned else manifest
    if not isinstance(entries,dict) or len(entries)>128: raise ValueError('Corpus too large')
    documents=[]; metadata={}; total=0
    for path,entry in sorted(entries.items()):
        if not path.endswith('.md') or len(path)>200: raise ValueError('Invalid document path')
        if versioned:
            if not isinstance(entry,dict) or not entry.get('reviewed_by'): raise ValueError('Unreviewed knowledge')
            scopes=entry['projects']
            if not isinstance(scopes,list) or not scopes: raise ValueError('Missing scope')
            if scopes!=['*'] and any(str(UUID(scope))!=scope for scope in scopes): raise ValueError('Invalid scope')
            # Scope is manifest/DB authority, never query text or alert labels.
            if scopes!=['*'] and project_id not in scopes: continue
            signals=entry.get('signals',[])
            if not isinstance(signals,list) or any(s not in SIGNALS for s in signals): raise ValueError('Invalid signals')
            digest=entry['sha256']
        else:
            # Existing git-reviewed hash manifests describe global public runbooks only.
            digest=entry; signals=[]
        data=verified_bytes(root,path,digest,65536)
        total+=len(data)
        if total>1048576: raise ValueError('Corpus too large')
        content=data.decode('utf-8').strip()
        if UNSAFE.search(content) or any(ord(c)<32 and c not in '\n\r\t' for c in content):
            raise ValueError('Unsafe knowledge')
        if not content: continue
        title=OperationalKnowledgeBase._extract_title(content,Path(path).stem)[:160]
        documents.append(KnowledgeDocument('knowledge:'+hashlib.sha256(path.encode()).hexdigest()[:16],path,title,content))
        metadata[path]={'document_sha256':digest,'signals':signals}
    return raw,documents,metadata


def load_knowledge(project_id=None):
    root=Path(os.getenv('AI_KNOWLEDGE_DIR',str(Path(__file__).resolve().parent.parent/'knowledge')))
    raw,documents,metadata=reviewed_knowledge(root,project_id)
    mode=os.getenv('AI_EMBEDDING_MODE','concept-v1')
    if mode not in {'concept-v1','lexical','pretrained-onnx'}: raise ValueError('Unsupported backend')
    embedder=concept_embedding if mode=='concept-v1' else None
    if mode=='pretrained-onnx':
        # Production semantic artifacts AND corpus approval must be explicitly pinned.
        if not os.getenv('AI_KNOWLEDGE_MANIFEST_SHA256'): raise ValueError('Corpus approval missing')
        embedder=configured_encoder()
    kb=OperationalKnowledgeBase(root,documents=documents,embedder=embedder,min_relevance=.35,
                                semantic_threshold=.45 if mode=='pretrained-onnx' else .35)
    if len(kb.chunks)>512: raise ValueError('Chunk budget exceeded')
    if mode=='pretrained-onnx':
        index=Path(os.environ['AI_KNOWLEDGE_INDEX_FILE'])
        bundle=json.loads(verified_bytes(index.parent,index.name,os.environ['AI_KNOWLEDGE_INDEX_SHA256'],8*1024*1024))
        if (bundle.get('schema_version')!=1 or bundle.get('corpus_sha256')!=hashlib.sha256(raw).hexdigest()
            or bundle.get('model_manifest_sha256')!=os.environ['AI_EMBEDDING_MANIFEST_SHA256']):
            raise ValueError('Stale embedding index')
        rows=bundle['chunks']
        if not isinstance(rows,dict) or len(rows)>512: raise ValueError('Invalid index')
        kb.embeddings={}
        for chunk in kb.chunks:
            row=rows[chunk.chunk_id]
            if row['sha256']!=hashlib.sha256(chunk.content.encode()).hexdigest(): raise ValueError('Chunk changed')
            kb.embeddings[chunk.chunk_id]=vector(row['embedding'])
    return kb,metadata,mode


def knowledge_references(query: str, project_id=None) -> dict:
    try:
        kb,metadata,mode=load_knowledge(project_id)
        hits=kb.search(query[:2000],top_k=5)
        return {'retrieval_status':mode if hits else 'no_match','retrieval_backend':mode,
                'references':[dict(path=h.chunk.path,title=h.chunk.title,chunk_id=h.chunk.chunk_id,
                                   score=h.score,matched_terms=list(h.matched_terms),**metadata[h.chunk.path]) for h in hits]}
    except Exception:
        # No silent fallback, raw error/secret/path disclosure or claim that semantic ran.
        return {'retrieval_status':'unavailable','retrieval_backend':'unavailable','references':[]}


def local_signal_knowledge(project_id, signals):
    """Query exclusively fixed evidence enums, never rejection reasons or raw evidence."""
    observed={s['signal'] for s in signals if s.get('state')=='degraded' and s.get('signal') in SIGNALS}
    result=knowledge_references(' '.join(sorted(s.replace('_',' ') for s in observed)),project_id)
    result['supported_signals']=sorted(observed.intersection(
        {s for r in result['references'] for s in r.get('signals',[])}))
    return result


def validate_knowledge_citations(citations, result):
    """Validate locally against this retrieval, never model-generated source names."""
    if result.get('retrieval_status') in {'unavailable','no_match'}: return isinstance(citations,list) and not citations
    allowed={r['chunk_id'] for r in result.get('references',[])}
    return (isinstance(citations,list) and len(citations)<=5 and all(isinstance(c,str) for c in citations) and len(set(citations))==len(citations)
            and all(isinstance(c,str) and c in allowed for c in citations))
