Run against a local development server connected to test backend services. Use dedicated accounts in a disposable or local test database. The suite creates projects, users and memberships, tests denied requests and revokes its login sessions. Terraform execution must remain disabled.

Install Chromium with `npx playwright install chromium`. Export `E2E_BASE_URL` (defaults to `http://127.0.0.1:3100`), `E2E_DEVELOPER_USER`, `E2E_SRE_USER`, `E2E_PLATFORM_ENGINEER_USER`, and their common `E2E_PASSWORD` from a private test fixture. Optionally set a unique `E2E_PROJECT_NAME` per run. Then run `npm run test:e2e`. Without account credentials the role tests are skipped.

The tests use real local sessions and signed backend requests. Backend tests cover replay, stale identity, session revocation, membership isolation and audit transactions. Cloud costs remain unavailable unless verified resource attribution exists.

Run `scripts/test-finops-audit-postgres.sh` from the repository root to execute the FinOps audit tests against the existing local Docker PostgreSQL. The runner creates and removes a dedicated schema and preserves application data.
