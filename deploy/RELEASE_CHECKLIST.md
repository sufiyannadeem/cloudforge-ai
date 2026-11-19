# Release checklist

Local verification on 2026-11-19 passed the frontend production image build, TypeScript, targeted lint, 11 frontend test files, four Playwright tests, Go race/security suites, 232 Python tests, and isolated PostgreSQL tests. The optional FinOps audit fixture passed separately with its database configured. All 22 Go-service migrations applied in order and passed a second idempotence run, including browser administration migration 006. npm audit reported zero vulnerabilities.

The local frontend image ID is `sha256:405ca951da593e1f97263288954a92cb0d713e7452c2be0dbb6e2c89e6079911`. It contains Next.js 16.4.5 and Node 22.23.5 and runs as UID 1001. It has not been deployed. Production Compose syntax and dependency order were checked with explicit validation placeholders. Target secrets, IAM, published image digests and live acceptance remain release gates.

## Images and local verification

- [ ] Build immutable images for frontend, project, infrastructure, deployment, AIOps and FinOps from the reviewed checkout. Record image digests and retain the previous release.
- [ ] Verify frontend Next.js 16.4.5, a non-root standalone runtime, and Node 22. Node 20 is end-of-life according to the [Node.js release schedule](https://nodejs.org/en/about/previous-releases).
- [ ] Run frontend tests, TypeScript, lint, Playwright with disposable accounts, Go race/security tests, and the FinOps PostgreSQL runner. Record npm audit results and any unresolved applicable advisories.
- [ ] Validate the intended production Compose or Kubernetes configuration using private runtime secrets. Record target cluster, IAM, network and TLS acceptance separately from local image validation.

## Database order

- [ ] Back up PostgreSQL and verify restore in an isolated environment before rollout. Preserve existing migration receipts and all historical migration files.
- [ ] Start project-service first. Its migration runner applies project migrations 001–006 in lexical order, including account, ownership, email, FinOps audit, and browser administration tables. Require its healthy state before dependent APIs start.
- [ ] Start infrastructure-service (001–011) and deployment-service (001–005). Each runs its own migrations before serving HTTP. Require healthy state before FinOps and AIOps.
- [ ] Start AIOps, which initializes its PostgreSQL schema during application startup. Start FinOps after project and infrastructure schemas exist. Start the frontend after backend readiness.
- [ ] Confirm the shared schema_migrations table contains all 22 Go-service receipts, including 006_browser_admin_audit.sql, 011_terraform_drift.sql and 005_deployment_diagnostics.sql. Re-running all three runners must preserve those receipts.
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
