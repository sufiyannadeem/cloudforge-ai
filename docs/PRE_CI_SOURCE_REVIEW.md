# Final pre-CI source review — 2026-11-25

Verdict: **source checks pass within the bounded local scope; hosted CI execution and
production release remain pending**. This is a risk-focused source review, not proof
of runtime behavior or an exhaustive independent audit. No commit, staging, push,
workflow dispatch, AWS provisioning/call, database startup, model/dependency download
or image build was performed during this review.

## Acquisition integrity

Recomputed SHA256 of `ci/integration-acquisition.json`:

```text
229740c6df87058f6c06162b908b8f48a9b408a5979ab6b5079492e0669e2d45
```

It matches the operator guide. Bootstrap lock hash, synthetic corpus source-manifest
hash and every corpus document hash also match their bindings. The acquisition lock
retains pending human approval and `reviewed_by: null`. Existing publisher metadata
claims in acquisition-evidence.json were inspected, not re-fetched or independently
re-established during this offline review. Full artifact-body verification remains CI work.

## Review and local verification

- Gitleaks scanned all 771 tracked/unignored source files at the initial snapshot,
  including untracked additions: no leaks found. Ignored local environments, backups,
  state, credentials, caches and generated reports were excluded; no secret values
  were printed. This scan does not attest to ignored local files or repository history.
- Pending inventory contains source, tests, synthetic fixtures, CI locks/workflows,
  deployment examples, migrations and documentation. No new model weights, wheelhouse,
  archives, binaries, state or credential files found. The existing tracked 15MB
  `services/infrastructure-service/server` binary is unchanged and outside this commit.
- Offline AI security suite: **228 passed, 6 skipped**. Skipped cases are not integration
  success; PostgreSQL/model/native gates still require real evidence.
- Frontend Node tests: **20 passed**; cached TypeScript `tsc --noEmit`: **PASS**.
- CI mechanics/hardening selection: **30 passed, 3 deselected** with cached system
  Python. Terraform and the redundant in-test Gitleaks invocation were excluded.
  An initial service-venv run had 29 passes and one missing-jsonschema failure;
  system Python supplied that already installed dependency without installation.
- All pending Python (65), JSON (9) and YAML (11, including multi-document manifests)
  parse; changed Go files pass gofmt. Diff whitespace check passes after removing
  one trailing-whitespace line in docker-compose.yml.
- Reviewed workflow triggers, permissions, environment boundaries, fail-closed aggregate
  gates, source/run/attempt binding, approved candidate hash selection and acquisition
  guards. Both new workflows are manual-only. Actions use commit pins; no OIDC or
  publication permission is added. Hosted data is synthetic. Dedicated runners retain
  separate private-input prerequisites and are outside the self-review exception.
- Application review focused on production CSRF/cookie restrictions, trusted telemetry,
  project boundaries and fresh independent platform-engineer remediation approval.
  The CI exception does not alter these application authorization checks.

## Approval exception

