# Local production semantic retrieval

For the current approval-gated hosted preparation/verification path and resolved
public pins, see [GITHUB_HOSTED_VERIFICATION.md](GITHUB_HOSTED_VERIFICATION.md).
Manual artifact staging below remains the optional dedicated/release-environment path.

Operational evidence, runbooks, rejection history and query text remain inside
CloudForge. Retrieval runs in the existing operational AIOps workload, **never** the
isolated Gemini worker. Gemini receives its existing aggregate enum DTO only. Runbooks
are context, not facts about live state; neither prose nor vectors create actions.
Existing project authorization runs before document collection. Manifest project scopes
further restrict knowledge; an unknown/missing project cannot load scoped documents.

## Reviewed model profile

The supported profile is `sentence-transformers/all-MiniLM-L6-v2`, pinned to
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`: 384 dimensions, at most 256 tokens,
attention-mask mean pooling and L2 normalization. It uses a six-layer English sentence
encoder with about 22.7 million parameters. The repository metadata declares Apache-2.0.
Technical licensing review: Apache-2.0 permits deployment/redistribution subject to its
license/notice conditions; preserve applicable copyright, license and notices and review
any modifications. Release owners must attest the exact source/license materials and
artifact hashes. This is not a claim that a production artifact has already been approved.

Sources: [pinned model repository](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41),
[model card and pooling example](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
[ONNX token outputs require pooling](https://www.sbert.net/docs/sentence_transformer/usage/efficiency.html).
The runtime implements that pooling locally, not a remote embedding service.

## Artifact preparation (separate approved release environment)

Nothing in runtime downloads, exports or discovers a model. No model has been downloaded
or executed during this batch. Prepare files in an approved build environment:

1. Obtain the exact pinned repository revision through the normal reviewed supply chain.
   Stage its **self-contained** `onnx/model.onnx` as `model.onnx`, its `tokenizer.json`,
   and reviewed Apache license/notice material as `LICENSE`. Do not stage pickle,
   safetensors, Python modules, external ONNX tensor files, or unreviewed quantized variants.
   Verify source provenance independently; hashing alone does not prove origin/licensing.
2. Run `scripts/prepare-embedding-artifact.py` with `--source`, a new `--output`, the
   exact `--source-revision` and `--reviewed-by`. It only packages already local files
   and produces a SHA256 manifest. Review/sign the resulting manifest and immutable
   artifact digest using the release process; protect expected hashes independently.
3. Review `knowledge/manifest.json`: schema v2 binds each Markdown file's SHA256,
   `reviewed_by`, `projects` (either `['*']` for global approved material or exact project
   UUIDs), and fixed signal tags used only for local ranking. Do not approve secrets,
   customer records, raw logs or rejection reasons. Unknown scopes are denied.
   Existing v1 path/hash manifests remain supported as global git-reviewed material;
   v2 is required for per-project documents and signal ranking metadata.
4. Set `AI_EMBEDDING_ARTIFACT_DIR`, `AI_EMBEDDING_MANIFEST_SHA256` and
   `AI_KNOWLEDGE_MANIFEST_SHA256` to reviewed local artifacts/digests. Run
   `scripts/prepare-knowledge-embeddings.py --knowledge-dir <reviewed-dir> --output <new-index.json>`.
   This executes the supplied local encoder, never a network client, and refuses
   overwrites. It includes every approved project scope and prints corpus/index hashes.
5. Review the index, run the real-model quality gate and sign/pin its SHA256. The index
   binds the corpus manifest, model manifest, stable content-based chunk IDs, exact
   chunk content hashes and finite 384-dimensional vectors. Any document/chunk/model
   change requires a newly prepared/reviewed index. No automatic resets or rebuilds.

## Runtime configuration and resource bounds

Optional CPU dependencies are pinned in `services/aiops-service/requirements-embeddings.txt`.
Generate a transitive, wheel-hashed lock and scan it for the target architecture in release
CI. Do not install these dependencies into the isolated inference image. ONNX Runtime
CPU wheels require a compatible **glibc** image; the current Alpine operational image
is not a semantic-ready image. Supply an approved digest-pinned glibc AIOps image with
existing service dependencies plus the optional locked wheels. No image was built or
lock generated here, so that packaging/scan gate remains unresolved.

Set on the operational AIOps workload only:

```text
AI_EMBEDDING_MODE=pretrained-onnx
AI_EMBEDDING_ARTIFACT_DIR=/opt/cloudforge/embeddings
AI_EMBEDDING_MANIFEST_SHA256=<reviewed-model-manifest-sha256>
AI_KNOWLEDGE_DIR=/opt/cloudforge/knowledge
AI_KNOWLEDGE_MANIFEST_SHA256=<reviewed-corpus-manifest-sha256>
AI_KNOWLEDGE_INDEX_FILE=/opt/cloudforge/index/approved.json
AI_KNOWLEDGE_INDEX_SHA256=<reviewed-index-sha256>
```

Mount artifact/corpus/index directories immutable and read-only; protect expected digests
with deployment review/admission. Model files are hashed at initialization and rechecked
when their filesystem identity changes. This assumes immutable mounts, not a malicious
local writer able to preserve inode/time/size. Corpus and index hashes are checked on
retrieval. No credentials, new IAM grants, Kubernetes permissions, vector DB or embedding
network access are needed. Block external embedding endpoints with existing egress policy.

Use **one application process per Pod** for one cached model session; horizontal replicas
have independent bounded sessions. One CPU thread, sequential CPU execution, batch one,
256 tokens and 2,000 query characters are enforced. Concurrent model initialization/query
capacity fails unavailable instead of queueing unbounded work. ORT telemetry is disabled.
Initial sizing proposal: request 500m CPU/512Mi, limit 1 CPU/1Gi; benchmark and load-test
on the chosen EKS architecture before production. This is a starting allocation, not a
measured memory/latency guarantee. The float model is roughly 90MB; runtime graph/session
memory adds overhead. Quantized profiles require a separate reviewed implementation and
quality baseline; none is silently selected.

Corpus limits: 128 manifest documents, 64KiB/document, 1MiB per visible corpus, 512 chunks,
2,000 characters/chunk, 8MiB index, five hits and 12,000 context characters. Long sections
are split rather than silently losing their tail. Document vectors are precomputed;
only a query is embedded at runtime. Flat bounded cosine scanning avoids a vector DB.
Hybrid relevance combines 80% cosine and 20% normalized lexical/title overlap; cosine
must reach 0.45, combined score 0.35. Calibrate these conservative defaults on approved
operational fixtures before activation; they are not proof of causality or action safety.
Duplicate normalized chunk content is suppressed and citations bind content, not rank.

## Privacy, status and local use

`concept-v1` remains the default: a small fixed concept vocabulary, **not** pretrained
semantic inference. `lexical` is an explicit alternate mode. `pretrained-onnx` means the
local pretrained query encoder and verified index were used. `no_match` retains the
configured backend; `unavailable` means validation/runtime failure. There is no silent
fallback or semantic success claim on a failed encoder. Empty/non-token queries do not
invoke the encoder. Errors expose no raw paths, secrets, query text or model exceptions.

Reviewed document hashes and scopes are primary controls. Obvious instruction override,
credential material and role delimiters are rejected as defense in depth. A pattern
filter is not a general proof of safe text; stronger protection is structural: retrieved
prose is never executed, sent to Gemini or parsed into actions. Only reviewed fixed signal
tags can prioritize catalog rows already supported by fresh trusted telemetry. Unknown
telemetry and rejected effects cannot be resurrected by runbooks. Citation lists are
validated against the actual local retrieval. Existing PE/independent execution checks
remain authoritative; local runbooks never grant approval or execution rights.

## Verification gates

The socket-disabled offline suite includes deterministic lexical/concept quality fixtures,
synthetic semantic adapter/index contracts, citation/dedup/context bounds, scope and
integrity failures, privacy and rejection suppression. Synthetic vectors are not proof
of pretrained quality. After supplying approved local artifacts/dependencies, run
`AI_TEST_LOCAL_EMBEDDINGS=1` with the offline test runner for the real encoder paraphrase
smoke gate; extend quality evaluation with reviewed incident/runbook examples and
irrelevant negatives on the actual artifact. No model or dependency download occurs in
that runner. Load, RSS, CPU, concurrency, tokenizer/pooling equivalence, ARM/x86 wheel
compatibility and accuracy must be verified in release CI before activation. All existing
PostgreSQL, promtool, provider, workload/network and production gates remain applicable.
