# Release checklist

Historical pre-Batch-23 verification on 2026-11-19 passed the frontend production image build, TypeScript, targeted lint, 11 frontend test files, four Playwright tests, Go race/security suites, 232 Python tests, and isolated PostgreSQL tests. The optional FinOps audit fixture passed separately with its database configured. All 22 Go-service migrations applied in order and passed a second idempotence run, including browser administration migration 006. npm audit reported zero vulnerabilities.

Those results are historical, not a fresh build of the current checkout. Current recovery evidence covers 23 migrations; see [the Batch 27 audit](PRODUCTION_READINESS_AUDIT.md) before release.

The historical local frontend image ID is `sha256:405ca951da593e1f97263288954a92cb0d713e7452c2be0dbb6e2c89e6079911`. It contains Next.js 16.4.5 and Node 22.23.5 and runs as UID 1001. It has not been deployed. Production Compose syntax and dependency order were checked with explicit validation placeholders. Target secrets, IAM, published image digests and live acceptance remain release gates.

## Images and local verification

- [ ] Build immutable images for frontend, project, infrastructure, deployment, AIOps and FinOps from the reviewed checkout. Record image digests and retain the previous release.
- [ ] Verify frontend Next.js 16.4.5, a non-root standalone runtime, and Node 22. Node 20 is end-of-life according to the [Node.js release schedule](https://nodejs.org/en/about/previous-releases).
- [ ] Run frontend tests, TypeScript, lint, Playwright with disposable accounts, Go race/security tests, and the FinOps PostgreSQL runner. Record npm audit results and any unresolved applicable advisories.
- [ ] Validate the intended production Compose or Kubernetes configuration using private runtime secrets. Record target cluster, IAM, network and TLS acceptance separately from local image validation.

## Database order

- [ ] Back up PostgreSQL and verify restore in an isolated environment before rollout. Preserve existing migration receipts and all historical migration files.
- [ ] Start project-service first. Its migration runner applies project migrations 001–006 in lexical order, including account, ownership, email, FinOps audit, and browser administration tables. Require its healthy state before dependent APIs start.
- [ ] Start infrastructure-service (001–011) and deployment-service (001–006). Each runs its own migrations before serving HTTP. Require healthy state before FinOps and AIOps.
- [ ] Start AIOps, which initializes its PostgreSQL schema during application startup. Start FinOps after project and infrastructure schemas exist. Start the frontend after backend readiness.
- [ ] Confirm the shared schema_migrations table contains all 23 Go-service receipts, including 006_browser_admin_audit.sql, 011_terraform_drift.sql and 006_rollout_strategies.sql. Re-running all three runners must preserve those receipts.
- [ ] Grant FinOps attribution its separate read-only login for projects, memberships, infrastructure resources and EC2 attribution. Grant the audit login only schema usage and SELECT/INSERT on finops_anomaly_captures. Set both DSNs through private secret references.

## Secrets and IAM

- [ ] Configure distinct frontend-to-service signing keys, the AIOps deployment key, Alertmanager signing key, database credentials and session/CSRF secret. Verify secure cookies behind the intended HTTPS origin, session revocation, key rotation and Developer/SRE denial of administration.
- [ ] Confirm workload STS identity is account 933018172228 in eu-west-1. Review scoped provisioner permissions and the exact runtime role trust. Production must use workload credentials and secret-controller/Secrets Manager access scoped to approved secret ARNs.
- [ ] Verify the S3 backend account, region, encryption, versioning, public-access blocking and lockfile permissions. Verify actual lock acquisition only during an independently approved operation.
- [ ] Keep Terraform execution disabled until the approved backend and role chain exist. Follow the [bootstrap runbook](../infrastructure/terraform/bootstrap/README.md). IAM creation and bootstrap apply require explicit approval.

## Monitoring and rollback

- [ ] Check backend health, durable queue leases, PostgreSQL connectivity, Prometheus targets, bounded logs, unavailable-data states, project metric boundaries and alert delivery.
- [ ] Verify audit retention for account changes, approvals, deployments, diagnostics, cost captures and drift scans. Check signed actor identity and project/resource attribution.
- [ ] Rehearse reverting to the recorded compatible image digests. Retain additive schemas. Any database restore requires a separately reviewed restore plan and backup validation.
- [ ] Preserve failed/partial Terraform state and audit records. Reconcile through a fresh, independently approved saved plan. Application image rollback must never trigger automatic cloud remediation.

## Live acceptance after separate approval

- [ ] In an authorized sandbox project, complete EC2 request → refreshed plan → independent approval → explicit apply authorization → AWS ID/provider verification. Reject self-approval, expired/tampered/replayed plans and cross-project access.
- [ ] Run read-only drift scans; verify desired changes versus observed provider drift. Verify project costs only after resource attribution and billing samples exist. Check real incident resource identifiers against that evidence.
- [ ] Generate and independently approve a fresh destroy plan, obtain explicit teardown authorization, then verify termination and retained disks/snapshots. Record final costs and remaining billable resources.
- [ ] Validate VPC/S3/RDS/EKS inputs and dependencies before their separate approved lifecycle tests. Verify EKS namespace RBAC, real deployment health, bounded/redacted logs, rollback and Kubernetes diagnostics.
- [ ] Obtain deployment sign-off only after target-environment IAM, state locking, recovery, monitoring and live acceptance evidence are recorded. Keep local validation and target-environment acceptance evidence explicit.

## Batch 22 deployment foundation gates

- [ ] Review [all 16 dependency PR decisions](PR_REVIEW.md); resolve failed checks before any merge. Rebase onto the release baseline without overwriting rc1 security changes.
- [ ] Render using [the non-secret deployment inputs](kubernetes/deployment-inputs.example.json) and [runbook](kubernetes/README.md#render-the-deployment-foundation-batch-22). Record all six published image digests and provenance. The renderer is offline and does not establish registry or AWS existence.
- [ ] Approve exact application bucket names and secret/KMS ARN allowlists in bootstrap; verify the distinct secret-sync OIDC subject and FinOps read-only role. No wildcard bucket lifecycle namespace is granted by default.
- [ ] Install/review namespace-scoped External Secrets Operator access and v1 CRDs, synchronize exact properties, require Ready status and validate payloads privately. Verify rotation/restart, encryption at rest and database TLS/CA. Never apply the example placeholder Secrets.
- [ ] Supply and validate an encrypted/backed-up RWX storage class/CSI implementation. Exercise two-replica workspace access, ownership, restart and saved-plan persistence; no storage class or AWS filesystem is created by the renderer.
- [ ] Validate CNI enforcement, selected TLS ingress, cluster DNS, database/API/provider endpoint CIDRs and monitoring selectors. Deny unrelated namespace access. Default-deny policies require actual endpoint/network acceptance; they do not configure ingress certificates or database TLS.
- [ ] Review Services and startup/readiness/liveness probes against published images. Start a single project-service migrator first; check all migration receipts before scaling and starting dependent APIs in the documented order.
- [ ] Keep Terraform read-only until separate bootstrap/locking approval. Perform live IAM, EKS RBAC, monitoring, cost-attribution, recovery and rollback acceptance only under separately approved operations.

## Batch 23 strategy acceptance gates

- [ ] Apply deployment `006_rollout_strategies.sql` before the new image (23 Go migration receipts total); verify strategy defaults and promotion audit retention without rewriting old receipts.
- [ ] Keep rolling as default and Argo opt-in disabled until [strategy prerequisites](kubernetes/ROLLOUT_STRATEGIES.md) pass. Validate additional readiness-condition controllers and rollback using a prior immutable image.
- [ ] Independently review the first native-to-Argo baseline handoff, absence of overlapping controllers, server-side field ownership, stable ReplicaSet identity and active/shared Service selectors. Initial unapproved Argo activation is intentionally blocked.
- [ ] Review pinned controller/CRDs, project-only rollout RBAC, namespace admission and controller networking. Verify actual revision-scoped workload metrics before approving the example AnalysisTemplate; never substitute platform metrics or healthy defaults.
- [ ] Rehearse independent body-bound promotion, self-approval/replay denial, failed analysis/abort and real stable traffic restoration. Canary is replica-based; no weighted router is configured.
- [ ] Test worker restart/lease recovery, timeout/manual reconciliation and rollback under the real controller. Local fixtures, schema validation and Prometheus tests do not establish live Kubernetes readiness.

## Batch 24 reliability gates

- [ ] Review [reliability prerequisites and offline commands](kubernetes/RELIABILITY.md). Verify Kubernetes 1.30+, two hosts/zones, metrics-server, HA database capacity and cross-zone RWX before enabling traffic.
- [ ] Verify all six HPA minimums, PDBs, topology, probes, bounded shutdown and migration serialization in the target environment. Do not reset HPA-owned replicas on release.
- [ ] Verify private kube-state-metrics scraping and fresh operator dashboard evidence; missing metrics must remain N/A.
- [ ] Preserve infrastructure execution drain/reconciliation during maintenance; its automatic scale-down/eviction is blocked, but direct deletion and failures remain possible.
- [ ] Review pinned Cluster Autoscaler chart/image, dedicated IRSA, exact tagged ASGs and upstream RBAC. Resolve Terraform desired-size ownership before activation. Record cost/quota limits and live scaling/drain evidence separately.

## Batches 25–26 recovery and chaos gates

- [ ] Review [disaster recovery](DISASTER_RECOVERY.md) and [bounded chaos drills](CHAOS_ENGINEERING.md). Record independently approved RTO/RPO objectives and recovery authorization; no existing-target restore is automated.
- [ ] Retain real isolated logical/WAL restore and fault evidence, checksums, integrity comparisons and cleanup results. AIOps startup schema and incident histories are covered locally; verify production role/grant recovery, encrypted/offsite retention and production-sized recovery separately.
- [ ] Revoke restored sessions/keys as needed and invalidate restored execution approval before reopening mutations. Reconcile uncertain execution and obtain fresh bound plans.
- [ ] Obtain separate acceptance for Kubernetes/GitOps/PVC reconstruction, state/secrets recovery, live Prometheus/SLO response and node faults; retain the bounded local kernel-OOM and alert-transport evidence separately. Local Docker timings are not production RTO/RPO claims.

- [ ] Use the [reviewed PostgreSQL 16.16 recovery image](RECOVERY_IMAGE_SECURITY.md), verify its actual digest and scan results. Local config digest pinning is not a published registry image; publish/provenance and production Compose/cluster image selection require separate release approval. Do not replace existing databases during a drill.

## Batch 27 production sign-off

- [ ] Resolve the P0 shared database principal/TLS/image gaps in the [production audit](PRODUCTION_READINESS_AUDIT.md). Per-service IAM and signed HTTP identities do not replace per-service database grants.
- [ ] Run the repaired hosted image-security workflow: shared identity build contexts, pinned scanner, exact RBAC exceptions and unfixed vulnerability enforcement. Local structure tests are not a successful GitHub image build/scan.
- [ ] Complete the prioritized acceptance sequence in the audit. No deployment approval is implied by local verification; GitOps reconciliation and centralized audit/search remain missing capabilities.
