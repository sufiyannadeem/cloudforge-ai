# Dedicated database principals (Batch 28)

Production runtime now requires `cf_project`, `cf_infrastructure`, `cf_deployment`,
`cf_aiops`, `cf_finops_project`, `cf_finops_audit` and the scheduled worker
`cf_drift` respectively, and verified
TLS (`sslmode=verify-full`, actual DNS hostname and trusted CA). No shared-user or
plaintext fallback is accepted. Mount the real public CA at
`/etc/cloudforge/db-ca/ca.crt`; `PGSSLROOTCERT` or a DSN parameter selects it.
The server must reject non-TLS network connections and use SCRAM or approved
certificate authentication. Do not disable certificate verification for a proxy.

Runtime identities have no schema/DDL ownership. Production startup does not run
migrations. Development startup retains its previous migration behavior. The
explicit Go `server migrate` command and AIOps `python -m app.database` accept
`cf_migrator` with verified TLS in production, then exit without serving traffic.
Migration credentials must never be mounted in runtime pods.

For a **new or separately approved** dedicated database, a DBA executes
`001_principals.sql`, securely configures independent random credentials using
approved secret tooling, and then runs existing migrations in this order:

1. Project image with args `migrate` (001–006).
2. Infrastructure image with args `migrate`, `TERRAFORM_READ_ONLY=true` (001–011).
3. Deployment image with args `migrate` (001–006; no Kubernetes credentials needed).
4. AIOps image with command `python -m app.database`.
5. As migration owner, execute `002_runtime_grants.sql`; verify all 23 receipts.

These files are deployment bootstrap/grant instructions, not replacements for
historical migrations. No passwords are embedded; newly created login roles have
NULL passwords and cannot authenticate with a password until separately set.
Existing unsafe role attributes/memberships/runtime ownership cause failure.
Do not run ownership reassignment, revoke legacy access, rotate credentials or
restore an existing database automatically. Back up, inventory owners/grants,
review the handoff and drain services before a production transition. Retire the
old shared principal only after independent negative-grant and cutover checks.

Runtime ACLs are explicit, not blanket future grants. Table and column ACLs are
reset before applying the reviewed allowlist; migration-owned append functions
use a fixed search path and qualified objects, with no resource UPDATE grant to
the scheduled reader. Other services cannot read
account hashes/sessions or mutate users. Deployment can read approver public
identity and consume only the dispatch column of an AIOps approval; it cannot
forge approval fields. FinOps has project/resource metadata reads and a separate
SELECT/INSERT-only audit login. Apply/review a grant update after future migrations.
Compromise of the identity-owning project service remains a trust-root risk;
these grants do not constitute per-user database RLS or tamper-proof auditing.

The Kubernetes renderer uses four independent DB Secret references and a
required existing CA ConfigMap. Production Compose now requires independent DSNs
and the public CA path; its optional database still requires separately configured
server TLS. A client DSN alone does not configure the database server certificate.

Local proof (fresh labelled fixtures only):

```sh
python3 scripts/test-database-boundaries.py /tmp/cloudforge-db-boundaries-UNIQUE
```

This uses the reviewed cached PostgreSQL image, cached AIOps image, ephemeral
self-signed test CA, actual TLS connections, all one-shot migration commands,
role/grant denials and a real non-owner HTTP server. No live DB is targeted.
External CA/secret distribution, existing ownership handoff, grants under the
production DBA role, TLS proxy/RDS behavior and cutover remain BLOCKED until
separately approved and tested. The older recovery drill explicitly uses
**development** policy for its isolated non-TLS fixtures; it is not a production
TLS acceptance test.
