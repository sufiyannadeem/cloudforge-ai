# Consolidated verification commands and prerequisites

The newer [GitHub-hosted workflow guide](GITHUB_HOSTED_VERIFICATION.md) adds CI-only
reviewed acquisition and ephemeral synthetic PostgreSQL. The commands and earlier
local blockers below remain valid; source preparation does not resolve them.

Release verdict remains **NO-GO**. A passing source test is not evidence of real
PostgreSQL locking/ACLs, PromQL semantics, Kubernetes admission or workload isolation.
All prior gates in PROJECT_STATUS.md remain mandatory. This batch performs no database
provisioning, cluster startup, model download, image build, AWS/provider call or remote
workflow dispatch. An initial broad Terraform test attempted registry discovery and
failed without downloading a provider; it was corrected to require an offline mirror.

## Locally verified

```sh
services/aiops-service/.venv/bin/python scripts/test-secure-ai-offline.py
python3 -m pytest tests -q --ignore=tests/test_monitoring_tls.py
python3 scripts/verify-consolidated-release.py native
```

The native gate runs cached Helm lint/template with reviewed vendored LBC values
and explicit **offline fixture** cluster/region/VPC values; it never contacts AWS.
It builds an isolated Kustomize directory from existing workload/services/inference
manifests and applies the exact AIOps strategic patch. Neither command applies objects.
Missing tools/schemas are BLOCKED with nonzero status, not replaced by synthetic schemas.

Frontend checks (from `frontend/`):

```sh
node --test tests/auth-csrf.test.mjs tests/inference-status.test.mjs \
  tests/remediation-review.test.mjs tests/trusted-evidence.test.mjs
./node_modules/.bin/tsc --noEmit
./node_modules/.bin/eslint src/lib/csrf.ts
```

Production rejects the loopback HTTP exception even with `CLOUDFORGE_LOCAL_DEV=true`
and always marks authentication cookies secure. Explicit localhost HTTP still works
under a development runtime. Do not use production NODE_ENV as a local security bypass.
Service identity and deployment Go tests use `GOPROXY=off GOTOOLCHAIN=local` with an
already cached Go 1.26 toolchain. No compiler/module download is permitted.

## Native Prometheus and schema gates — BLOCKED

Supply an already cached Prometheus `promtool` (target v3.5.0-compatible) on PATH or
`PROMTOOL=/absolute/path/promtool`, then rerun the native gate. Exact native operations:

```sh
promtool check config --syntax-only monitoring/prometheus/prometheus.yml
promtool check rules monitoring/prometheus/rules/*.yml
# Run from each fixture's directory, including the nested tests/ directory:
promtool test rules project-evidence.test.yml
# Also availability-burn, rollout-analysis, slo-evidence, recovery-alerts, drift-alerts.
```

Supply cached `kubeconform` or `KUBECONFORM`, plus
`KUBERNETES_SCHEMA_LOCATION=/absolute/approved/schema-bundle/<local-template>`.
The bundle must include Kubernetes 1.35.0 **and** Argo Rollouts/CSI custom resource
schemas. The native gate invokes `kubeconform -strict -summary -kubernetes-version
1.35.0 -schema-location "$KUBERNETES_SCHEMA_LOCATION" <native renders and Rollouts/RBAC
manifests>`. Missing schemas are errors: no ignore-missing or remote default fallback.
Reviewed production replacements must also be validated before release; unbound example
values and offline fixture names do not constitute a release configuration.

Actual admission, service-account/IAM permissions, FQDN egress and policy enforcement
remain separate live release gates. Source checks cannot establish those properties.

## Real PostgreSQL — default hosted path, execution pending

Local PostgreSQL provisioning is **not required**. The default GitHub-hosted workflow
selects the verified PostgreSQL 16 digest and creates three new disposable synthetic
test databases and unprivileged roles on its ephemeral service. Existing exact-name,
empty-database and schema-reset-consent guards remain. Follow
[GITHUB_HOSTED_VERIFICATION.md](GITHUB_HOSTED_VERIFICATION.md) for the approved sequence.

The real suites are still unexecuted here: eight Python migration/ACL/ownership/ledger/
import/rejection/claim tests plus native Go atomic dispatch must actually pass with no
skips. Hosted CI supplies all DSNs itself; do not enter application/production secrets.
The prior skipped results below/elsewhere are not retroactively passing results.

Optional dedicated runners retain explicitly supplied empty `cloudforge_inference_test`,
`cloudforge_remediation_test`, `cloudforge_release_test` and their existing local-host
checks. Use only isolated CI settings, with precreated roles/pgcrypto and explicit
`RELEASE_TEST_ALLOW_SCHEMA_RESET=yes-disposable-public`; these are an optional dedicated
runner prerequisite, not a request to provision a local database in this batch.

## Semantic packaging, artifacts and measurements — BLOCKED

See [release packaging inputs](../deploy/release/rag/README.md) and
[model/index preparation](PRODUCTION_SEMANTIC_RAG.md). Required inputs include an approved
actual glibc Python base **digest**, complete platform wheelhouse, generated/reviewed
transitive wheel-hashed embedding lock, independent lock SHA256, pinned reviewed
model/corpus/index artifacts and hashes, and reviewed resource thresholds.

```sh
services/aiops-service/.venv/bin/python scripts/verify-rag-release.py packaging
services/aiops-service/.venv/bin/python scripts/verify-rag-release.py benchmark
```

The first resolves both operational/embedding locks offline with pip --require-hashes;
the second measures real local pretrained retrieval quality, irrelevant negatives,
RSS and query latency with sockets disabled. No mock/concept backend qualifies. Run
under reviewed EKS-equivalent CPU/memory cgroup limits. No wheel hashes/base digest/model
or benchmark numbers were fabricated. Dockerfile.rag is digest-required packaging source,
not an already built/scanned approved image. The inference worker remains unchanged.

## Manual release CI

The consolidated workflow now supports hosted ephemeral PostgreSQL/native acquisition
and the retained preprovisioned dedicated path. Semantic verification is a separate
manual workflow with its own protected environment. See
[GITHUB_HOSTED_VERIFICATION.md](GITHUB_HOSTED_VERIFICATION.md) for the current exact
settings, source/artifact approvals and execution sequence. No workflow was dispatched.
Require both `integration-verification` and `semantic-gate` for the exact approved
source revision; administrators must configure those protection settings independently.
Workflow presence alone does not authorize publishing or establish runtime success.
The existing image-release matrix still selects the original Alpine AIOps Dockerfile;
a reviewed release change must select Dockerfile.rag and its verified build contexts
before claiming that published AIOps images support pretrained semantic retrieval.

Other unresolved gates: production TLS/IAM/RDS identities, complete historical ledger
import/finalization, trusted telemetry rollout, model/free-tier/terms availability,
FQDN-capable network enforcement, signed immutable image/SBOM provenance and current
clean independently approved release source. No automatic paid fallback is introduced.

TLS listener regression tests currently fail to create AF_INET sockets in this sandbox
(1 failure, 5 setup errors, all PermissionError). Rerun `python3 -m pytest
tests/test_monitoring_tls.py -q` on an approved runner with loopback listener permission;
do not replace that evidence with a mocked TLS success. Terraform validation requires
`TF_OFFLINE_PROVIDER_MIRROR=/absolute/cached/provider-mirror`; its test explicitly disables
registry fallback and reports a skip when missing. Native schema/tool tests likewise
remain explicit skips in the general source suite and nonzero blockers in release gates.
