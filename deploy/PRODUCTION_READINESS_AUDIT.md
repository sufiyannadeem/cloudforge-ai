# Batch 27 production readiness audit

**Batch 28 update:** the assessment below is the historical baseline.
[Current local closure and remaining gates](BATCH28_CLOSURE.md) supersede its
shared-principal, GitOps and scheduler code-status findings. Production remains
NO-GO pending approved cutover and hosted/cluster/AWS acceptance.

**Verdict: NO-GO for production.** Baseline `1eda657` on
`feat/aws-terraform-foundation`, plus the narrow CI fixes recorded below.
This is a code/configuration audit, not a live AWS, cluster or penetration test.
No AWS/EKS API, Terraform operation, deployment, remote Git mutation or existing
application data modification was performed.

VERIFIED means the stated **local scope** has test/evidence support, not that its
AWS implementation has passed acceptance. PARTIAL means code exists with stated
integration/coverage limits. BLOCKED means a required external configuration or
acceptance gate is unresolved. MISSING means no implementation was found in the
reviewed architecture. Prior tests are distinguished from fresh checks below.

## Capability evidence

| Capability | Classification | Exact evidence and gap |
| --- | --- | --- |
| Individual accounts, session expiry/revocation, canonical roles | VERIFIED locally | `services/project-service/internal/accounts/admin.go` (`update` increments session_version), `accounts_integration_test.go`; `frontend/src/lib/auth.ts`. Fresh account/handler race and browser auth contract tests pass; real identity-provider/MFA integration is not implemented by this account store. |
| Signed backend identity and RBAC | VERIFIED locally | `services/service-identity/identity.go:Verify/Human` checks caller key, audience, exact method/URI and <=30s lifetime; Python `app/service_identity.py` equivalents. Fresh identity and infrastructure handler tests pass. Frontend is a trusted identity issuer; compromise of its keys remains a trust-root compromise. |
| Project/resource isolation | VERIFIED at local authorization boundary | `services/service-identity/projects.go:Level/Resource`, infrastructure `internal/handler/router.go`, FinOps `app/project_costs.py:project_resources`, frontend `src/proxy.ts`. Null legacy ownership fails closed; backend membership checks accompany UI guards. Database grant isolation is separately BLOCKED below. |
| Developer no-code EC2/VPC/S3/RDS/EKS workflow | PARTIAL | `frontend/src/app/infrastructure/page.tsx`, `frontend/tests/infrastructure-form.test.mjs`, infrastructure `internal/terraform/generator.go` has all five real AWS resource templates. Fresh form/role tests pass; no actual AWS creation, dependency or cleanup acceptance is established. Browser E2E source is `frontend/e2e/roles.spec.ts`; it was not rerun in this audit. |
| Saved Terraform plans, independent approvals and failure recovery | PARTIAL end to end | `internal/handler/router.go` body/nonce checks; `internal/repository/approval_assertion.go`; `internal/service/provisioning_service.go:Apply/ApplyDestroy`; `internal/terraform/runner.go:apply`. Hash/backend binding, expiration, single-use claim, destroy_failed and provider-refresh failure paths have fresh Go tests. AWS and interrupted-operation acceptance remain blocked. |
| AWS resource IDs and actual status | PARTIAL | `internal/terraform/runner.go:ApplyWithState/verifyProviderRefresh` separates a state ID from refresh verification; `internal/terraform/ec2_attribution.go` maps approved workspace evidence. Successful database writes alone are not AWS acceptance. No live provider observation was obtained during this audit. `ApplyDestroy` checks empty managed Terraform state, not an independent AWS orphan/billing sweep; continuous provider-status reconciliation is not established. |
| Deployment concurrency, durable ownership and audit | PARTIAL | `services/deployment-service/internal/repository/deployment_execution.go:ClaimExecution/RenewExecution/FinishExecution` fences DB completion with tokens/expiry; attempts and rollout promotions persist separately. SQL/integration tests exist; queue/lease integration was not rerun here. DB fencing does not guarantee exactly-once external Kubernetes side effects. |
| Rolling / blue-green / canary | PARTIAL | Deployment executor `kubernetes_executor.go`, `argo.go`, handler `rollout_handler.go`, and `deploy/kubernetes/ROLLOUT_STRATEGIES.md`. Rolling uses native Deployment; Argo owns progressive releases and gated promotion. Canary is replica-based without a traffic router. Real CRDs/controller, traffic handoff, analysis abort and rollback remain unverified. |
| SRE scaling / HA | PARTIAL | `scripts/render-kubernetes.py` emits six HPA/PDB sets, probes, topology and termination budgets; `scripts/prepare-node-autoscaler.py` prepares standard Cluster Autoscaler artifacts. Infra automatic downscaling/eviction is blocked for synchronous Terraform. Two-zone placement, metrics-server, exporter, HA PostgreSQL, RWX storage and node desired-size ownership are external gates. |
| Monitoring, SLO/error budgets and anomalies | PARTIAL | AIOps `app/slo_service.py`, `test_telemetry_api.py`, `test_anomaly_service.py`; `monitoring/prometheus/rules/`. Coverage/freshness and five-sample minimum guards have local tests. Target health is not seven-day coverage. Intended-cluster scrape labels, exporter delivery, burn alerts and full fault-to-SLO response remain unverified. |
| AI Kubernetes Agent | PARTIAL | Deployment `internal/executor/project_diagnosis.go:DiagnoseProject/samplePod` bounds diagnosis to one owned pod, events/logs/restarts/usage; `project_telemetry.go` validates pod identity and redacts bounded logs. Diagnosis is rule-based, not a live verified generative/autonomous agent. Multi-pod/temporal diagnosis and real EKS evidence are not established. |
| AIOps recommendations and human remediation | PARTIAL | `services/aiops-service/app/ai_provider.py` explicitly supports disabled/mock/live providers; `app/remediation_access.py` and deployment `internal/repository/deployment_remediation.go:ClaimRemediation` verify persisted approval binding/expiry/policy and consume dispatch. Local Compose selects mock enrichment and simulated deployments explicitly. No live model or approved Kubernetes remediation ran. |
| Cloud Cost Detective / project billing | PARTIAL | FinOps `app/project_costs.py` uses DB mappings plus AWS instance/tag/account checks and resource-scoped cost filters; no global billing fallback for developers. Attribution currently covers EC2 compute, not VPC/S3/RDS/EKS/shared costs. Cost Explorer enablement, real billing samples and attribution remain AWS acceptance gates. Supplied inventory is analytical input, not independently verified AWS evidence. |
| AIOps–FinOps integration | PARTIAL | `frontend/src/app/api/incidents/[id]/cost-evidence/route.ts` joins authenticated incident IDs to backend-scoped verified resource costs; absent identifiers return unavailable. This is evidence display, not proof of incident causation or automatic AI cost correlation. |
| Terraform Drift Detection | PARTIAL | Infrastructure `internal/terraform/drift.go:ScanDrift/classifyDrift` uses a refreshed, non-applied observation plan, separates provider_drift from desired_change, and emits sanitized risks. `internal/handler/drift.go` and repository `drift.go` persist project-scoped history. Fresh parser/runner tests pass; scheduled scans and drift-specific alert delivery are MISSING; live AWS drift acceptance is BLOCKED. Remediation requires a fresh approved plan. |
| PostgreSQL restore / local chaos | VERIFIED for disposable fixtures | [Recovery evidence](RECOVERY_EVIDENCE.md): PostgreSQL 16.16, 23 migrations, 22-table logical/PITR fingerprints including AIOps, real kernel OOM and authenticated Alertmanager delivery; measured restore 3.680s/PITR 2.576s. Evidence is inherited unchanged from `1eda657`, not rerun. Production RTO/RPO, offsite encryption, role/grant restore, scale and cutover are not established. |
| CI security / supply chain | PARTIAL; local blockers repaired | `.github/workflows/ci.yml`, `security.yml`, `tests/test_ci_pipeline_hardening.py`: pinned actions, SBOM and failure gates exist. Go image contexts, feat pushes, Trivy parity, unfixed vulnerability handling and Node 22 are corrected below. Hosted scans/builds, signed registry images/provenance and release promotion remain unverified; builds currently use push:false/provenance:false. |
| IAM, secrets and state backend | BLOCKED for production | `infrastructure/terraform/bootstrap/{iam,provisioner,secret_sync,s3}.tf` defines service-account trust, approved/tagged resource policies, scoped secret/KMS reads and versioned/encrypted private S3. Generator `backendFile` enables native lockfiles. Actual principals, trust, IAM conditions/quotas, KMS, state locking and rotation were not contacted. Read-only inventory wildcard permissions require target-policy review. |
| GitOps reconciliation | MISSING | Existing workflows build/test/scan; `deploy/kubernetes` contains rendered workload/controller prerequisites, not an Argo CD Application/Flux reconciliation implementation. Argo Rollouts is not GitOps CD. No drift reconciliation or automatically verified release rollback pipeline is established. |
| Central security/audit operations | PARTIAL | Account admin, infrastructure reviews, deployment attempts/promotions, AIOps events, drift and FinOps captures persist in separate tables. No consolidated tamper-resistant/offsite audit stream/search/retention enforcement was found. Existing per-capability history must not be presented as centralized audit coverage. |

