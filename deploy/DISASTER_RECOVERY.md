# Disaster recovery and chaos drills

## Safety and evidence

Production recovery is **BLOCKED pending independently recorded human approval**.
Record incident, authorized Platform Engineer, separate approver, verified source
backup/version and checksum, exact target, recovery point, expected data loss,
execution window and rollback. Confirm target identity with a second person.
Neither an AI recommendation nor a restored approval row authorizes execution.
Never restore over an existing database or roll back secrets/state automatically.
Keep Terraform execution disabled and remediation/promotion stopped throughout
recovery. Reconcile uncertain operations and obtain fresh bound plans/approvals
before permitting mutations. Session revocations newer than a backup may be lost:
rotate signing keys and invalidate restored sessions before reopening access.

The local drill has no existing-target or cloud argument. It creates uniquely
named/labelled fixtures, refuses unowned targets, never pulls images, uses an
internal network and no published ports, and cleans up only its resources.
Synthetic data includes account roles, memberships, approvals, deployment attempts
and audit history. Faults are preauthorized only for those disposable fixtures.
Do not point the fixture SQL or commands at an application database.

```sh
# Requires the reviewed pinned recovery image, Docker, Go, Python 3, AIOps .venv,
# cached cloudforge-ai-aiops-service and prom/alertmanager:v0.28.1 images.
# Build/review instructions: deploy/RECOVERY_IMAGE_SECURITY.md
python3 scripts/test-recovery-chaos.py --output-dir /tmp/cloudforge-recovery-UNIQUE
pytest -q tests/test_recovery_chaos.py
```

The output directory must not exist; it is mode 0700. `evidence.json` records
PASS/FAIL, durations, cleanup failures and BLOCKED scenarios. `synthetic.dump`
is a verified fixture archive (0600), not a production backup. Keep output outside
Git. Inspect any cleanup failure by its exact fixture ID; never use global Docker
prune, wildcard deletion or volume cleanup. The script uses the inspected local
image ID. Verify image provenance/scanning separately before reuse.

## PostgreSQL backups and recovery

For production use established PostgreSQL tooling (managed database PITR or a
reviewed pgBackRest/Barman deployment), encrypted offsite storage, separate backup
credentials, retention/immutability and alerting on backup age/WAL archive lag.
This procedure does not configure production archiving or create a backup service.
Protect account hashes, sessions, incident logs and audit evidence as sensitive.

Capture all application schemas, migration receipts, extensions and roles/grants;
logical `pg_dump -Fc` does not include globals, server configuration or credentials.
Use credential files/secret injection, never inline passwords. Verify checksums,
`pg_restore --list`, server/extension compatibility and storage before restoration.
Restore first to a fresh, network-isolated target using `pg_restore
--exit-on-error --single-transaction`; compare tables, canonical row fingerprints,
foreign keys, sequences, project membership, audit and approval history. Validate
least-privilege login grants separately. Do not use `--clean` on an existing target.

The real local drill applies all 23 Go SQL migrations in service order, takes a
custom-format dump, restores to another fresh PostgreSQL instance and checks all
public table rows plus a post-restore identity-sequence insert. It then uses
`pg_basebackup -X stream`, actual archived WAL, a named restore point and a third
fresh instance with `recovery_target_action=pause`. Inclusion/exclusion of writes
and a full table fingerprint prove the target was reached. It never promotes a
recovery target or performs cutover. AIOps startup DDL runs twice against the real
fixture before backup; authenticated firing/resolved webhook history is included
in both logical and PITR fingerprints. A real disposable Alertmanager also sends
an injected firing/resolved alert over authenticated HTTP to the current AIOps
code; its persisted incident/event history is included before backup. A private Unix socket under the 0700
output directory and a per-run database ownership proof isolate this fixture.
Production role grants, backup encryption/retention, large databases and offsite
loss remain unverified.

**RTO:** drill elapsed times include local Docker/SQL probes; logical restore
includes dump creation and target initialization. PITR RTO starts at copying the
base backup and ends at verified paused recovery (the final full fingerprint is
also included). Neither measures DNS, secrets, operator response or live cutover.
**RPO:** zero committed fixture rows lost at the logical snapshot; PITR includes
all fixture rows through the named point and intentionally excludes one later
row. This is target correctness, not a continuous production RPO guarantee.
Production RPO is the last independently verified recoverable WAL timestamp
relative to incident time. Define and approve objectives before deployment.

## Kubernetes / GitOps reconstruction (not executed)

Preserve Git commit, signed immutable image digests/provenance, rendered manifests,
controller/CRD versions, non-secret release inputs, namespace policies and encrypted
PVC backup references. Git is desired configuration, not a database/PVC backup.
No GitOps controller is installed by this batch. Use the existing reviewed
renderer and release checklist; do not invent cloud identities or storage classes.

After approved target provisioning, restore secrets/identity and data first;
start project migrations, then infrastructure/deployment, then AIOps/FinOps and
frontend. Check receipts, database readiness, RBAC, isolation, default-deny
networking, RWX workspaces, HPA/PDB capacity, Argo prerequisites and controller
ownership. Reconcile execution leases and uncertain Terraform/Kubernetes actions
before admitting work. Use native/Argo rollback approval gates; never restore
traffic solely because an API row says succeeded. Require actual health evidence.

## Terraform state and secrets recovery (not executed)

Preserve S3 versioning/encryption/public-access blocks, state key mapping,
lockfile policy, KMS access and approved-role trust in separately protected
inventory. Back up saved-plan/workspace references without exposing plan values.
A Terraform state resource ID is not live AWS verification. After independent
approval, compare lineage/serial, object version, current lock owner, audit events
and read-only provider observations before selecting a version. Do not force-unlock,
push state, copy older state over current state, apply or destroy automatically.
An old saved plan/approval must never become executable merely through restore.

For Secrets Manager, preserve secret ARN/property mappings, versions, KMS policy,
IRSA trust and external-secret synchronization definitions. Recover verified
versions through authorized tooling, validate payloads privately, rotate exposed
keys and test revocation. Never put recovered secret values into Git, command
history or evidence logs. Offsite secret/state restoration and lock recovery
require separately approved live acceptance.

The original cached image is rejected. The reviewed PostgreSQL 16.16 derivative
is pinned by its local image config digest; see [the image review](RECOVERY_IMAGE_SECURITY.md)
and [measured evidence](RECOVERY_EVIDENCE.md). Its registry publication and
production acceptance are separate gates. Refresh the vulnerability database and
repeat security/restore checks before release use; no production image was changed.
