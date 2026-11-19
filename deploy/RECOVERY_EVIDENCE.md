# Local recovery evidence — 2026-11-19

Final fixture: `cf-drill-a51f2ed7b37046afa2e645e88f6a7faf`.

Executed `scripts/test-recovery-chaos.py` against newly created Docker fixtures,
Docker 29.1.3, cached PostgreSQL 16 Alpine image
`sha256:81bd698b4594e751a3269e4dcd3e03a4a0ec0daf7b72e7aa1abd43cce9887542`.
Project-service was compiled from this checkout. No image pull, existing database
restore, Kubernetes or AWS access occurred. Outputs remained under `/tmp`, outside
Git. The evidence is a small synthetic local test, not production acceptance.

| Check | Result | Measured elapsed |
| --- | --- | --- |
| Logical backup and fresh restore | PASS: 23 migrations, 17 tables, all-row fingerprints, identity sequence | 5.455s including dump and target initialization |
| Base backup + archived WAL to named restore point | PASS: all-table fingerprint, retained WAL write, excluded later write; paused, not promoted | 3.865s recovery; 7.823s including base backup |
| Actual project-service SIGKILL/restart | PASS: readiness returned, unsigned projects request denied | 0.530s |
| Actual PostgreSQL SIGKILL/restart | PASS: readiness 503/liveness 200 during outage; committed data unchanged | 3.250s including outage detection |
| Actual service network disconnect/reconnect | PASS: readiness 503 then 200 | 1.535s |
| Dedicated 1MiB scratch exhaustion | PASS: ENOSPC, release, service ready | 0.337s |
| Graceful service stop + final data integrity | PASS: exit 0; all-table fingerprint unchanged | 2.285s |
| Fixture cleanup | PASS: no reported cleanup failures | not an RTO measurement |

Logical RPO: no committed synthetic rows lost at the backup snapshot. PITR:
no rows lost through the selected restore point; one later write deliberately
excluded. This measures recovery-point correctness, not continuous time-based
production RPO. Production RTO/RPO and offsite loss remain UNVERIFIED.

Focused regressions: 39 infrastructure/drill safety Python tests; 38 AIOps
telemetry/anomaly/readiness tests; deployment executor/worker/workflow Go race
packages passed. These tests preserve insufficient-data and authorization logic;
they do not establish live alert or Kubernetes rollback delivery. Trivy secret
scan of the new drill/fixture found no secrets; staged Gitleaks/diff checks must
also pass before commit.

BLOCKED: Kubernetes/GitOps/PVC restoration, actual failed rollout/rollback,
end-to-end alert delivery and SLO fault response, AIOps startup-schema backup,
production roles/grants and encrypted/offsite backups, AWS state/secrets recovery,
OOM/node failures and production-size recovery. Follow
[the recovery runbook](DISASTER_RECOVERY.md) and obtain separate human approval
before destructive recovery. No automatic remediation or production recovery
endpoint was added.

Image security gate: **FAIL/BLOCKED**. Offline Trivy 0.76.2 scanning of the cached
PostgreSQL fixture image reported **47 HIGH and 1 CRITICAL** vulnerabilities
(krb5-libs, libxslt, musl/musl-utils, zlib and embedded Go stdlib). No exceptions
were added. This existing cached image was used only in isolated disposable
fixtures; do not treat it as an approved release image. Refresh to a reviewed,
patched cached image, verify provenance and rerun vulnerability/restore checks
before release acceptance. The offline database was reused, not refreshed.
Docker label-filtered checks confirmed no drill containers, named volumes or
networks remained; the initial trial's anonymous image volume was traced through
its container events and removed. Final cleanup removes anonymous volumes too.