The [operator guide](GITHUB_HOSTED_VERIFICATION.md#solo-developer-self-approval-exception--synthetic-ci-only)
now documents explicit solo-developer self-review only for hosted synthetic runs in
release-verification, semantic-preparation and semantic-verification. Human audit
identity/date, source/lock hashes, run IDs/attempts and a separate candidate hash review
remain required. This document grants no actual approval. Independent production
release/deployment review, prevention of production self-review and fresh independent
PE approval remain mandatory; absence of a production approver blocks release.

## Readiness dependencies and blockers

1. User approval is required before committing or pushing this reviewed source.
2. Protected environment/ruleset capabilities, required reviewers, allowed refs,
   disabled bypass, explicit lock approval, same-SHA required checks, quotas and
   artifact headroom have not been verified against GitHub settings. Follow the guide.
3. Cached actionlint was unavailable on PATH and in inspected cache/tmp locations;
   it was not downloaded. Earlier actionlint results in acquisition-evidence.json are
   historical evidence, not a fresh run. Hosted CI must rerun the pinned validator.
4. Local default Go is 1.22.2; deployment-service requires 1.26.11. Go tests were not
   attempted with automatic toolchain/module downloads. Run them in approved CI.
5. Real PostgreSQL ACL/locking/atomic dispatch, native Prometheus/schema/Terraform/TLS
   gates, semantic preparation, candidate review and measured quality/RSS/p95 remain
   unexecuted in this review. The synthetic source checks cannot replace them.
6. Production retains the existing independent release, image/security, live IAM/TLS,
   workload isolation, authoritative ownership/inventory and budget/provider gates.

## Intended commit contents

Proposed scope: isolated inference/semantic RAG and budget ledger; trusted project
telemetry and insights; versioned remediation reviews and dispatch integrity;
project workspaces/UI and local-dev CSRF hardening; matching SQL/IAM/Kubernetes/
Prometheus assets; manual hosted verification with hash-bound acquisition and synthetic
corpus; regression tests and operational/review documentation. This review adds only
the approval documentation, this inventory and the whitespace correction.

Exact pending paths below form the intended allowlist (no files staged). Generated
TypeScript output is ignored. Recheck this inventory and lock hash before committing
if the working tree changes; candidate evidence must use the final committed SHA.

- `.github/actionlint.yaml`
- `.github/workflows/consolidated-release-verification.yml`
- `.github/workflows/semantic-release-verification.yml`
- `ci/acquisition-evidence.json`
- `ci/integration-acquisition.json`
- `ci/integration-acquisition.template.json`
- `ci/semantic-corpus/runbooks/deployment-failure.md`
- `ci/semantic-corpus/runbooks/high-error-rate.md`
- `ci/semantic-corpus/runbooks/high-latency.md`
- `ci/semantic-corpus/runbooks/service-down.md`
- `ci/semantic-corpus/slo/cloudforge-slos.md`
- `ci/semantic-corpus/source-manifest.json`
- `ci/semantic-preparation.lock`
- `deploy/kubernetes/inference/README.md`
- `deploy/kubernetes/inference/aiops-patch.yaml`
- `deploy/kubernetes/inference/secret-providers.yaml`
- `deploy/kubernetes/inference/workload.yaml`
- `deploy/postgres/003_inference_grants.sql`
- `deploy/postgres/004_remediation_review_grants.sql`
- `deploy/postgres/005_advisory_feedback_grants.sql`
- `deploy/release/rag/README.md`
- `deploy/security/inference/iam-policy.json`
- `deploy/security/inference/iam-trust.json`
- `docker-compose.yml`
- `docs/CONSOLIDATED_RELEASE_VERIFICATION.md`
- `docs/GITHUB_HOSTED_VERIFICATION.md`
- `docs/PRE_CI_SOURCE_REVIEW.md`
- `docs/PRODUCTION_SEMANTIC_RAG.md`
- `docs/PROJECT_STATUS.md`
- `frontend/src/app/agent/page.tsx`
- `frontend/src/app/api/proxy/[service]/[...path]/route.ts`
- `frontend/src/app/deployments/page.tsx`
- `frontend/src/app/drift/page.tsx`
- `frontend/src/app/incidents/[id]/page.tsx`
- `frontend/src/app/infrastructure/page.tsx`
- `frontend/src/app/project-costs/page.tsx`
- `frontend/src/components/finops/ProjectInsights.tsx`
- `frontend/src/components/incidents/InferenceStatus.tsx`
- `frontend/src/components/incidents/KnowledgeReferences.tsx`
- `frontend/src/components/incidents/RemediationPanel.tsx`
- `frontend/src/components/incidents/TrustedEvidencePanel.tsx`
- `frontend/src/components/infrastructure/DriftHistory.tsx`
- `frontend/src/components/workspaces/ProjectWorkspace.tsx`
- `frontend/src/components/workspaces/WorkspaceEvidence.tsx`
- `frontend/src/lib/csrf.ts`
- `frontend/src/lib/incidents-api.ts`
- `frontend/src/lib/remediation-review.ts`
- `frontend/src/lib/role-access.ts`
- `frontend/src/types/incidents.ts`
- `frontend/src/types/infrastructure.ts`
- `frontend/tests/auth-csrf.test.mjs`
- `frontend/tests/four-project-api.test.mjs`
- `frontend/tests/inference-status.test.mjs`
- `frontend/tests/project-insights.test.mjs`
- `frontend/tests/remediation-review.test.mjs`
- `frontend/tests/trusted-evidence.test.mjs`
- `infrastructure/terraform/bootstrap/STATE_RECOVERY_SEQUENCE.md`
- `monitoring/prometheus/project-evidence-discovery-rbac.example.yml`
- `monitoring/prometheus/project-evidence-scrapes.example.yml`
- `monitoring/prometheus/project-evidence.test.yml`
- `monitoring/prometheus/rules/cloudforge-project-evidence.yml`
- `scripts/ci/acquire-integration-inputs.py`
- `scripts/ci/bootstrap-integration-postgres.py`
- `scripts/ci/guard-verification-environment.py`
- `scripts/ci/prepare-semantic-artifacts.py`
- `scripts/ci/require-same-sha.py`
- `scripts/ci/run-hosted-native-tests.py`
- `scripts/ci/select-semantic-candidate.py`
- `scripts/import-ai-budget.py`
- `scripts/prepare-embedding-artifact.py`
- `scripts/prepare-knowledge-embeddings.py`
- `scripts/test-database-boundaries.py`
- `scripts/test-secure-ai-offline.py`
- `scripts/verify-consolidated-release.py`
- `scripts/verify-rag-release.py`
- `services/aiops-service/Dockerfile.inference`
- `services/aiops-service/Dockerfile.rag`
- `services/aiops-service/app/ai_enrichment_models.py`
- `services/aiops-service/app/ai_enrichment_routes.py`
- `services/aiops-service/app/ai_evidence_package.py`
- `services/aiops-service/app/ai_provider.py`
- `services/aiops-service/app/analysis_routes.py`
- `services/aiops-service/app/analysis_service.py`
- `services/aiops-service/app/conftest.py`
- `services/aiops-service/app/database.py`
- `services/aiops-service/app/evidence_catalog.py`
- `services/aiops-service/app/fixtures/retrieval-quality.json`
- `services/aiops-service/app/gemini_provider.py`
- `services/aiops-service/app/inference_client.py`
- `services/aiops-service/app/inference_identity.py`
- `services/aiops-service/app/inference_main.py`
- `services/aiops-service/app/inference_security.py`
- `services/aiops-service/app/isolated_analysis.py`
- `services/aiops-service/app/knowledge_config.py`
- `services/aiops-service/app/legacy_usage.py`
- `services/aiops-service/app/main.py`
- `services/aiops-service/app/models.py`
- `services/aiops-service/app/postgres_ledger.py`
- `services/aiops-service/app/project_evidence.py`
- `services/aiops-service/app/rag.py`
- `services/aiops-service/app/remediation_access.py`
- `services/aiops-service/app/remediation_integrity.py`
- `services/aiops-service/app/remediation_models.py`
- `services/aiops-service/app/remediation_policy.py`
- `services/aiops-service/app/remediation_routes.py`
- `services/aiops-service/app/remediation_service.py`
- `services/aiops-service/app/remediation_store.py`
- `services/aiops-service/app/sentence_embeddings.py`
- `services/aiops-service/app/store.py`
- `services/aiops-service/app/test_ai_enrichment_api.py`
- `services/aiops-service/app/test_analysis_service.py`
- `services/aiops-service/app/test_inference_security.py`
- `services/aiops-service/app/test_knowledge_api.py`
- `services/aiops-service/app/test_postgres_inference.py`
- `services/aiops-service/app/test_production_rag.py`
- `services/aiops-service/app/test_release_postgres.py`
- `services/aiops-service/app/test_remediation_reviews.py`
- `services/aiops-service/app/test_remediation_route_auth.py`
- `services/aiops-service/app/test_secure_integration.py`
- `services/aiops-service/app/test_trusted_telemetry.py`
- `services/aiops-service/app/trusted_telemetry.py`
- `services/aiops-service/app/workload_policy.py`
- `services/aiops-service/knowledge/embedding-profile.json`
- `services/aiops-service/knowledge/manifest.json`
- `services/aiops-service/migrations/004_secure_inference.sql`
- `services/aiops-service/migrations/005_remediation_reviews.sql`
- `services/aiops-service/migrations/006_advisory_feedback.sql`
- `services/aiops-service/requirements-embeddings.txt`
- `services/deployment-service/cmd/server/main.go`
- `services/deployment-service/internal/executor/project_telemetry.go`
- `services/deployment-service/internal/executor/trusted_evidence.go`
- `services/deployment-service/internal/executor/trusted_evidence_test.go`
- `services/deployment-service/internal/handler/project_workflow_authorization_test.go`
- `services/deployment-service/internal/metrics/evidence_auth.go`
- `services/deployment-service/internal/metrics/middleware_test.go`
- `services/deployment-service/internal/metrics/project_evidence.go`
- `services/deployment-service/internal/metrics/project_evidence_test.go`
- `services/deployment-service/internal/repository/deployment_remediation.go`
- `services/deployment-service/internal/repository/deployment_remediation_integration_test.go`
- `services/deployment-service/internal/repository/deployment_repository.go`
- `services/finops-service/app/main.py`
- `services/finops-service/app/project_costs.py`
- `services/finops-service/app/project_insights.py`
- `services/finops-service/app/test_project_costs.py`
- `services/finops-service/app/test_project_insights.py`
- `services/infrastructure-service/internal/terraform/drift.go`
- `services/infrastructure-service/internal/terraform/drift_comparison.go`
- `services/infrastructure-service/internal/terraform/drift_comparison_test.go`
- `tests/test_ci_pipeline_hardening.py`
- `tests/test_consolidated_verification.py`
