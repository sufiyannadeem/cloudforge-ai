# Local recovery evidence — 2026-11-19

The first section is the historical Batches 25–26 baseline. Its image/AIOps/OOM
blockers are superseded by the recovery-security validation below.

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


## Recovery security validation — final image

Fixture `cf-drill-262273c65391496b8a7b684a0b9dc060` used the actual non-root local
image config digest
`sha256:8609eed620cb7660c35f409afeac1a4a921c781079a690b9872f4197dae714f7`.
See [the full 48-finding review and fixed versions](RECOVERY_IMAGE_SECURITY.md).
The PostgreSQL 16.16 runtime defaults to UID/GID 70:70 and removes vulnerable Go
binaries from all distributed layers. Trivy 0.76.2 reports **0 HIGH/CRITICAL image
vulnerabilities and 0 HIGH/CRITICAL Dockerfile findings**, with no new exceptions.
Its database was updated 2026-11-19 07:06:49 UTC. Lower-severity/unknown issues and
future database updates are not covered by this claim.

| Check | Result | Measured elapsed |
| --- | --- | --- |
| Real AIOps startup DDL twice, authenticated ASGI firing/resolved ingest | PASS; unauthorized requests denied; durable events | 0.610s |
| Real Alertmanager HTTP delivery/resolution to AIOps | PASS; injected alerts over new internal network; incident/event history retained | 5.549s including startup |
| Logical restore | PASS; 23 migrations, **22 tables** including AIOps; all-row fingerprints and sequence check | 3.680s including dump and target initialization |
| Archived WAL/PITR | PASS; all-table fingerprint; exact target paused; one later row excluded | 2.576s recovery; 5.120s with base backup |
| Service crash/restart | PASS | 0.333s |
| Database crash/reconnect | PASS; readiness 503/liveness 200 during outage; committed rows intact | 2.502s |
| Network reconnection | PASS | 1.342s |
| Bounded scratch ENOSPC | PASS | 0.189s |
| **Real cgroup-v2 kernel OOM** | PASS; 256MiB hard memory/swap ceiling; PID1 killed and restarted; final data intact | 0.373s |
| Graceful shutdown/integrity | PASS; exit 0, all-row fingerprint unchanged | 1.796s |
| Cleanup | PASS; no reported cleanup failures | not production RTO |

RPO remains zero committed fixture rows lost **through the chosen recovery point**;
PITR deliberately excludes one later write. Production RTO/RPO, dataset scale,
operator response and cutover are not measured. Raw sanitized runtime evidence
is `/tmp/cloudforge-recovery-security-complete/evidence.json`, outside Git.

The existing DeploymentServiceDown rule passed offline promtool checks for its
one-minute hold, firing and clearing. Actual Alertmanager delivery was exercised
with injected alerts; no live Prometheus-to-Alertmanager scrape-fault chain is
claimed. The transport used cached AIOps and Alertmanager images resolved to
immutable local IDs, with current AIOps source mounted read-only; this is not a
release approval of those images.

Focused regression evidence: 44 drill/foundation Python tests, 38 AIOps
telemetry/anomaly/readiness tests, and deployment worker/executor/workflow Go race
suites passed. Setup/interruption/unexpected errors now report FAIL, never an
empty PASS. A private socket and per-run database proof guard AIOps schema setup.
No existing application database, monitoring history or production image changed.

Remaining gates: derivative registry publication/provenance and production image
selection; production grants, encrypted/offsite backup retention and large-dataset
restore; full Prometheus/SLO fault response, external notifications; Kubernetes
PDB/PVC/node/GitOps/Argo recovery; AWS state/lock/secrets/IAM restoration. Independent
human approval remains required for destructive recovery. No AWS/EKS access,
Terraform operation, cluster deployment, push or PR mutation occurred.
