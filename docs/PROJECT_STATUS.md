<!-- Current schema/acquisition hash revision: see HOSTED_VERIFICATION_SECOND_RUN_FIX.md; separate human approval pending. -->
# CloudForge AI implementation status

Final pre-CI review: see [PRE_CI_SOURCE_REVIEW.md](PRE_CI_SOURCE_REVIEW.md). The
[solo-developer exception](GITHUB_HOSTED_VERIFICATION.md#solo-developer-self-approval-exception--synthetic-ci-only)
permits explicit hosted synthetic-CI self-review only; independent production release
and fresh PE approval remain mandatory. No approval or CI execution is recorded by this note.


Updated: 2026-11-25. Current batch: Resolve CI Acquisition Prerequisites.
Prior workload-isolation implementation and all unresolved production gates are retained.

Implementation is connected locally; production activation remains fail-closed.
No Kubernetes, full-stack startup, downloads, AWS calls, live inference, image build,
push or deployment was performed. Existing unrelated working-tree edits were preserved.

## Current batch: Resolve CI Acquisition Prerequisites

**Verified inputs and executable source paths; HUMAN APPROVAL / CI EXECUTION PENDING.**
No workflow dispatch, push, database startup, Kubernetes, AWS, image build, model-weight
fetch, inference or deployment occurred. Only small public metadata/schema sources and
checksum-verified 2.3MB actionlint were retrieved; no heavy local artifacts were fetched.

| Gate/input | Result this batch | Remaining dependency |
| --- | --- | --- |
| Native tools, URLs and independent publisher checksums | VERIFIED METADATA | Prometheus 3.5.0, kubeconform 0.6.7, Helm 3.20.0, kubectl 1.35.0, Terraform 1.17.2, Go 1.26.11, actionlint 1.7.12 resolved in active lock. Full binaries except small actionlint remain CI acquisitions. |
| Official PostgreSQL/Python OCI pins | VERIFIED METADATA | PostgreSQL 16-bookworm and Python 3.12-slim-bookworm linux/amd64 child digests recomputed from registry manifests; no layers fetched or database/image started. |
| Terraform and Python dependencies | VERIFIED METADATA | AWS provider 6.66.0 published linux/amd64 checksum matches both existing locks. All 34 runtime/test lock entries have an approved compatible wheel in official PyPI metadata; eight bootstrap tool hashes checked. Actual CI installs/resolution remain unexecuted. |
| Rollouts/CSI schema inputs | VERIFIED SOURCE DERIVATION | Rollouts 1.10.2 and CSI 1.6.2 pinned commits/upstream CI include Kubernetes 1.35.1. Pinned Kubernetes 1.35.0 OpenAPI plus official/vendored CRDs deterministically produce 314 strict standalone schemas; expected manifest pinned. Live compatibility/CEL/admission remains unverified. |
| Acquisition approval | PENDING HUMAN | Active `ci/integration-acquisition.json` is populated but keeps `reviewed_by=null` and verified/pending status. Protected-environment `CI_ACQUISITION_APPROVED=true` plus independent exact lock hash and real required-review protection are mandatory; no review identity fabricated. |
| Workflow syntax/mechanics | PASS (LOCAL LIGHTWEIGHT ONLY) | Official-checksum actionlint 1.7.12 accepts both workflows after quoted port-map keys/custom runner label fixes. Bash/Python/job-reference inspection passed; **9 gate-mechanics tests passed**. These are not real integration results. |
| Same-SHA release evidence | SOURCE READY / UNEXECUTED | Semantic preparation and verification check successful exact integration workflow/run/attempt/repository/SHA via read-only API. Verification additionally binds exact preparation run and independently approved inner candidate hash. Preparation emits `candidate-preparation-only`, never the required `semantic-gate`. |
| Hosted semantic artifact preparation | SOURCE READY / UNEXECUTED | Separate approved prepare operation acquires pinned MiniLM ONNX/tokenizer/license, hash-locked bootstrap/wheels and committed synthetic-only corpus; reuses existing artifact/index scripts. Candidate storage expires in three days. No model/export/index/benchmark ran locally. |
| Real PostgreSQL/native Prometheus/Kubernetes/Terraform/TLS/RAG integration | NOT EXECUTED / RELEASE BLOCKED | Default hosted CI supplies its own ephemeral synthetic PostgreSQL; **local PostgreSQL provisioning is no longer a prerequisite**. Manual approvals/settings and actual successful same-SHA CI runs are required; all prior skipped integration evidence remains unresolved until run. |

### Corrected defects and boundaries

- Removed the unpublished schema-bundle prerequisite: existing acquisition now derives
  and verifies the complete expected bundle from official hash-pinned metadata sources.
- Corrected kubeconform local path handling (`file://` is not supported by pinned 0.6.7),
  made filenames group-aware, and moved hash-locked Python/PyYAML setup before generation.
- Corrected numeric PostgreSQL port-map keys rejected by actionlint and declared the
  retained dedicated runner labels. Archive format/path/link mechanics are covered.
- Added protected hosted candidate preparation, actual independent candidate hash approval,
  exact run/attempt/SHA binding and no auto-latest artifacts. No automatic reviewer name,
  model export, private corpus upload, provider call, paid fallback or execution API.
- Source model pin: MiniLM `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, ONNX publisher
  SHA `6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452` (90,405,214 bytes).
  Weights remain unfetched locally. Preparation uses `ci/semantic-corpus` synthetic data
  only; actual human/license/corpus review statements remain operator inputs.
- Strictly read-only AI, project isolation, current PE approvals/rejections, rejected
  effects, immutable contracts, aggregate-only Gemini disclosure, free-only default,
  durable ₹360 cutoff and ₹400 maximum remain unchanged. Production image build/scan,
  actual OS library compatibility, IAM/TLS/network/provider/import gates remain.

### Exact next operator actions

1. Review final source and [resolved lock](../ci/integration-acquisition.json) against
   [public evidence](../ci/acquisition-evidence.json); configure eligible protected
   GitHub environments/reviewers and required same-SHA status checks. No settings changed.
2. After real human review only, bind lock SHA
   `8f73972d01681d32e3c3e817fc176dc15b19bb93893da1bfab8578fa2846759e`
   and explicit approval in the three environments described in the guide.
3. At final SHA S, manually run hosted integration; then separately approved semantic
   `prepare` with that successful run/attempt; independently inspect/hash the retained
   candidate; finally run semantic `verify` at S with both exact run/attempt bindings.
4. Check actual plan/required-review capability, remaining Linux minutes, artifact
   storage and registry/network quotas before running. Preparation is not semantic
   verification and cannot satisfy its required status. No workflow has run here.

Current commands, approval variables, quota estimates and execution order:
[GITHUB_HOSTED_VERIFICATION.md](GITHUB_HOSTED_VERIFICATION.md).
All historical production blockers and skipped test results are retained below as
history; hosted CI supersedes old default instructions to provision local databases.

## Prior batch: GitHub-Hosted Integration Verification

**SOURCE PREPARED ONLY — UNEXECUTED. Release remains NO-GO.** No local tool/model
installation/download, database/Kubernetes startup, workflow dispatch, AWS operation,
image build, push, publishing or deployment occurred in this batch. Earlier PASS
counts below belong to earlier batches; no new integration success is claimed.

| Verification path | Prepared source | Execution / remaining prerequisite |
| --- | --- | --- |
| Hosted isolated PostgreSQL | Ephemeral digest-selected PostgreSQL 16 service, synthetic credentials/data, three exact dedicated test databases, unprivileged NOLOGIN roles and pgcrypto bootstrap; existing disposable-schema guards retained. | UNEXECUTED. Requires reviewed image digest/acquisition lock and approved manual workflow run. No production secret or database default. |
| Real migration/ACL/ledger/rejection/dispatch gates | Reuses eight actual Python database cases and required native Go dispatch case; skip/count/PASS checks remain mandatory. | UNEXECUTED; no mocked integration substitute. |
| Native Prometheus/Kubernetes/Helm/Terraform/TLS | CI-only SHA/version-verified tools, strict standalone schema bundle, lockfile-verified provider mirror; seven real Terraform/TLS cases must pass with no skips. | UNEXECUTED. Actual independent tool/schema checksums, Rollouts/CSI versions and schema bundle still need review. |
| Dedicated runners | Existing cached native, isolated DB and private artifact paths retained under `runner_profile=dedicated`; ambient application/cloud credentials rejected. | Requires preprovisioned clean dedicated runners and isolated-only settings. No hosted bootstrap/acquisition in this path. |
| Separate semantic verification | New manually triggered workflow with independent semantic environment approval, reviewed model/index/wheel bundles, hash-required offline resolution/install, real quality/RSS/p95 and one-core/time/virtual-memory bounds. | UNEXECUTED. No model export/automatic index regeneration or paid/provider inference. Public/synthetic global corpus only on hosted runners; private knowledge stays on approved dedicated mounts. |
| Approval/status/settings | `integration-verification` rejects active-job skips; separate `semantic-gate` always rejects skipped/failed semantic jobs. Both workflows contents:read only, pinned checkout, no OIDC/publish/deploy permissions. | GitHub administrators must configure protected environments and require both statuses at the same reviewed source SHA. No settings or workflow run changed remotely. |

### Prepared source and unresolved inputs

- `.github/workflows/consolidated-release-verification.yml` now defaults to hosted
  Ubuntu 24.04 with an explicit hosted/dedicated choice. Protected preflight validates
  the service image before the PostgreSQL job can start. Hosted tools are acquired
  only by a GitHub-hosted CI guard; local execution is refused.
- `.github/workflows/semantic-release-verification.yml` is separately dispatched and
  approved. Its result is independently required; a green base integration run is
  not a complete release verdict. Private/customer/operational data, rejection history,
  production secrets and AWS credentials are not hosted CI inputs.
- `ci/integration-acquisition.template.json` is intentionally **UNBOUND**: no guessed
  hashes/digests or fabricated review. A reviewed `ci/integration-acquisition.json`
  plus independently approved `CI_ACQUISITION_LOCK_SHA256` is required before hosted
  jobs can acquire anything. Tools, providers, schemas and artifacts have no floating
  checksum fallback. All existing security/disclosure/approval/budget controls remain.
- Added guarded acquisition/bootstrap/native-test scripts and updated gate-mechanics
  regression source. No test suite, acquisition, PostgreSQL or benchmark was run here.
  Source syntax inspection is not native tool/database/CI verification.
- Planning estimate only: **9–22 Linux runner-minutes** for integration, plus **5–15**
  for the separately approved semantic run; actual usage/compatibility is unmeasured.

Exact GitHub settings, artifact layouts/pins, safeguards and execution order:
[GITHUB_HOSTED_VERIFICATION.md](GITHUB_HOSTED_VERIFICATION.md).
Next dependency: independently review acquisition/image/schema/model/wheel inputs and
GitHub environments, then an operator may manually run integration followed by semantic
verification on the same reviewed revision. All prior PostgreSQL, promtool, actual
packaging, live identity/network/provider and production release blockers remain until
corresponding real evidence is obtained. No prior skip is converted to PASS by source.

## Prior batch: Consolidated Integration & Release Verification

**Release verdict: FAIL / NO-GO.** Mandatory integration evidence is still blocked.
PASS below means only the stated check passed, not that deployment is authorized.
No feature expansion, database provisioning, cluster/model startup, image build,
AWS/provider call, remote workflow dispatch, push or deployment was performed.

| Release gate | Status | Verified evidence / blocker |
| --- | --- | --- |
| Secure AI, retrieval, telemetry, authorization and approval offline contracts | PASS | Socket-disabled runner: **228 passed, 6 skipped**; retained PostgreSQL/promtool/real-model skips remain blockers below. |
| Cross-service/source configuration, vendored inventory, RBAC, network-policy and Rollouts contract checks | PASS | System cached Python source suite: **246 passed, 2 skipped** excluding TLS listener module. Two skips: offline Terraform mirror and independent native tool/schema bundle. Synthetic source fixtures do not prove live enforcement. |
| Native vendored Helm lint and template | PASS | Cached Helm 3.20.0, reviewed LBC values, explicit offline fixture cluster/region/VPC; no installation or AWS call. |
| Native Kustomize inference integration | PASS | kubectl 1.35.0 / Kustomize 5.7.1 rendered existing base, Services, inference/CSI manifests and exact AIOps strategic patch; confirmed one matched AIOps container with Gemini internal integration. |
| Kubernetes 1.35 / Argo Rollouts / CSI independent schema validation | BLOCKED | Cached kubeconform and approved offline built-in/CRD schema bundle absent. Rendering and source assertions are not admission validation. |
| Native Prometheus configuration/rules/all fixtures | BLOCKED | No cached promtool. No Docker/download fallback used; existing native rule skip preserved. |
| Real ownership, complete migrations, effective ACLs, review/advisory concurrency and replay | BLOCKED | No explicit empty `cloudforge_release_test` DSN, precreated service roles/pgcrypto or schema-reset authorization. Four newly prepared real integration cases explicitly skipped; no connection attempted. |
| Real inference ledger concurrency/rate/replay/history imports | BLOCKED | Retained four PostgreSQL integration tests skipped; no explicit empty `cloudforge_inference_test` DSN/server supplied. No reservations/imports/reset touched. |
| Native atomic deployment dispatch | BLOCKED | Tagged Go test explicitly skipped without empty `cloudforge_remediation_test`. Unit/repository compilation is not dispatch locking proof. |
| Deployment executor/metrics/handlers and service identity | PASS | Cached offline Go tests passed; repository/server compile; service identity tests passed with GOPROXY=off/GOTOOLCHAIN=local. |
| Production rejection of localhost-only exceptions | PASS | Corrected production localhost HTTP bypass; Secure auth cookies cannot be disabled in production. Four focused frontend files passed (including auth/CSRF, AI, review, evidence); TypeScript and focused ESLint passed. Development localhost HTTP retained. |
| Actual TLS CA/hostname/redirect listener integration | BLOCKED | Attempted listener module: **1 failure, 5 setup errors**, all AF_INET PermissionError in sandbox. No mocked TLS success substituted; rerun on permitted isolated runner. |
| Cached-only Terraform provider validation | BLOCKED | No offline provider mirror. Initial broad test attempted registry discovery and failed without provider download; corrected fixture now requires filesystem mirror and has no registry fallback. Formatting/source checks pass. |
| Digest-pinned glibc AIOps packaging and wheel hashes | BLOCKED | Added digest-required Dockerfile.rag, offline hash-resolution gate and exact lock-generation/build instructions. Actual approved base digest, complete wheels and reviewed transitive hash lock absent; no fake digest/lock/build/scan result supplied. Selecting this optional packaging in the existing image release process remains required. |
| Reviewed model/index integrity, real retrieval quality and resource benchmarks | BLOCKED | Added release gate for pinned artifacts/index, real paraphrase/retrieval negatives and measured RSS/p95 with sockets disabled. Approved artifacts/dependencies/resource thresholds absent; real model test skip retained. |
| Release CI activation/protection and current signed source/images | BLOCKED | Manual-only protected-environment native/DB/semantic jobs and all-success aggregator added, not dispatched. Dedicated runners, approvals, required-status settings and exact-revision binding remain administrator/release prerequisites. |
| Production IAM/TLS/RDS, FQDN egress, ownership/telemetry inventory, historical import, free-only Gemini terms/availability and final release approvals | BLOCKED | All previous independent production gates remain unresolved. Strictly read-only isolated AI, PE approval/rejection, rejected effects, ₹360 cutoff and immutable ₹400 maximum unchanged. |

### Corrections and prepared verification

- Production frontend no longer accepts HTTP loopback with the local-development flag
  and cannot issue insecure auth cookies when NODE_ENV=production. Development-only
  localhost behavior remains tested. No other approval/execution behavior changed.
- Consolidated native/DB gates return nonzero on missing prerequisites; real Python
  JUnit skips or native Go dispatch skips cannot qualify as a passing release gate.
- Added actual full-migration/role/store tests using real PostgreSQL only, with exact
  local database-name/emptiness checks and explicit disposable-public reset consent.
  They reuse production SQL and services, not invented mock schemas. All four are
  **unexecuted/skipped here**; their existence is not SQL/ACL/concurrency verification.
- Added manual-only `.github/workflows/consolidated-release-verification.yml`; no
  service/database provisioning or remote workflow execution. Existing release image,
  signature, human review and deployment approvals remain independent requirements.
- Added optional digest-required glibc release packaging and offline wheel/artifact/
  quality/resource CI checks. Missing real hashes/artifacts remain explicit blockers.
- Changed Terraform test to cached filesystem-mirror-only initialization rather than
  network provider discovery. No test now treats absent provider cache as validation.

Exact commands, prerequisites, isolated database safeguards and retry dependencies:
[CONSOLIDATED_RELEASE_VERIFICATION.md](CONSOLIDATED_RELEASE_VERIFICATION.md).
Next dependency: operator-supplied disposable PostgreSQL databases and cached native
validators/schemas, followed by approved glibc/wheel/model artifacts on reviewed runners.
All prior status sections and unresolved release gates are retained below.

## Prior batch: Production Semantic RAG

### Completed

- Added an optional local CPU ONNX sentence encoder for `all-MiniLM-L6-v2`, pinned
  to revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Reviewed model metadata
  declares Apache-2.0; license/notice retention and release-owner artifact approval
  are documented. Runtime requires separately pinned SHA256 manifests and reviewed
  local ONNX/tokenizer/license files. No Hub client, exporter, remote code, model
  download or pretrained model execution ran during this batch.
- Added offline artifact packaging and precomputed-index preparation tools. Indexes
  bind exact corpus/model manifests, content-derived citations, chunk hashes and
  finite 384-dimensional vectors. No vector database or runtime document embedding
  is required. One cached sequential CPU session/thread and nonqueueing capacity
  controls bound local inference; batch one, 256 tokens and 2,000 query characters.
- Implemented hybrid lexical/cosine relevance, semantic and combined thresholds,
  content deduplication, stable citations, five-hit/12,000-character context bounds
  and bounded document/chunk/index sizes. Long sections are split without dropping
  tails. Failed/stale/invalid artifacts return unavailable without silent fallback.
- Upgraded reviewed knowledge manifests with explicit document hashes, reviewers,
  project scopes and fixed signal tags. Existing global hash manifests remain
  compatible. Server-authorized incident/project scope precedes corpus reads; foreign
  documents are not read. Integrity, scope, symlink and obvious injection/credential
  checks fail closed. Reviewed hashes and structural nonexecution are primary controls;
  the text pattern filter alone is not a complete injection defense.
- Knowledge remains local. Gemini's aggregate-only DTO and isolated worker image,
  secrets, approval/authorization and telemetry boundaries are unchanged. Local
  runbook metadata can add contextual investigation hints and prioritize existing
  options supported by fresh trusted telemetry; it cannot invent evidence/actions,
  revive rejected effects or grant approval. Legacy provider prompt paths now also
  withhold runbook content; legacy unscoped enrichment no longer auto-loads a corpus.
- APIs/UI retain truthful `pretrained-onnx`, `concept-v1`, `lexical`, `no_match` and
  `unavailable` status. Concept mode remains the default and does not claim pretrained
  inference. Evidence options expose contextual citations separately from live facts.

### Verified offline results

- Socket-disabled focused runner: **228 passed, 6 skipped**. Added lexical/concept
  quality fixtures, synthetic semantic hybrid/index tests, irrelevant negatives,
  scope-before-read, artifact/index integrity and failure modes, citation/dedup/context
  bounds, offline preparation, privacy, CPU configuration, numerical mask/pooling validation
  and rejection suppression.
- Six skips are the retained four real PostgreSQL ledger tests, native promtool gate,
  and new opt-in real pretrained paraphrase test. Approved artifacts and optional
  runtime dependencies were not supplied. Synthetic vectors do not establish actual
  pretrained quality, pooling equivalence, RSS, latency or production concurrency.
- Five frontend test files passed, including local retrieval/citation/advisory status;
  TypeScript and focused ESLint checks passed. No live browser/full-stack test ran.

### Remaining blockers and next dependency

- Supply release-owner reviewed model/license artifacts and signed expected digests;
  prepare/review the matching corpus index in the approved build environment. Run
  real pretrained retrieval-quality, tokenizer/pooling equivalence and load/RSS tests
  on the chosen EKS CPU architecture before enabling `pretrained-onnx`.
- Optional dependencies are version-pinned but require a transitive wheel-hashed lock,
  scanning and a digest-pinned glibc operational AIOps image. The existing Alpine image
  is not semantic-ready. No image build, dependency installation or lock generation
  ran here. Keep the optional backend unavailable until packaging gates are satisfied.
- Mount immutable read-only artifacts/corpus/index and independently protect expected
  hashes. Resource proposal: 500m CPU/512Mi request, 1 CPU/1Gi limit, one process/Pod;
  this is an unmeasured starting allocation requiring production-hardware validation.
- All previous PostgreSQL migration/locking/ACL, promtool, trusted telemetry rollout,
  IAM/TLS/network, historical budget import, free-only provider/disclosure and release
  gates below remain unresolved. No database provisioning, Kubernetes, AWS, live
  inference, paid call, push or deployment was performed.

Preparation/configuration/resource details: [PRODUCTION_SEMANTIC_RAG.md](PRODUCTION_SEMANTIC_RAG.md).
Next dependency: reviewed local artifacts and glibc packaging, followed by real-model
quality/resource validation; PostgreSQL and all earlier release gates remain mandatory.

## Prior batch: Trusted Telemetry & Evidence-Based Safe Alternatives

### Completed

- Reused deployment-service DB ownership and live controller/ReplicaSet/Pod UID chains
  for authoritative resource/project mapping. Labels only corroborate ownership.
  Wrong revisions, ambiguous owners, replaced UIDs and host-network Pods fail closed.
  Dedicated bearer-file protected metrics are opt-in, bounded to 20 resources/five
  Pods per resource, with cache expiry, duplicate rejection and complete coverage.
- Added trusted CPU/memory pressure (90% of limits), explicit recent OOM, restart-loop,
  image-pull, configuration/scheduling failure and deployment-health observations.
  Missing limits, stale metrics and absent runtime evidence stay unknown. Deployment
  readiness is not external availability. No raw logs/messages/configuration are sent.
- Added project recording rules: UID joins, unique sources, finite values, timestamps,
  complete Pod/resource coverage and bounded HTTP windows. HTTP requires sufficient
  five-minute samples, explicit 5xx series (1% threshold) and latency buckets (95%
  within 500ms). Availability requires real probes. Dependency/SLO inputs require
  explicit approved health, coverage and timestamps; no evaluators are fabricated.
  Only existing latency/error/availability signals enter the unchanged Gemini DTO.
- Expanded the local evidence catalog with investigations and advisory remediation.
  Fresh project-bound validated stored AI citations may rank corroborated options;
  model prose never creates evidence/actions. No alternative calls inference.
  Unsupported scaling/restart/rollback/repair is advisory-only. Supported reruns
  require a verified pending target and fresh degraded deployment evidence.
  Acknowledgement is separately labelled workflow handling, not infrastructure repair.
- Reused incident authorization/locks, durable rejection families, immutable versioned
  contracts and independent fresh PE approval. Added append-only scoped advisory
  feedback; reasons/history remain internal. Generated infrastructure alternatives
  bind immutable parent evidence, rechecked at approval/claim and final dispatch.
  Feedback neither grants execution rights nor cancels already dispatched changes.
- Added evidence/status/citation and advisory rejection UI/API controls. Actual
  supported changes continue through existing proposal review and approval services.
  AI remains read-only with no additional workload permissions or disclosure fields.

### Verified offline results

- Socket-disabled secure AI runner: **203 passed, 5 skipped**. Four existing real
  PostgreSQL ledger tests remain skipped. Native promtool validation is the fifth
  skip because promtool is absent. New coverage includes provenance, stale/foreign/
  ambiguous evidence, disclosure, rejected effects, authorization and stale approvals.
- Go executor/metrics/handler tests passed; repository/server compiled. Tests cover
  UID/revision ownership, missing/stale metrics, inventory ambiguity/cache bounds and
  scrape authentication. A metrics test uses an isolated in-process HTTP recorder.
- Five frontend test files, TypeScript and focused ESLint checks passed.
- Rule structure/fixtures were checked offline; native PromQL/config validity is
  **unverified**. Docker inspection was unavailable; no container was started.
  No database, cluster, AWS, live inference, push or deployment was performed.

### Remaining blockers and next dependency

- Review/apply migration `006_advisory_feedback.sql` and grants
  `005_advisory_feedback_grants.sql` through the separate migrator. Run retained
  PostgreSQL ledger and tagged remediation concurrency/dispatch/ACL integration
  tests against preprovided isolated databases. No provisioning/migration ran here;
  fixtures do not prove real database locking or effective privileges.
- Run native promtool rule/config checks and supplied rule fixtures before release,
  then verify actual telemetry coverage, provenance and cross-project denial.
- Enable `PROJECT_EVIDENCE_ENABLED` only on the operational Kubernetes executor;
  supply dedicated `PROJECT_EVIDENCE_SCRAPE_TOKEN_FILE`, Prometheus bearer-file
  authentication and TLS/network controls. Scrape/RBAC examples remain unapplied;
  set exact approved namespaces/cluster and API-derived Pod UIDs. AI/frontend obtain
  no Kubernetes/scrape/execution rights. Use one authoritative producer per fleet;
  duplicates fail closed and fleets exceeding bounds require reviewed sharding.
- Supply real HTTP/probe sources and approved dependency/SLO evaluators. Unsupported
  telemetry remains unknown. All prior PostgreSQL, IAM/TLS, ownership, historical
  budget import, free-only provider/disclosure and production gates below remain.
  Next dependency: native rule validation and preprovided PostgreSQL verification,
  followed by reviewed telemetry rollout inputs.

## Prior batch: Human Approval, Rejection & Safe Alternatives

### Completed

- All assisted remediation previews, including workflow changes, now create expiring
  `PENDING_APPROVAL` versions; none auto-approve. Approval and execution require an
  active **Platform Engineer** with current project owner/maintainer access. SREs may
  propose, inspect and reject within their authorized projects, but cannot approve or
  execute. Proposers cannot approve their own recommendations; deployment requesters
  cannot approve their own high-risk deployment changes either.
- Added immutable recommendation versions, parent alternatives, authoritative project
  and incident/resource scope, normalized action-effect fingerprints, parameters,
  current-state snapshots and exact approved contracts. Fingerprints deliberately
  exclude prose and parameters/target substitutions; immutable versioned contracts
  separately bind the exact action/parameters/target/revisions/identity/policy/expiry.
- Rejection accepts an optional internal reason. An append-only review table records
  versions, reviewer identities, rejection history and execution claims in the same
  transaction as state changes. General incident timeline events do not receive new
  rejection reasons. Review and proposal reads are filtered by the current verified
  project binding; no rejection history enters inference requests.
- Rejected effects cannot be reworded or resubmitted with parameter/target-only edits.
  Suppression is rechecked at creation, approval and execution, including duplicate
  versions that existed before rejection. Restart/rerun share a conservative recovery
  effect family. There is no automatic rejection-history reset.
- Alternatives use a local deterministic policy catalog, **not a Gemini call**. An
  open, unacknowledged incident can support a materially different acknowledgement
  recommendation, explicitly labelled workflow handling rather than an infrastructure
  fix. It gets a new immutable version, new expiry and no inherited approval. If that
  effect was also rejected, the incident is already acknowledged/resolved, or no safe
  supported candidate exists, the result is investigation/escalation with no mutation
  recommendation. Unsupported restart/scaling/rollback execution remains blocked.
- Incident/proposal locking, unique incident versions, a scoped parent foreign key and
  one-child-per-parent constraint serialize alternatives and decisions. Repeated parent
  alternative requests return their recorded result instead of creating extra versions.
  Concurrent rejection cannot reopen or modify a claimed/terminal action.
- Before execution AIOps revalidates exact approved contract, scope, current incident
  and target state, active identities/memberships, independent approval, policy, expiry,
  parameters and idempotency. Deployment-service repeats the critical checks in its
  atomic one-time dispatch/queue transaction. A proof-gated definer function obtains the
  incident lock without granting deployment-service incident UPDATE authority.
- Acknowledgement is performed atomically by the existing authorized **operational**
  AIOps service with its approval/idempotency claim; it is not performed by the isolated
  AI workload. Infrastructure changes remain delegated to deployment-service. Cached
  same-key execution receipts cannot re-dispatch and are bound to the executing actor.
- Frontend has approve/reject, optional internal reason, alternative/investigation,
  version/scope/exact-state review and internal history controls. Approval and execute
  controls enforce PE/independence/expiry hints, with backend authorization decisive.
  Requests carry the exact displayed version/fingerprint and stable execution keys.
  The proxy also restricts approve/execute to PEs. Remediation POST assertions bind the
  complete body as well as target/identity/nonce; CSRF and localhost fixes are preserved.
- The inference image, role, Gemini disclosure DTO and free-only/budget policy are
  unchanged. No operational tools, approvals, rejection reasons or sensitive history
  are added to Gemini, its credentials, or its workload permissions.

### Current validation

- Socket-disabled focused Python runner: **181 passed, 4 skipped**. Includes 40 new
  review tests exercising the actual store/service and ASGI/middleware with isolated
  transactional fixtures: rejection, duplicate suppression, stale/self/SRE/viewer
  approvals, contract tampering, role revocation, final state checks, body substitution,
  replay, concurrent alternatives/claims/decisions, cross-project denial and privacy.
- Four frontend test files pass, including rendered review controls, private text
  escaping, PE/independence gates, version/key request contracts, proxy body signatures,
  CSRF and existing workflows. TypeScript and focused ESLint pass.
- Deployment-service repository/handler unit packages pass using the already cached
  Go 1.26.11 toolchain with proxy downloads disabled. The updated tagged deployment
  remediation integration test **skips** without an explicitly supplied empty local
  `cloudforge_remediation_test` database. No database was provisioned or contacted.
- The **original four PostgreSQL inference ledger tests remain skipped and unchanged**.
  Review concurrency fixtures serialize transactions in memory; they are not proof of
  PostgreSQL locking, trigger syntax/effectiveness, runtime ACLs or live service behavior.
  Those production gates remain unresolved. Focused whitespace checks pass.

### New migration/release gates (in addition to ALL retained blockers below)

1. In an authorized existing test environment, verify the review migration, immutable
   contract/lineage triggers, same-project parent constraints, SQL/Python contract
   equivalence, review/claim/reject concurrency, and effective runtime-role ACLs. Validate
   the real deployment dispatch integration test as well as the four existing ledger
   tests. **Do not provision a database as part of this batch.**
2. After existing deployment migrations (including strategy/requester provenance) and
   AIOps ownership migration 004, apply
   `services/aiops-service/migrations/005_remediation_reviews.sql` as the migrator and
   `deploy/postgres/004_remediation_review_grants.sql` as the DBA. These files were only
   authored here, never applied. Audit inheritance/PUBLIC/default/column grants too.
   Reapply the dedicated grants after any broad runtime-grant reconciliation.
3. Coordinate AIOps, deployment-service and frontend rollout; old clients cannot approve
   the new version-bound protocol. Drain/freeze legacy dispatches before migration.
   Legacy pending/approved version-0 records become expired, never grandfathered into
   new approvals. Legacy rejection history is reconciled only where authoritative
   incident ownership and actual deployment project scope agree; unprovable rows stay
   internal/unscoped. Existing records/reasons are retained, not fabricated or deleted.
   All subsequent alternatives require fresh current-state review and approval.
4. Do not treat acknowledgement as remediation of an outage. The currently controlled
   catalog has no alternate executable infrastructure fix after a rejected rerun.
   Additional infrastructure alternatives require independently implemented, approved
   execution APIs and policy/evidence rules; model suggestions cannot create those APIs.

**Next dependency:** authorized PostgreSQL migration/ACL/concurrency verification,
then the existing ownership, telemetry-provenance and workload/provider release inputs
listed below. No provisioning, live mutation, inference or deployment is authorized
by this batch. All previous production blockers are retained.

## Prior workload-isolation batch (retained implementation and release gates)

## Completed implementation

### Authoritative ownership and authorization

- Added explicit `aiops_incident_projects` migration, with foreign keys to existing
  incidents/projects and verification provenance. No automatic ownership inference
  or backfill from untrusted labels, annotations, service names or model output.
- Reused existing `projects.created_by`, `project_members` and active `auth_users`.
  Every incident intelligence/detail/timeline/remediation or incident action request
  verifies role, active server-side identity and project owner/member status before
  loading evidence. Unknown ownership, revoked users or unavailable authorization deny.
  No client-supplied membership or broad operator bypass authorizes AI evidence.
- Incident list/statistics queries apply the same membership predicate, preventing
  persisted AI from leaking through alternate APIs. Incident responses are no-store.
- Existing human approval, verification, execution separation and localhost/CSRF
  security controls remain intact. New authorization restricts access to owned projects;
  it does not grant AI any human approval or execution capability.

### Dedicated inference workload and authenticated boundary

- Added a separate inference FastAPI entry point and explicit-copy Dockerfile.
  The worker image excludes operational routes/stores, remediation/execution tools,
  knowledge files and legacy SQLite code. Its only application routes are health and
  fixed-contract inference. No operational mutation endpoint is exposed.
- AIOps delegates Gemini calls to the fixed HTTPS worker service. Internal requests
  reuse the existing assertion format and bind issuer/audience/method/target, body
  hash, nonce and short expiry. PostgreSQL atomically consumes the nonce with the
  budget reservation before provider I/O. No redirect, application retry or fallback.
- Worker rejects co-located business DSNs, execution/frontend credentials, static
  AWS credentials/profiles and alternate credential providers before ledger/AWS access.
- Added EKS worker/service/account/CSI manifests and exact-resource IAM/trust templates.
  No Kubernetes Secret sync, API service-account token, RBAC binding, host mount or
  execution credential is provided. Only an STS-audience projected token is mounted.
  Read-only root, non-root UID, dropped capabilities and resource limits are specified.
- API key, request-auth key and worker TLS certificate are separate, related Secrets
  Manager inputs. IAM is limited to their exact ARNs and the exact RDS inference user;
  AIOps must receive only the request-auth key, never the Gemini API key/worker TLS key.
  Base network policy denies external egress; provider disclosure defaults false.

### Evidence, Gemini, retrieval and frontend integration

- Authorization precedes a fixed project-scoped aggregate Prometheus query. Only
  exact project/signal labels, cardinality-one, finite 0/1 states and samples ≤120s
  old are accepted. Missing/stale/ambiguous/foreign samples remain unknown. No broad
  service telemetry is substituted. All-unknown evidence blocks provider requests.
- Only bounded, unique, fixed-vocabulary signal/state pairs reach Gemini. No project
  identifiers, raw logs, descriptions, credentials, customer data, configuration or
  documentation content is disclosed. Gemini 2.5 Flash is the approved configurable
  model; unsupported/unavailable models fail closed, with no model/provider/paid fallback.
- Strict enum-only diagnoses reject extra fields/actions, invalid/duplicate citations,
  contradictory healthy/degraded claims and unsupported evidence claims. Gemini and
  AIOps both validate. Validated results map into existing analysis/enrichment APIs;
  citations and retrieval metadata survive JSONB persistence and reload. Events record
  actual analysis status instead of claiming a blocked diagnosis was generated.
- Added explicit AI diagnosis UI action while preserving deterministic analysis.
  Reused the central CSRF request helper, bounded frontend/proxy/worker timeouts, and
  keyed incident state by ID to avoid stale evidence across navigation. UI labels
  provider/blocked/retrieval status and aggregate citations truthfully.
- Connected `concept-v1`, a small local operational semantic vocabulary/cosine backend
  with no downloads or embedding API calls. Synonym concepts cover latency, errors,
  availability, deployments and SLOs. Explicit `lexical` mode is separately labelled;
  unknown modes fail closed. This is limited domain semantics, not a trained general
  sentence encoder. The reviewed SHA-256 manifest allowlists knowledge files.
- Local semantic chunk citations are displayed as related contextual documentation;
  the provider never receives or claims to cite that documentation. Only supplied
  aggregate evidence indices become validated model citations. Retrieval remains
  bounded to five hits, 2,000 characters/chunk and 12,000 characters/context.

### PostgreSQL budget and legacy reservations

- Replaced the active SQLite reservation path with a narrowly granted PostgreSQL
  SECURITY DEFINER function. Runtime gets function execution only, not direct ledger
  updates, refunds, resets, incident data or other business-table access.
- Singleton row locking serializes concurrent-replica replay/rate/budget decisions.
  Fixed ₹1 conservative reservations commit before inference, five attempts/minute,
  lifetime ₹360 cutoff and immutable ₹400 maximum policy. Failed/uncertain attempts
  retain reservations. Account-side free-only controls remain required: reservations
  are conservative bounds, not token invoices or proof of provider billing settings.
- Added explicit read-only legacy SQLite import using stable source identity plus
  logical-row digest. It preserves amounts (including already exhausted balances),
  timestamps and zero-value attempts; retries are idempotent and altered snapshots
  reject. Import is DBA-only, with no runtime fallback. Reservations deny until an
  operator explicitly finalizes the complete historical import. No migration ran here.
- Added least-privilege PostgreSQL grants and checks for inherited/PUBLIC/column/DDL
  authority. Existing broad PUBLIC TEMP/function rights require reviewed revocation.
  Worker uses a dedicated RDS IAM-authenticated `cf_inference` connection with verified
  TLS and bounded connection/statement/lock timeouts. Operational DB connections are
  also bounded; migration statement limits remain explicitly overridden by migration.

## Verified offline results

- `services/aiops-service/.venv/bin/python scripts/test-secure-ai-offline.py`:
  **141 passed, 4 skipped in 1.35s**, all socket connections disabled.
- Includes real in-process ASGI/middleware tests for ownership-before-collection,
  role denial, replay/budget failure, forbidden actions, strict disclosure, stale/
  foreign evidence, credential co-location, persistence, semantic manifest enforcement,
  workload manifests/IAM shape and legacy snapshot preservation. Existing guardrails,
  read-only tools and human remediation/approval tests also pass.
- Previously stalled enrichment/knowledge API tests now pass with isolated mocked I/O,
  inline deterministic scheduling fixtures and three-second request bounds. Production
  scheduling is unchanged; these tests do not validate production threadpool behavior.
- Real PostgreSQL concurrent-replica, replay, rate/import gate and idempotent historical
  import tests exist in `test_postgres_inference.py`. **All four skipped** because no
  local PostgreSQL server is installed/configured. Client tools alone are insufficient.
  Offline fixture/SQL checks are not proof of actual PostgreSQL locking or ACL behavior.
- Three frontend test files passed: inference status/CSRF/action coverage, existing
  four-project workflow/proxy coverage, and service identity coverage. Frontend
  `tsc --noEmit` and focused ESLint checks passed. No browser or full-stack test ran.
- Focused changed-file whitespace validation passed. Existing unrelated Compose
  whitespace was not changed.

## Remaining blockers and production prerequisites

1. **Database verification and migration:** run the hosted ephemeral PostgreSQL integration gates, then validate actual function
   ACLs as `cf_inference` (including PUBLIC/default/column ACLs and RDS IAM membership).
   Apply existing migrations, the new ownership/ledger migration and inference grants
   using the separate migrator/DBA identity. Freeze all old workers, import **every**
   ledger, reconcile totals and finalize. Never finalize merely to bypass missing
   reservations. No existing reservations or production schemas were accessed here.
2. **Ownership inventory:** bind existing/new incidents from independently approved
   incident-to-project inventory. Unbound incidents deliberately remain unavailable.
   Keep normal project/user/membership management in the existing project service;
   do not create a parallel membership authority.
3. **Telemetry provenance:** provision reviewed project aggregate recording rules
   backed by authoritative resource-to-project inventory and approved SLO thresholds.
   The metric contract is documented in the runbook. The bounded trusted producer and rules are now implemented above; native
   validation, reviewed inputs and live provenance checks remain required. No
   inferred/global metric fallback is supplied.
4. **Workload release inputs:** approved image build/scan/digest, exact IAM/OIDC/RDS
   identifiers, Secrets Manager entries, public CAs, DNS-SAN worker TLS certificate,
   CSI driver/provider and coordinated key/certificate rotation. Validate the AIOps
   strategic patch against the actual deployment/container name before applying.
5. **Network enforcement:** provide a reviewed FQDN-capable CNI/egress-proxy overlay
   for exact Google/regional AWS/RDS destinations and allow AIOps→worker TLS. The base
   worker denies external egress. Standard NetworkPolicy cannot safely allowlist public
   DNS endpoints. Block direct provider access from AIOps; enforce admission/RBAC against
   label/CSI/role spoofing. Effective cloud/Kubernetes/network isolation was not tested.
6. **Provider approval:** verify account-specific Gemini 2.5 Flash availability,
   permitted data handling, free-only quotas and account-side paid-billing prevention,
   plus current pricing/currency headroom for the fixed reservation. Then explicitly
   enable disclosure/terms gates. There is no automatic paid inference mode or fallback.
   No live availability, AWS, RDS IAM, TLS or provider call was performed.

Detailed migration/configuration/security inputs:
[`deploy/kubernetes/inference/README.md`](../deploy/kubernetes/inference/README.md).
Provider terms/pricing reference: https://ai.google.dev/gemini-api/docs/pricing

## Next dependency

Use the approved hosted ephemeral PostgreSQL workflow to run ledger, review, ACL and
atomic-dispatch integration gates; no local database provisioning is required. After
that, the release owner must
supply verified incident ownership and trusted project aggregate recording rules.
Keep disclosure disabled and worker external egress denied until all release gates
above are verified. No further live action is authorized by this batch.
