# Batch 22 PR review

Read-only GitHub review on 2026-11-19. Compared all 16 open PR heads with fetched
`origin/main` (`7eafd35`) and `v1.0.0-rc1` (`70f7464`), including manifest changes,
lockfiles and patch applicability. No PR was changed. All currently have failed
checks; none should merge immediately. GitHub reports each mergeable against main,
which does not establish compatibility with rc1. No complete patch is already
merged-equivalent in either baseline.

| PR | Change | Recommendation | Comparison and required follow-up |
| --- | --- | --- | --- |
| #49 | FastAPI 0.162.4 | Retain | Valuable unmerged update; patch applies to both. Test AIOps/auth compatibility after release baseline integration. |
| #48 | Pydantic 2.14.3 | Retain | Valuable unmerged update; patch applies to both. Test request validation/serialization with FastAPI. |
| #47 | Deployment pgx 5.13.0 | Retain/rebase | Applies to main; rc1 go.mod/go.sum conflicts. Preserve service-identity replacement and newer x/text. Test repository/race/PostgreSQL paths. |
| #46 | Project pgx 5.13.0 | Retain/rebase | Applies to main; conflicts with rc1 module/security changes. Preserve identity module and account/migration tests. |
| #45 | Infrastructure pgx 5.13.0 | Retain/rebase | Applies to main; conflicts with rc1 module/security changes. Preserve identity module and approval/persistence tests. |
| #43 | psycopg 3.3.8 | Retain/rebase | Applies to main; requirement context conflicts with rc1 additions. Keep boto3/httpx2 and run PostgreSQL tests. |
| #41 | Sonar scan action 8.4.1 | Merge candidate after green CI | SHA-pinned patch applies to both baselines; no replacement of rc1 workflow. |
| #35 | setup-python 7.1.0 | Merge candidate after green CI | SHA-pinned patch applies to both; validate runner compatibility. |
| #34 | React 19.3.1 | Retain/rework | Applies to main; rc1 lockfile conflicts. Updates React alone while react-dom remains 19.3.0: coordinate versions and test frontend. |
| #33 | Node types 26.6.5 | Retain/rework | Applies to both; runtime is Node 22, while both baselines already use Node 26 types. Align types with runtime before accepting more Node-26-only API surface. |
| #32 | eslint-config-next 16.4.1 | Close as superseded after rc1 reaches main | rc1 already has 16.4.5. Useful for old main only; do not downgrade release configuration. |
| #29 | Next.js 16.4.1 | Close as superseded after rc1 reaches main | rc1 already has 16.4.5; conflicts with its package/lockfile. Do not downgrade patched release. |
| #28 | Prometheus Go client 1.25.0 | Retain | Raises Go requirement from 1.25.14 to 1.26.0 and updates transitives. Coordinate CI/Docker toolchains; rc1 modules conflict. |
| #27 | ESLint 10 | Retain | Major upgrade; rc1 lockfile conflicts. Validate plugins, Next config and Node engine requirements separately. |
| #23 | upload-artifact 7.0.2 | Merge candidate after green CI | SHA-pinned two-line patch applies to both. Preserve rc1 expanded image matrix and security guardrails. |
| #16 | Uvicorn 0.54.0 | Retain | Applies to both; run ASGI/startup/shutdown/auth regressions. |

Nine patches conflict when checked directly against an exported rc1 tree:
#47, #46, #45, #43, #34, #32, #29, #28, #27.
Context/lockfile conflicts are not proof of semantic incompatibility. Rebase or
regenerate the dependency-only patch; never replace rc1 files with old PR snapshots.
Existing check failures were observed, not attributed to these dependency changes.
Dependency upgrades were not installed or tested during this deployment-foundation task.

Some transitive security updates (notably x/text 0.41.0) are already present in rc1, but the complete pgx and Prometheus update patches are not. Preserve those newer versions during conflict resolution.
