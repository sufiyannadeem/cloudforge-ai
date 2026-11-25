# Offline semantic release inputs

A verified glibc base candidate and pinned model sources are now recorded in
`ci/integration-acquisition.json`, with human approval still pending. The current
hosted prepare/verify sequence is documented in `docs/GITHUB_HOSTED_VERIFICATION.md`.
No production image approval or generated wheel/model candidate is invented.
`Dockerfile.rag` requires a separately reviewed **glibc Python 3.12** base pinned by
SHA256. Existing inference packaging stays separate and receives no knowledge/model.

Supply `AIOPS_GLIBC_BASE=image@sha256:...`, the approved offline `RAG_WHEELHOUSE`
containing **all operational and embedding transitive wheels**, and a new output lock:

```sh
PIP_NO_INDEX=1 .venv/bin/pip-compile --no-index --find-links "$RAG_WHEELHOUSE" \
  --generate-hashes --allow-unsafe --no-emit-index-url \
  --output-file "$RAG_EMBEDDING_LOCK" services/aiops-service/requirements-embeddings.txt
```

Review/sign the lock and set `RAG_EMBEDDING_LOCK_SHA256`. The packaging gate uses
`pip install --dry-run --ignore-installed --no-index --only-binary=:all: --require-hashes`
to verify actual wheel resolution for both locks. No wheelhouse was supplied locally;
no generated wheel-hashed candidate exists locally. The verified base candidate
digest is in the acquisition lock, not a built/scanned semantic application image.

After that gate passes, an independently authorized release build can use:

```sh
docker build --network=none --pull=false --build-arg AIOPS_GLIBC_BASE="$AIOPS_GLIBC_BASE" \
  --build-context rag_wheels="$RAG_WHEELHOUSE" \
  --build-context rag_lock="$(dirname "$RAG_EMBEDDING_LOCK")" \
  -f services/aiops-service/Dockerfile.rag services/aiops-service
```

The lock build context must contain `requirements-embeddings.lock`. Base image must
already be cached; verify its platform, interpreter, glibc, OS libraries and package
manager utilities. Build/scan/SBOM/signing and final immutable image selection remain
independent existing release gates, not implied by a passing dry-run dependency check.

Use the model/index preparation and independent manifest hashes described in
`docs/PRODUCTION_SEMANTIC_RAG.md`. Run `scripts/verify-rag-release.py benchmark` with
all pinned model/corpus/index variables, `AI_EMBEDDING_MODE=pretrained-onnx`, and reviewed
`RAG_MAX_RSS_MIB` / `RAG_MAX_P95_MS`. Run under EKS-equivalent CPU/memory cgroup limits.
This is local embedding inference only, no Gemini/AWS/network calls. The gate rejects
missing artifacts, irrelevant matches, failed paraphrase quality or resource overruns.
No benchmark has run without the required approved artifacts.