## Critical and high-priority production blockers

1. **P0 — Shared database authority.** The four references at
   `deploy/kubernetes/cloudforge-secrets-example.yml` (project, infrastructure,
   deployment, AIOps) use `cloudforge-postgres-credentials/DATABASE_URL`; the
   renderer carries that common mapping forward. `docker-compose.prod.yml`
   uses the same `cloudforge` principal and its PostgreSQL initializer user.
   A service possessing account-table write privileges is not confined by signed
   HTTP RBAC. Require independent runtime principals, explicit cross-table read
   grants, separate migration ownership and negative grant tests. This is not
   fixed by changing a secret name alone. Live grants/credentials were not changed.
2. **P0 — Production transport and immutable image selection.** Production
   Compose uses mutable `:prod`/`postgres:16-alpine` tags, Go DSNs with
   `sslmode=disable`, and directly published service ports. The digest-only
   Kubernetes renderer is the prepared path, not proof of TLS/ingress/CNI/DB-CA
   enforcement. Publish verified images, private secrets and certificate-verified
   DSNs; reject legacy Compose as production sign-off evidence. The patched
   recovery PostgreSQL image has a local config digest, not a published registry
   artifact. Existing running images/data were deliberately left untouched.
3. **P0 — Real cloud/cluster acceptance absent.** Example deployment inputs have
   null images/roles/bucket/storage and empty endpoint CIDRs. Do not invent these
   values or enable Terraform writes. Bootstrap, IAM role boundaries, state
   isolation/locking, Secrets Manager/IRSA and real EC2 lifecycle must pass first. Post-destroy acceptance must independently
   check AWS IDs, retained snapshots/disks and billable orphans; an empty state
   file alone does not establish complete cleanup.
