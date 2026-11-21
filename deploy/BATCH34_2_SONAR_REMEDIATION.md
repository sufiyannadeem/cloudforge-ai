# Batch 34.2 — remaining SonarCloud findings

Baseline PR #50/head `28ba0460018eec2842734f647b85976fe3e6334e` was re-read via
SonarCloud issue/dataflow/duplication APIs: the same nine issue keys remain OPEN.
Security E, reliability A, duplication 3.0211539979477466% (1,531/50,676 lines).
No settings, issue statuses, suppressions, exclusions or thresholds were changed.
No push or PR mutation was performed. Local dispositions below are not hosted
scanner closure or live cluster/AWS acceptance.

## Exact findings and local dispositions

Locations refer to that baseline, before this commit's line shifts.

| Issue key | Rule / severity | Baseline location | Disposition and evidence |
| --- | --- | --- | --- |
| `AaH6QWyusU18O1jEplCW` | pythonsecurity:S8707 / MAJOR | scripts/release-images.py:196 | Local remediation: argparse source at 190 formerly reached `args.manifest.read_text()`. Inputs now become parsed JSON objects through `review_workspace.read_review_json`: anchored directory descriptors, no-follow components/files, regular-file/size checks and bounded reads. File content cannot select a pathname. CLI traversal/symlink/size/FIFO regressions and release signature/provenance tests pass. Hosted confirmation pending. |
| `AaH6QWypsU18O1jEplCK` | pythonsecurity:S8707 / MAJOR | scripts/prepare-node-autoscaler.py:91 | Local remediation: actual reported flow is parse_args at 88 to **output_dir.mkdir**, not an input read. Output is constrained to a regex-validated single new child of the private review cwd; mkdir is exclusive and mode 0700. JSON config separately uses the descriptor reader. Valid offline preparation and overwrite/escape regressions pass. Hosted confirmation pending. |
| `AaH6QWyjsU18O1jEplCJ` | pythonsecurity:S2083 / BLOCKER | scripts/test-release-signatures.py:53 | Local correction plus reproducible safe-fixture evidence: former `bundle=json.loads(...)` at 48 reached fixed `attestation.json.write_text(...)` at 53. The caller creates a private TemporaryDirectory; no field selects a filename. The helper now serializes data through a stream opened exclusively at fixed `tampered-attestation.json`, preserving the original signed bundle. Traversal-like payload values remain JSON data; input/output symlink probes cannot overwrite protected files. Real pinned Cosign drill rejects the changed signed claim. No false-positive transition was made; hosted rule review remains necessary. |
| `AaH6QWyssU18O1jEplCM` | python:S5332 / MINOR | scripts/render-kubernetes.py:176 | Local remediation: production Prometheus URL must be an explicitly reviewed Service HTTPS origin, with mounted CA trust and actual pod targetPort. No generated HTTPS URL or HTTP fallback. Python/Node real local TLS tests verify trusted success and untrusted/wrong-host rejection. Cluster listener/cert/CNI acceptance remains blocked. |
| `AaH6QWyssU18O1jEplCN` | python:S5332 / MINOR | scripts/render-kubernetes.py:176 | Same Prometheus trust boundary and tests as CM; separate scanner issue retained in this inventory. No TLS verification bypass or issue suppression. |
| `AaH6QWyssU18O1jEplCO` | python:S5332 / MINOR | scripts/render-kubernetes.py:189 | Local remediation: Grafana URL must be an explicitly reviewed Service HTTPS origin and trusted CA bundle; frontend health fetch rejects redirects. Actual Grafana native HTTPS/certificate installation is an external prerequisite, not claimed complete. |
| `AaH6QWyssU18O1jEplCP` | python:S5332 / MINOR | scripts/render-kubernetes.py:189 | Same Grafana trust boundary as CO; separate scanner issue retained. Renderer tests reject HTTP, foreign hosts, credentials, query selectors, missing CA and invalid target ports. |
| `AaH6QWy0sU18O1jEplCf` | kubernetes:S6865 / MAJOR | deploy/kubernetes/cloudforge-secrets-example.yml:385 | **Unresolved external evidence/review gate.** API token is required by the real executor. The companion project-deployment-rbac-example.yml binds exactly cloudforge/cloudforge-deployment-service to a namespace Role in cf-PROJECT_UUID, not a ClusterRoleBinding; negative permission assertions exclude Secrets, exec, nodes, namespaces, RBAC mutation, wildcards and deletion. Optional Argo permissions are separately namespace-bound. No installed namespace/RoleBinding/API audience evidence is available under the no-cluster-access constraint. Token remains; no workaround removes detection or broadens permissions. |
| `AaH6QWxBsU18O1jEplB5` | typescript:S1313 / MINOR | frontend/src/lib/infrastructure-form.ts:29 | **Unresolved maintainer evidence assessment.** The literal is an RFC1918 IPv4 VPC form default, not a socket/URL or credential. Existing frontend tests serialize it only as cidr_block and reject invalid CIDRs; backend generator parses IPv4 CIDR and constrains /16–/28. Actual network availability/overlap needs approved account/project evidence before apply. No false-positive disposition was assumed or requested. |

