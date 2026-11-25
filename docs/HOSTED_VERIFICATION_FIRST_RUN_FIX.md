# First hosted Consolidated Release Verification: focused fixes

Reviewed the complete 1,252-line log and every job/step result of
[run 45570072860](https://github.com/sufiyannadeem/cloudforge-ai/actions/runs/45570072860),
source `9d0aff98373fac38b67a15d69879580dc57f2e71` on main.

## Confirmed root causes

1. **Native job, provider mirror:** bootstrap mirrored, then dev failed at
   `vpc.tf:1` with `Module not installed`. Provider discovery traverses module
   dependencies, but the fresh checkout had not acquired the pinned VPC module.
   The hosted acquisition step now runs `terraform get -no-color -update=false`
   on both roots before mirroring either root. This acquires the exact configured
   module versions without initializing a backend or providers. The existing approved
   hosted-only step, credential guard, platform selection and lock diff check remain.
   Subsequent filesystem-mirror validation adds `-get=false` and `-input=false` to
   backend-disabled, read-only-lock init: missing cached modules fail rather than
   trigger a module download during offline validation. Dedicated runners therefore
   still need their approved preloaded modules and provider mirror.
2. **PostgreSQL job, final inference ACL guard:** four real inference tests passed;
   the four release tests errored during shared fixture setup in
   `deploy/postgres/003_inference_grants.sql`. PostgreSQL evaluated a sequence
   privilege call against `auth_users`, raising `WrongObjectType`. A sibling
   `AND c.relkind='S'` condition cannot enforce evaluation order. Both relation
   scans now put their type-sensitive privilege functions inside `CASE` branches:
   sequence-only for sequence privileges and the existing table-like kinds for
   table/column privileges. All privilege lists, namespace filters, ownership/DDL/
   function restrictions and the fail-closed exception remain intact.
3. **Aggregate job, Python line 7:** the unchanged assertion requires success for
   plan, native and the active PostgreSQL branch. Logged results were plan=success,
   native=failure, postgres-hosted=failure, postgres-dedicated=skipped. This is the
   correct downstream failure, not an independent defect. No gate was weakened.

## Equivalent-query audit and remaining observed stages

Repository-wide audit of `has_sequence_privilege`, `has_table_privilege`,
`has_any_column_privilege` and `has_column_privilege` found only these unsafe
mixed-catalog calls. Existing real-test calls choose types in Python before separate
SQL executions, or address explicit known tables/columns. Column-grant revocation
loops filter relation kinds before their PL/pgSQL loop body; they do not invoke
privilege functions in reorderable SQL predicates.

No additional independent failing step appears in the complete log. Approval-bound
planning, hashed native tools, 314-schema generation, hashed Go acquisition, service
startup, synthetic DB/role bootstrap and Go module acquisition succeeded in that run.
Native actionlint, rendered/native schema/Prometheus/Terraform/TLS checks never ran
because mirroring failed first. Native Go atomic dispatch never ran because the
Python database gate failed first. Those unexecuted stages remain unverified, and
fixing the two observed causes does not prove they will pass.

## Regression checks and limits

- **26 passed:** hosted workflow ordering using a fake Terraform executable on a
  clean synthetic cache; offline init flags; aggregate success/failure cases for both
  profiles; mixed-kind ACL predicates using SQLite CASE evaluation with type-checking
  privilege UDFs; and the nine existing consolidated gate-mechanics tests.
- **21 passed, 3 deselected:** cached CI hardening checks, excluding real Terraform
  execution and the duplicate in-test Gitleaks invocation. These are local source
  checks, not a changed CI selection.
- **Eight real PostgreSQL tests collected, not executed.** The existing ACL test now
  executes the actual production DO guard with tables, an index, a sequence, a view,
  a materialized view, a partitioned table and a composite relation. It also verifies
  fail-closed rejection and savepoint rollback of direct and PUBLIC table, column
  and sequence grants. Keeping this within the existing test preserves the mandatory
  exact eight-case gate; no required case is skipped or removed.
- Changed Python/workflow source parses; whitespace check passes. A full staged-tree
  secret scan is required before commit. `terraform get -help` confirmed available
  cached command flags; no module/provider acquisition was performed locally.

The SQLite regression checks SQL CASE semantics with deliberate wrong-type errors;
it does **not** establish PostgreSQL catalog/ACL behavior. New real mixed-relation
coverage must run in the approved hosted PostgreSQL gate. Native success is also
unclaimed. No database, local cluster, AWS call, provider/model download, manual
workflow dispatch or production action was performed while preparing this fix.

## Acquisition and approval impact

`ci/integration-acquisition.json` remains byte-for-byte unchanged:

```text
229740c6df87058f6c06162b908b8f48a9b408a5979ab6b5079492e0669e2d45
```

Both Terraform provider locks and the pinned VPC module `6.7.3` are unchanged.
No approval, environment, permission, same-SHA binding, scanner setting or protected
main rule changes. After protected review/merge, hosted verification must run at the
new exact reviewed SHA; the failed run cannot authorize semantic preparation or a
production release. This change neither dispatches that run nor grants its approval.
