# Scheduled drift batches (Batch 28)

The existing infrastructure binary supports `drift-scan`. Production requires its
dedicated `cf_drift` TLS DSN, `TERRAFORM_READ_ONLY=true`, remote
state configuration, and no provisioner assume-role ARN. It reuses ScanDrift,
which produces refreshed observation plans and sanitized findings, not apply.
Production requires the expected IRSA role and nonempty projected token, rejects
static keys, and disables EC2 metadata credential fallback. STS authentication
and actual policy permissions still require target acceptance.
No frontend signing keys or saved-plan workspace PVC is supplied to this job.

Renderer `drift.enabled` defaults false. When explicitly enabled, require a real,
distinct `roles.drift` ARN and `secrets.cloudforge-drift-db` mapping. The DB role
can read resource/plan metadata and append bounded history only through a fixed
migration-owned definer function. The actor is fixed, search_path is pg_catalog,
objects are qualified and active/revision row locking is preserved. No resource
UPDATE (including timestamps), direct history mutation, approval or account
privilege is granted. A standard hourly CronJob uses a dedicated
`cloudforge-drift` service account, no API token, 120s deadline, zero retries and
Forbid concurrency. The CLI has a 90s bound and PostgreSQL advisory transaction
lock across instances. It selects at most five least-recently-scanned active
resources, persists the existing optimistic-revision scan history, and exits
nonzero on drift, unavailable evidence, overlap or stale state. Empty batch
success is not full-fleet compliance. Fleet scan latency depends on size/frequency.

`bootstrap/drift.tf` prepares an opt-in read-only IRSA role: exact service-account
trust, state GetObject/ListBucket, regional Describe inventory, scoped IAM role
reads and only approved application bucket metadata. No S3 put/delete/lockfile,
PassRole, provisioning or assume-provisioner privilege is granted. Regional
Describe APIs need Resource `*`; review target IAM conditions independently.
RDS scans needing a Secrets Manager value intentionally fail unavailable until
separately reviewed exact secret/KMS read permission is provided. Provider-mirror,
DNS, CA, state, AWS API and STS network reachability remain target prerequisites.

Prometheus's existing rule glob loads `cloudforge-drift-alerts.yml`. It alerts on
failed/review-required jobs and a >2h unsuccessful scheduler, including a job that
has never succeeded. Required kube-state-metrics job/cronjob metrics are listed
in its example values. Failure does not imply a specific root cause: inspect
persisted scan history and logs. Exporter absence is not measured health; verify
scrape/absence alerting separately. Job retention does not replace audit retention.

VERIFIED locally: bounded configuration, offline alert pending/recovery math,
real PostgreSQL history, overlap denial, unavailable evidence and stale revisions
under the scoped runtime principal. The observer in DB tests is an explicit
fixture; no AWS observation was executed. A nullable legacy description bug found
by the fixture was fixed in repository read queries without rewriting data.

PARTIAL/BLOCKED: actual CronJob execution, IRSA/permissions, AWS provider reads,
full-fleet cadence and live alert transport. No role was created, CronJob run or
Terraform apply performed. Human approval and fresh saved plans remain mandatory
for remediation. This feature never produces or consumes an apply approval.