## Transport implementation and limitations

`monitoring_tls` production inputs are mandatory: reviewed Prometheus/Grafana
HTTPS origins in monitoring_namespace, their actual **pod** TLS targetPorts and an
approved CA ConfigMap. Service port and targetPort are allowed to differ; policies
use the latter. CA mounts are read-only; Node receives NODE_EXTRA_CA_CERTS and
Python/Go receive SSL_CERT_FILE before process startup. Supply a complete trusted
PEM bundle, including necessary public roots. CA rotation requires reviewed client
restart/reload; a test initially changing CA variables after client initialization
was corrected to start a fresh process, matching workloads.

Production Python monitoring rejects HTTP and redirects. Frontend monitoring and
health fetches reject redirects; the Go metrics client already did so. Local
HTTP development is unchanged. No verify=False, CERT_NONE, insecure Node TLS flag,
or replacement of native TLS servers with fictitious HTTPS URLs was introduced.

Enable real native Prometheus/Grafana TLS in the existing monitoring installation
and verify SANs, CA trust, certificate/key permissions, Service targetPorts and CNI
policies before deployment. Inputs contain no fabricated certificates/credentials.
Other existing service HTTP links are outside these four findings; this is not an
all-service TLS or production-readiness claim. See [transport prerequisites](kubernetes/README.md#monitoring-transport-prerequisite).

## Duplication

The exact remaining duplicated fixture blocks at
`app/test_ai_evidence_package.py:14+66` and `app/test_ai_tools.py:10+66`
were compared byte-for-byte and extracted to one shared, explicitly test-only
`app/test_ai_fixtures.py`. All original assertions remain in their original tests.
No source/test exclusions or nonfunctional padding were added. This removes the
large repeated block rather than narrowly targeting the minimum line count.
Hosted duplication percentage and any additional overlaps require separately
authorized reanalysis; no local sub-3% measurement is invented.

## Local verification

- Root focused release/CLI/rendering/CI/RBAC checks: **143 passed**, one unrelated
  Terraform init/validate wrapper deselected (no Terraform files changed).
- Loopback-only real TLS: **6 passed**. Python and Node accept configured trust,
  reject untrusted/wrong-host certificates, and reject monitoring downgrade
  redirects; development HTTP remains usable.
- AIOps evidence, guardrail, signed telemetry, SLO and readiness tests: **55 passed**.
  FinOps readiness/cost/optimization tests: **17 passed**.
- Frontend: **six test files passed**, including roles, CSRF, signed telemetry,
  guided resource forms, reliability and explicit redirect/unavailable handling.
  TypeScript and changed-file ESLint passed.
- Existing offline Cosign v3.1.4 drill: **PASS** for valid signature/attestation and
  rejection of changed bytes, wrong key and changed signed provenance. Official
  release bytes matched SHA256
  `424e2c97d0b45fd7a6b608a87f090f35633f4c23ece5f092d48bba11aaf4bbfa`;
  temporary fixture signing keys were removed. Offline-only transparency flags
  remain confined to that existing fixture; production verifier is unchanged.
- Trivy configuration: **0 HIGH/CRITICAL**, using current cached/embedded rules
  and unchanged exact-path project-RBAC exceptions. No image CVE acceptance is
  inferred; no dependencies or base images changed.
- Python syntax, staged Gitleaks and git diff --check passed. No full build,
  cloud call, cluster access, deployment or hosted Sonar upload was performed.

Reproduce the local evidence from the repository root:

```sh
pytest -q tests/test_review_workspace.py tests/test_release_signature_fixture.py
pytest -q tests/test_monitoring_tls.py  # opens disposable loopback listeners only
python3 scripts/test-release-signatures.py --cosign /path/to/reviewed/cosign
```

## Remaining gates

1. Separately authorized hosted CI/Sonar reanalysis of this local commit; verify
   exact remaining issue flows, security rating and duplication. All nine current
   remote issues remain OPEN until that occurs/review is completed.
2. Approved real monitoring TLS servers, CA material, mappings and CNI acceptance.
3. Installed project-scoped RoleBinding/token evidence and maintainer assessment
   of the test-fixture/CIDR findings. Do not dismiss findings just to pass a gate.
4. Approved network/project CIDR availability and broader platform/cloud acceptance.
