# Tamper-evident centralized audit — design boundary

Status: **PARTIAL (design)**. Existing per-service audit persistence remains
implemented. No central collector, signing service, immutable bucket or retention
policy was installed, and none is claimed to exist. This design does not turn a
mutable database hash into tamper-proof storage.

## Sources and trust

Capture account_admin_audit; infrastructure_plan_reviews and assertion usage;
deployment_attempts, deployment_promotions and diagnostics metadata;
aiops_incident_events and remediation decisions/dispatch consumption;
terraform_drift_scans; finops_anomaly_captures. Include failures, denials,
revocations, migrations and destructive recovery authorization. Current source
coverage is incomplete for raw DBA changes and all authentication denials.

Use an established OpenTelemetry Collector distribution for transport and an
approved PostgreSQL/outbox adapter, not a new controller or queue. Selecting and
validating the supported SQL/CDC adapter and transactionally complete capture is
implementation work still required. An stdout-only collector must not be called
complete database auditing. Source ownership/approval records remain unchanged.
The exporter identity must be separate from all runtime and migration principals;
it reads only sanitized audit projections/outbox, never account hashes/sessions,
Terraform values, secret payloads, logs or arbitrary configuration JSON.

## Envelope and checkpoints

A v1 envelope contains event_id, source_service, source_table, source_primary_key,
source_watermark, collector_sequence, occurred_at, observed_at, authenticated_actor
identifier, action, project/resource identifiers, outcome and approved-request
binding hash. Hash canonical UTF-8 JSON with stable field order/types and no floats.
Allowlist fields; reject unknown payloads. Pseudonymize sensitive actor attributes
under approved retention policy. A signature/approval hash is not an approval token.

For each independently identified stream, compute
`H(n) = SHA256(version || H(n-1) || canonical_event(n))`, with fixed-length/framed
inputs. Persist a monotonically increasing sequence and resumable source watermark;
bound retries, deduplicate by immutable source event ID and emit explicit gap/error
records. Never silently advance past failed exports or label empty data healthy.

Batch checkpoints contain stream ID/generation, sequence range/count, previous
checkpoint hash, final chain hash, source watermark and observation time. An
independent signing identity signs canonical checkpoint bytes using an approved
asymmetric KMS/HSM key. Runtime services, DBA/migrator and export workers cannot
use that key. Verify against pinned public keys and record rotation/revocation.
A second security-controlled store receives signed checkpoints to detect rollback
or total-chain replacement. A hash chain without a trusted retained anchor detects
neither a rewritten whole chain nor missing unanchored tail events.

## Retention and verification

Use separately administered encrypted immutable/WORM storage with explicit legal
retention, lifecycle/cost budget and deletion separation. Object Lock mode and KMS
policy require independent approval; do not enable them by Terraform apply as part
of this batch. Exporters may append new objects, not overwrite/delete history;
verifiers read only. Protect checkpoint/admin access with independent identities.

Offline verification must reject changed/deleted/reordered/duplicated events,
wrong stream/generation, invalid signatures, stale/rolled-back checkpoints and
broken source watermarks. It must distinguish anchored evidence from pending
exports. Test key rotation, clock skew, retry/duplicate recovery, unavailable
signer/storage and recovery from an old database backup without resetting history.

Alert on export age, source/sequence gaps, checkpoint/signature failure and
retention-policy drift through existing Prometheus/Alertmanager. Run real delivery
and restore drills before calling this integrated. The accepted RPO includes the
unanchored export window; a compromised producer can still lie before capture.
These controls prove evidence integrity after anchoring, not actor honesty or
non-repudiation of the current symmetric frontend assertions.

Production gates: approved schema/projections and grants, collector/adapter
version/digest, real TLS identity, independent signer/public-key policy, WORM
retention/cost approval, append-only end-to-end tests and operational ownership.
Until those pass, centralized tamper-evident audit remains **BLOCKED for use**.