4. **P1 — Operational interruption and HA acceptance.** Infrastructure requests
   execute Terraform synchronously; PDBs cannot prevent direct termination or
   deployment updates. Drain/reconcile before maintenance. Database connection
   budget, cross-zone RWX, node scaling ownership, Argo RBAC/CRDs and monitoring
   transport remain unverified in a cluster. Local RTOs do not cover these failures.
5. **P1 — Hosted CI and release provenance.** Source checks now cover the repaired
   paths; the hosted six-image build/scan was not run. Unfixed HIGH/CRITICAL findings
   now fail rather than disappear. Rescan all release images: a zero-finding
   PostgreSQL recovery image does not prove other mutable base images are secure.

## Confirmed local fixes and focused evidence

- Security image builds lacked the `service_identity` named context required by
  all three Go Dockerfiles. Matrix inputs now supply the local source, rather than
  letting Docker resolve an unrelated external image.
- Security push filters now cover `feat/**`, matching the main CI workflow.
- Every security Trivy invocation now uses the existing reviewed v0.76.2 binary;
  repository scans reuse only the existing exact-path KSV-0048/KSV-0056 deployment
  Role exceptions. No global suppression was added.
- Both workflows now include unfixed HIGH/CRITICAL findings. Frontend CI uses
  Node 22, matching the runtime/release policy. No app authorization was changed.
- Release migration order/count is corrected to deployment 001–006 / 23 receipts;
  historical build/test results are explicitly marked as historical.

Checks invoked for this audit (Go cache reused where valid): **22 CI/gate/RBAC tests**, six frontend auth/role/form/strategy test
files, identity Go race suite, project account/handler race tests, infrastructure
handler/service/Terraform race tests, and redacted Gitleaks HEAD-history scan
(zero findings) passed. External Terraform init/validate and the history-scanning
pytest wrapper were not run by the focused pytest command (three deselected);
Gitleaks was run directly with redaction. Terraform runner tests use command fixtures, not real provider execution.
No full build, browser E2E, PostgreSQL
drill, hosted workflow or cloud/cluster acceptance was rerun for CI-only changes.

## Prioritized AWS readiness sequence

1. **Before cloud mutations:** separate and test database grants; resolve TLS and
   private network/ingress design; publish signed/digest-pinned images and SBOMs;
   run hosted security gates and review any unfixed findings. Choose GitOps versus
   an explicitly approved manual release process; do not claim GitOps exists.
2. **Approved foundation:** verify exact account/region, scoped AMI/bucket/role
   allowlists, IAM trust/PassRole limits, backend isolation/versioning/encryption,
   lock acquisition/recovery, secret-sync property/KMS grants and workload identity.
   Keep Terraform read-only until the distinct approval boundary is satisfied.
3. **Platform before traffic:** restore/verify HA PostgreSQL and grants; run project
   migrations first, then infrastructure/deployment, then AIOps/FinOps/frontend.
   Verify private endpoints, TLS/CSRF, default-deny enforcement, namespace isolation,
   RWX persistence, probes, resource budgets, HPA/PDB and node scaling limits.
4. **EC2-first sandbox acceptance:** authorized developer request → plan → different
   Platform Engineer approval → explicit apply authorization → provider refresh,
   AWS ID and audit verification. Exercise stale/replayed/self approvals and
   cross-project denial. Establish cost limits, expiry and cleanup ownership.
5. **Remaining lifecycles:** separately approve VPC/S3/RDS/EKS dependencies and
   teardown; validate partial failures, state/lock recovery, retained disks and
   snapshots. Then test EKS rolling/Argo promotion/abort/rollback and scoped logs/
   diagnostics, never claiming weighted traffic without a router.
6. **SRE/FinOps acceptance:** real target/label/sample coverage and fault-to-alert/
   SLO recovery; AWS billing/EC2 attribution and unavailable-data states; real drift
   observation with no automatic apply. Validate offsite restore, revocation,
   audit retention and operational RTO/RPO before production sign-off.

Every AWS write, Terraform apply/destroy, destructive recovery and remediation
requires its own existing human authorization/approval flow. This audit and its
local commit authorize none of those actions.
