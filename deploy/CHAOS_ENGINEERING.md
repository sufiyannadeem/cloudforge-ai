# Local chaos verification

Run `scripts/test-recovery-chaos.py` as described in
[the recovery runbook](DISASTER_RECOVERY.md). Docker fixtures are isolated from
existing containers, databases, host ports and external networks. The script
bounds container memory/CPU, scratch space, subprocesses and recovery polling.
It never changes existing infrastructure or installs tools/controllers.

| Scenario | Evidence required |
| --- | --- |
| SIGKILL project-service + restart | real service `/ready` returns 200; unsigned `/projects` denied |
| SIGKILL PostgreSQL + crash recovery | `/ready` 503 while `/health` remains 200; reconnect succeeds; committed data fingerprint unchanged |
| Service network disconnect/reconnect | readiness fails closed, then recovers without process replacement |
| Bounded scratch exhaustion | real ENOSPC in dedicated 1MiB tmpfs; space released; readiness succeeds |
| Graceful SIGTERM | server exits 0 within stop budget; durable data unchanged |
| Logical restore / WAL recovery | separate real PostgreSQL targets, checksum, table fingerprints, sequences, precise restore point |

Scratch exhaustion is not an OOM, CPU starvation, database disk-full or node-loss
test. These require separate disposable capacity and are BLOCKED here. No local
Kubernetes cluster, failed rollout, load balancer failover or real controller
rollback is claimed. Existing executor/worker tests cover cancellation, lease
fencing and failed rollout logic, but fixtures do not establish live recovery.

Run focused AIOps SLO/anomaly tests with existing tooling to preserve insufficient
coverage/freshness behavior. Alert delivery, end-to-end SLO changes during these
faults and monitoring-history durability remain BLOCKED until a disposable
Prometheus/Alertmanager integration is independently exercised. Do not scrape
fixture readiness as a substitute for the user-facing SLI or claim healthy
compliance without adequate samples. Preserve anomaly minimum sample counts.

Stop on unexpected target identity, data changes, missing approval, unbounded
fault impact, cleanup failure or failed assertions. Retain sanitized evidence;
do not retry destructive production operations to make a test pass. Local drill
results and production recovery objectives must remain separate.
