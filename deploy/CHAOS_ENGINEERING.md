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
| Hard cgroup OOM | fixed 512MiB allocation under a 256MiB memory/swap ceiling; verify kernel OOM and recover readiness/data |
| AIOps alert recovery | real startup schema, authenticated ASGI checks and actual Alertmanager HTTP delivery/resolution with persisted history; included in restore |
| Graceful SIGTERM | server exits 0 within stop budget; durable data unchanged |
| Logical restore / WAL recovery | separate real PostgreSQL targets, checksum, table fingerprints, sequences, precise restore point |

Scratch exhaustion is separate from the real cgroup-v2 OOM check. The OOM helper
only runs inside the capped disposable service container; never execute it on the
host. A missing memory.events interface is reported BLOCKED, not PASS.
CPU starvation, database disk-full and node-loss tests remain BLOCKED. No local
Kubernetes cluster, failed rollout, load balancer failover or real controller
rollback is claimed. Existing executor/worker tests cover cancellation, lease
fencing and failed rollout logic, but fixtures do not establish live recovery.

The offline `monitoring/prometheus/tests/recovery-alerts.test.yml` checks the
existing DeploymentServiceDown hold period, firing and clearing. Run it with
cached promtool using a read-only rules mount, no network and bounded writable
`/tmp`; this is rule evaluation, not Alertmanager transport acceptance.

Run focused AIOps SLO/anomaly tests with existing tooling to preserve insufficient
coverage/freshness behavior. Injected-alert transport to AIOps is tested locally;
end-to-end Prometheus scraping/SLO changes during faults, external notification
channels and monitoring-history durability remain BLOCKED until independently
exercised in the intended environment. Do not scrape
fixture readiness as a substitute for the user-facing SLI or claim healthy
compliance without adequate samples. Preserve anomaly minimum sample counts.

Stop on unexpected target identity, data changes, missing approval, unbounded
fault impact, cleanup failure or failed assertions. Retain sanitized evidence;
do not retry destructive production operations to make a test pass. Local drill
results and production recovery objectives must remain separate.
