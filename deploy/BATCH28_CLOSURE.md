# Batch 28 — local security and integration closure

**Production remains NO-GO.** This supersedes the local-code gaps in the Batch 27
baseline; it does not assert a live database cutover, publication or cluster sync.
All application data/services outside uniquely labelled fixtures were untouched.

| Priority | Status | Implemented / remaining evidence |
| --- | --- | --- |
| Database principals and TLS | VERIFIED locally; production cutover BLOCKED | Seven scoped runtime principals plus separate migration owner, verified TLS/hostname checks in Go/Python startup, no production startup DDL, distinct runtime/migration Secrets and CA mounts. Actual PostgreSQL tests cover all 23 one-shot migrations, AIOps schema, denied DDL/hash/session/account/approval writes and a real non-owner HTTP server. Existing DB ownership/grants, random credentials, real CA/rotation and retiring shared users require approved handoff. |
| Build/scan/publish handoff | PARTIAL; hosted execution BLOCKED | Manual seven-image workflow, strict scans including unfixed findings, exact scanned tar/config/revision bindings, protected-main publish job without rebuilding and actual registry digest output. Offline selection rejects tag/local-ID/incomplete manifests. No image was published. Required environment reviewers, registry permissions, all-image hosted scans, signing/provenance and admission remain unverified. |
| GitOps reconciliation | PARTIAL; cluster acceptance BLOCKED | Standard Argo CD AppProject/Application preparation, exact Git revision/repo, one destination namespace, no raw Secrets/cluster RBAC/tenant Rollout authority, no automatic prune, HPA replica respect and ordered isolated migration/grant hooks. Argo/ESO installation, trusted SSO/repo credentials, CRDs, controller privilege review and actual sync are not performed. |
| Scheduled drift and alerts | VERIFIED local DB/format/alert logic; AWS execution BLOCKED | Standard opt-in CronJob, read-only AWS identity definition, separate cf_drift DB principal, bounded five-resource batches and cross-instance advisory lock; existing observer/history/revision fences reused. Actual scoped PostgreSQL tests cover findings, overlap, unavailable provider evidence and stale-resource rejection. Offline Prometheus tests cover never-successful and recovered scheduling. No AWS observation or CronJob execution occurred. RDS secret read permissions and full provider read coverage require separate target verification. |
| Central tamper-evident audit | PARTIAL (design); collector/anchoring BLOCKED | [Design](CENTRAL_AUDIT_DESIGN.md) maps existing sources, sanitized envelopes, resumable sequence/watermarks, independently signed chained checkpoints and immutable/offsite anchors. No collector, asymmetric signer, WORM store or complete source coverage is claimed. Current DB audit tables remain mutable source evidence. |

## Evidence from this run

- Final disposable fixture: `cf-drill-86898651594c4f4c83f3ecb6316d9d83`.
  `/tmp/cloudforge-b28-security-final/evidence.json` records PASS and no cleanup
  failures. Real production-mode TLS, seven runtime principals, explicit migration
  binaries and scheduler repository tests executed; the driver checks the test's
  PASS marker, not just its exit code. Observer output is an explicit test fixture,
  not actual AWS drift. Stale column grants were deliberately seeded in the fixture and removed before
  the negative checks. No SQL grant/principal changes targeted existing data.
- 59 focused release/GitOps/foundation/drift/CI/RBAC Python tests passed (three
  unrelated Terraform/history wrappers deselected). 26 AIOps and 12 FinOps
  database/readiness/authorization/project-cost tests passed: **97 total**.
- Identity, project account/handler, infrastructure handler/service/runner and
  deployment config/handler/executor/worker Go race checks passed; valid Go cache
  results were reused. Server/migration binaries compile and run in the DB drill.
- 59 built-in rendered Kubernetes objects validated against cached official 1.35
  OpenAPI. Synthetic production Compose configuration also passed quiet validation
  without reading .env or contacting services. Argo/ESO custom resources received structural tests, not validation
  against an installed target controller. New Jobs/CronJob obey scoped networking,
  read-only roots, no API token, bounded resources and deadlines.
- Trivy 0.76.2 found zero HIGH/CRITICAL configuration findings in the rendered
  fixture and new drift IAM definition, without new suppressions. Terraform fmt
  and offline bootstrap validate passed using the cached provider. No plan/apply
  ran. Offline cached promtool drift-alert tests passed; exporter/live transport
  acceptance remains separate.
- The scheduler integration uncovered nullable legacy resource descriptions/types
  failing string scans. Read queries now normalize those optional fields without
  rewriting data; the NULL fixture is retained as regression coverage.

## Operational boundaries

[Database handoff](postgres/README.md), [image release](IMAGE_RELEASE.md),
[GitOps preparation](gitops/README.md), [scheduler](kubernetes/SCHEDULED_DRIFT.md)
and [central audit design](CENTRAL_AUDIT_DESIGN.md) contain exact prerequisites.

Runtime cf_drift can append scan history, not approve plans or change accounts,
resource status or existing audit rows. A fixed-purpose migration-owned definer function preserves the existing
active/revision row lock and fixed service actor without granting resource UPDATE,
including timestamps, or direct history INSERT/UPDATE/DELETE. Function payloads
are bounded and field-allowlisted, objects qualified and search_path fixed;
no dynamic SQL is used by the definer function. The worker cannot change approval
revisions. AWS permissions remain read-only; job credentials
contain no frontend signing key or provisioner assume-role ARN.

The older recovery drill uses development-only non-TLS fixtures explicitly; this
new DB drill supplies production TLS evidence. No full seven-image build, browser
E2E, existing-data migration, hosted workflow, Argo sync, AWS/EKS call, live drift,
registry push, PR mutation or deployment was performed. Actual CloudForge/AWS
execution still requires independently approved fresh saved plans. Restore and
ownership handoff require explicit human approval; no automatic repair is added.
