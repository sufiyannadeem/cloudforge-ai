"""Offline-only MiniLM sentence embeddings. Optional CPU dependencies; no Hub client."""
import hashlib
import json
import math
import os
import re
import threading
from functools import lru_cache
from pathlib import Path

MODEL_ID = 'sentence-transformers/all-MiniLM-L6-v2'
MODEL_REVISION = '1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
DIMENSION = 384
MAX_TOKENS = 256


def verified_bytes(root, relative, digest, limit):
    root = Path(root).resolve()
    path = root / relative
    if (not isinstance(relative, str) or Path(relative).is_absolute()
        or '..' in Path(relative).parts or path.is_symlink()
        or not path.resolve().is_relative_to(root)
        or not re.fullmatch('[0-9a-f]{64}', digest or '')
        or path.stat().st_size > limit):
        raise ValueError('Unapproved artifact')
    raw = path.read_bytes()
    if len(raw) > limit or hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError('Artifact integrity failed')
    return raw


def vector(value, dimension=DIMENSION):
    if not isinstance(value, (list, tuple)) or len(value) != dimension:
        raise ValueError('Embedding dimension mismatch')
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError('Invalid embedding')
    norm = math.sqrt(sum(x*x for x in value))
    if not math.isfinite(norm) or norm < 1e-12:
        raise ValueError('Empty embedding')
    return tuple(float(x/norm) for x in value)


def pool_sentence(tokens, mask):
    """Bounded attention-mask mean pooling, then L2; independently testable offline."""
    if (len(tokens)!=MAX_TOKENS or len(mask)!=MAX_TOKENS or not any(mask)
        or any(type(m) is not int or m not in (0,1) for m in mask)):
        raise ValueError('Invalid token mask')
    summed=[0.0]*DIMENSION
    for row,active in zip(tokens,mask):
        if len(row)!=DIMENSION: raise ValueError('Unexpected token dimension')
        if active:
            if any(type(x) not in (float,int) or not math.isfinite(x) for x in row):
                raise ValueError('Invalid token output')
            for index,value in enumerate(row): summed[index]+=value
    count=sum(mask)
    return vector([value/count for value in summed])


class LocalSentenceEncoder:
    def __init__(self, root, manifest):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        ort.disable_telemetry_events()
        self.np = np
        files = manifest['files']
        if set(files) != {'model.onnx', 'tokenizer.json', 'LICENSE'}:
            raise ValueError('Unexpected model files')
        model = verified_bytes(root, 'model.onnx', files['model.onnx'], 128*1024*1024)
        tokenizer = verified_bytes(root, 'tokenizer.json', files['tokenizer.json'], 2*1024*1024)
        verified_bytes(root, 'LICENSE', files['LICENSE'], 65536)
        self.tokenizer = Tokenizer.from_str(tokenizer.decode('utf-8'))
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)
        self.tokenizer.enable_padding(length=MAX_TOKENS, pad_id=0, pad_token='[PAD]')
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # Load bytes: no paths for ONNX external tensors, exporters or remote code.
        self.session = ort.InferenceSession(model, sess_options=options, providers=['CPUExecutionProvider'])
        self.inputs = {item.name for item in self.session.get_inputs()}
        if self.inputs != {'input_ids', 'attention_mask', 'token_type_ids'}:
            raise ValueError('Unexpected encoder inputs')
        self.lock = threading.Lock()

    def __call__(self, text):
        if not self.lock.acquire(blocking=False):
            raise ValueError('Embedding capacity exhausted')
        try:
            encoded = self.tokenizer.encode(text[:2000])
            np = self.np
            mask = np.asarray([encoded.attention_mask], dtype=np.int64)
            feed = {'input_ids': np.asarray([encoded.ids], dtype=np.int64),
                    'attention_mask': mask, 'token_type_ids': np.asarray([encoded.type_ids], dtype=np.int64)}
            tokens = self.session.run(None, feed)[0]
            if tokens.shape != (1, MAX_TOKENS, DIMENSION):
                raise ValueError('Unexpected encoder output')
            return pool_sentence(tokens[0].tolist(), encoded.attention_mask)
        finally:
            self.lock.release()


@lru_cache(maxsize=1)
def _load(root, raw, identity):
    manifest = json.loads(raw)
    if (manifest.get('schema_version') != 1 or manifest.get('model_id') != MODEL_ID
        or manifest.get('revision') != MODEL_REVISION or manifest.get('dimension') != DIMENSION
        or manifest.get('pooling') != 'attention_mask_mean_l2' or manifest.get('max_tokens') != MAX_TOKENS
        or manifest.get('license') != 'Apache-2.0' or not manifest.get('reviewed_by')):
        raise ValueError('Model approval mismatch')
    return LocalSentenceEncoder(root, manifest)


_configuration_lock = threading.Lock()

def configured_encoder():
    if not _configuration_lock.acquire(blocking=False):
        raise ValueError('Embedding initialization busy')
    try:
        return _configured_encoder()
    finally:
        _configuration_lock.release()


def _configured_encoder():
    root = Path(os.environ['AI_EMBEDDING_ARTIFACT_DIR'])
    digest = os.environ['AI_EMBEDDING_MANIFEST_SHA256']
    raw = verified_bytes(root, 'manifest.json', digest, 16384)
    # A changed local file invalidates the one-entry cache and is rehashed on load.
    identity = tuple((name, (root/name).stat().st_size, (root/name).stat().st_mtime_ns,
                      (root/name).stat().st_ino) for name in ('model.onnx','tokenizer.json','LICENSE'))
    if any((root/name).is_symlink() for name in ('model.onnx','tokenizer.json','LICENSE')):
        raise ValueError('Symlink artifact')
    return _load(str(root.resolve()), raw, identity)
