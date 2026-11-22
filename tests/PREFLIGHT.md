# Source-only preflight regression checks

Install tests/requirements-preflight.txt into a test environment. Run pytest on
`test_release_readiness.py test_preview_safety.py test_deployment_foundation.py
 test_preview_capacity.py test_free_plan_preflight.py test_offline_installation_inventory.py`.
The fixture module preflight_fixtures.py constructs invented test-only schemas,
prices, quotas and balances; it contains no account capture. Fixtures have fixed
future timestamps and fixture_only=true. Deployment preflight rejects that marker
regardless of synthetic acceptance flags. Tests pass their synthetic clock
explicitly. Pricing defaults and current-account assumptions are never embedded
in production tools.

Helm renders only local vendored source. Optional native monitoring checks use
PROMTOOL, AMTOOL and KUBERNETES_OPENAPI paths to independently provisioned local
validation tools/public schemas. No test downloads artifacts or calls AWS.
Generated batch directories, reports, account snapshots, state, caches, real
credentials and private CA keys are excluded from the source-only candidate.
