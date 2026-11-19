# Batch 29 — final local release gate

Baseline: `bc5e693`; reviewed against [Batch 28](BATCH28_CLOSURE.md) and the
[historical capability audit](PRODUCTION_READINESS_AUDIT.md).
**Local closure is not production sign-off. Production remains NO-GO.**

| Gate | Classification and evidence |
| --- | --- |
| Database identity, TLS and persistence | **LOCAL-PASS** for disposable PostgreSQL. `services/service-identity/database.go`, both Python `app/service_identity.py`, `deploy/postgres/{001_principals,002_runtime_grants}.sql`, and `scripts/test-database-boundaries.py`: 23 actual migrations, AIOps schema, seven scoped runtime roles, verified TLS, rejected hostname/unverified TLS, denied DDL/accounts/approval writes, non-owner HTTP startup and drift-history concurrency. Actual production ownership/credentials/CA cutover is **EXTERNAL-BLOCKED**. |
| Cross-service authorization | **LOCAL-PASS** for focused identity, project account/handler and deployment handler/worker race tests, Python readiness/project-cost/telemetry authorization, and frontend role/CSRF contracts. These do not prove a deployed multi-service topology or all browser workflows. |
| CI image identity and provenance | **PARTIAL**. `.github/workflows/release-images.yml` and `scripts/release-images.py` bind the scanned archives/config IDs/revision before publishing without rebuilding; offline tests reject tampering, incomplete manifests and tags. `provenance: false` remains explicit: SBOM/checksums are not signed provenance. Hosted seven-image builds/scans, independent protected-environment reviewers, real registry digests, signing/attestations and verification/admission are **EXTERNAL-BLOCKED**, not completed by this gate. |
| GitOps approvals | **PARTIAL**. `scripts/prepare-gitops.py` pins an exact commit/repo, verified operator groups, namespaced kind allowlist, no tenant Rollout/raw Secret/RBAC authority and no automatic prune. Migration hooks have separate credentials and ordering. Trusted repository/Argo administrators remain trust roots. Controller privileges/CRDs, SSO, ESO health, sync and rollback are **EXTERNAL-BLOCKED**. GitOps is not Terraform or remediation approval. |
| Drift scheduling/alerts | **LOCAL-PASS** for bounded batches, real PostgreSQL history/overlap/outage/stale fences, read-only IAM configuration and offline Prometheus fixtures. **PARTIAL** operationally: CronJob/IRSA/provider reads, exporter delivery and actual alert routing are **EXTERNAL-BLOCKED**. A successful batch is not full-fleet compliance; missing metrics are not evidence of health. |
| Audit integrity | **PARTIAL** source persistence/append boundaries and [central design](CENTRAL_AUDIT_DESIGN.md). FinOps rejects unauthorized capture access; isolated capture API persistence test is skipped without its dedicated DSN. No signed offsite checkpoints, central collector, independent immutable anchor or end-to-end tamper verification exists. Those implementation/acceptance gates are **EXTERNAL-BLOCKED for release**; local history is mutable source evidence, not cryptographic integrity. |

## Confirmed local P1 fix

The original bootstrap accepted an existing runtime role with `CREATE ON SCHEMA
public`; table ACL cleanup does not remove schema/database CREATE or ownership.
An actual PostgreSQL regression failed before the correction
(`/tmp/cloudforge-b29-ddl-before/evidence.json`, clean fixture teardown).
Bootstrap now rejects runtime database/schema CREATE and database/schema/routine
ownership, in addition to its prior table/role checks. It does not silently revoke
or reassign existing authority. The fixture exercises five explicit unsafe
handoffs and requires the specific rejection, not an arbitrary SQL failure.
No historical migration, existing database or application workflow changed.

## Focused checks

- 59 root release/GitOps/foundation/drift/CI tests passed; three unrelated
  Terraform/history wrappers deselected. 26 AIOps and 13 FinOps tests passed;
  one FinOps capture API PostgreSQL test skipped (dedicated DSN unavailable).
- Seven Go package race checks passed: service identity; infrastructure
  config/repository; project accounts/handler; deployment handler/worker.
  Separate real DB integration runs through the disposable driver.
- Final actual DB evidence: `/tmp/cloudforge-b29-ddl-final/evidence.json`, fixture
  `cf-drill-5319301e512c4dd1b13131d16af62fc5`: PASS, no cleanup failures.
- Two frontend role/CSRF test files passed with Node 22.23.2. No frontend code
  changed; no full build, browser E2E or broad suite was rerun.
- Trivy 0.76.2 cached configuration checks: zero HIGH/CRITICAL for the synthetic
  76-object Kubernetes render and drift IAM definition, with no ignore file.
  This is not a fresh all-image vulnerability scan; the local vulnerability DB
  is dated October 27 and cannot establish current image vulnerability status.
- Cached Prometheus 3.5.0 offline drift rule tests, staged Gitleaks and
  `git diff --check` passed. No new suppression is added.

## Minimal acceptance order — separately approved operations only

1. Approve account/region, budget/quota limits, cleanup owner and expiry. Complete
   hosted scanned/signed digest release and independent promotion protection.
2. Approve and verify backend bucket versioning/encryption/public blocking,
   native locking, isolated state keys, least-privilege workload/IRSA/secret trust
   and verified database CA/credential/ownership handoff. Test negative access.
3. Review controller digests/RBAC, network/DNS egress, RWX availability, backups
   and ordered migration/ESO readiness before an independently approved sync.
4. Start read-only/provider checks; then explicitly authorize one bounded EC2
   lifecycle: project request, saved plan, independent approval, apply, AWS ID/live
   verification, scoped telemetry/cost attribution and a fresh approved destroy.
   Verify actual termination and retained/billable orphans independently of state.
5. Accept S3/VPC/RDS/EKS separately; validate deployment promotion/abort/rollback,
   project-scoped diagnostics/logs, SLO coverage, drift alerts and audit transport.

Cost approval must include EKS control plane/nodes, NAT/data transfer, RDS/storage/
snapshots, EBS/PVCs, registry, Secrets Manager/KMS, monitoring retention, billing
queries and immutable audit retention. No fixed estimate is justified without
chosen sizes, duration and region-specific pricing; no AWS pricing lookup ran.

Rollback prerequisites: previous verified image/Git digests, migration
compatibility and approved DB restore point, tested backup/CA/secret recovery,
state versions/locking, maintenance drain and named recovery authority. Do not
undo additive schemas or overwrite failed Terraform state automatically. Image
rollback never authorizes cloud destroy or remediation; all such actions require
fresh approvals. Production RTO/RPO and offsite integrity remain unverified.
