# Isolated AI inference release inputs

These are **unapplied** manifests and patches. Disclosure and external egress are
closed by default. Replace all `REPLACE_*` inputs using the approved release overlay.
No Kubernetes Secret, Role, RoleBinding, host mount, exec credential, or business
DSN is needed in the inference pod. The STS-audience projected token cannot be used
as a Kubernetes API token. CSI uses Secrets Manager without `secretObjects` sync.

Build the separate image using `services/aiops-service/Dockerfile.inference`, with
that service directory as build context. It copies only explicitly listed modules;
never replace this with a copy of the AIOps application tree. Sign/scan and pin its
digest in the release overlay. No image was built in this batch.

Apply DB migrations as a separate DBA operation in this order: existing service
migrations, `services/aiops-service/migrations/004_secure_inference.sql`, then
`deploy/postgres/003_inference_grants.sql`. Review PUBLIC privileges first (including
TEMP and function execution). The latter script fails if the inference role still
has business-table or schema/DDL access. On RDS, grant only the required `rds_iam`
authentication membership after that audit; never grant service/migrator roles.
Migration identity must not be mounted in either runtime workload.

Stop all legacy inference workers. For **every** original SQLite ledger, run
`scripts/import-ai-budget.py --source-id <stable-original-ledger-id> --sqlite <snapshot>`
with the migrator DSN and verified TLS. Reads are read-only; logical row digest and
source identity make re-import idempotent and changed snapshots an error. Zero-cost
attempts and timestamps are preserved. Import total reservations without clamping
an exhausted historical balance. Run `--finalize` only after every ledger has been
accounted for (or an operator has confirmed no previous ledger exists). There is no
runtime import, refund, reset or fallback. Until finalized, all reservations deny.
The fixed function serializes nonce/rate/budget decisions using a singleton row lock,
commits ₹1 per attempt before provider I/O, and stops at ₹360, below the ₹400 maximum.
Failures/timeouts consume their reservations. Free-only provider/account restrictions
remain mandatory; reservations are conservative estimates, not provider invoices.

Bind incident IDs to project UUIDs in `aiops_incident_projects` using independently
verified inventory, `verified_by` and the migrator/DBA identity. No alert label,
frontend project selector or model output may assign ownership. Unknown historical
or new incidents remain denied until bound. Existing `projects.created_by`,
`project_members` and active `auth_users` are used for every intelligence request.
Both SREs and platform engineers require verified membership/ownership for AI evidence.
No broad admin bypass or client-supplied membership assertion is used.

Configure trusted monitoring recording rules to expose exactly one fresh
`cloudforge_project_signal_state{project_id="<uuid>",signal="latency|error_rate|availability"}`
series per signal/project, with value 0 (healthy) or 1 (degraded). Labels must originate
from approved resource-to-project inventory, not arbitrary application/alert labels.
The collector enforces project and signal equality, cardinality one, finite values
and sample age ≤120 seconds; missing/stale/ambiguous observations remain unknown.
No service-wide metrics, logs or deployment text are substituted. All-unknown evidence
blocks inference without making a worker request. Thresholds/SLOs belong in the
reviewed recording rules, not in the model.

The inference IAM role trust must name the exact EKS OIDC provider, STS audience and
`system:serviceaccount:cloudforge:ai-inference` subject. Attach only the exact-ARN
Secrets Manager/RDS policy template. AIOps gets only the related request-auth secret
in addition to its existing operational credentials; it must not have the Gemini
API secret, worker ledger role, worker TLS key or provider egress. The Gemini secret
contains only `api_key`; auth is a ≥32-byte dedicated text key; TLS is a JSON object
with `tls.crt`/`tls.key` for `ai-inference.cloudforge.svc.cluster.local`. Configure the
public issuer CA in `cloudforge-inference-ca`; the public RDS CA uses the existing
`cloudforge-db-ca` ConfigMap. Keys/certs rotate through CSI; schedule worker rollout
for TLS renewal because Uvicorn loads certificates at startup. Allow bounded
coordinated request-key rotation across clients/workers. Never reuse frontend,
deployment or execution signing keys. If using customer-managed KMS keys, add only
exact-key decrypt with `kms:ViaService=secretsmanager.<region>.amazonaws.com` and
matching `kms:EncryptionContext:SecretARN` constraints for those related secrets.

The base worker NetworkPolicy denies all egress except DNS. A reviewed FQDN-capable
CNI policy or authenticated egress proxy must allow only the required regional STS,
Secrets Manager, the pinned RDS DNS endpoint:5432 and
`generativelanguage.googleapis.com:443`. Standard Kubernetes NetworkPolicy cannot
express safe public DNS restrictions. Do not replace this with unrestricted 443.
Allow the AIOps deployment to reach this service:8443 in its existing egress policy;
block its direct Google provider egress. Enforce namespace admission/RBAC so arbitrary
pods cannot claim the AIOps labels or read the auth CSI mount. Infrastructure admins
must retain their existing human approval workflows; the inference worker has none.

`AI_EMBEDDING_MODE=concept-v1` is a small local domain-semantic vocabulary backend
(latency/error/availability/deployment/SLO concepts); it downloads no model and makes
no embedding API calls. It is intentionally less expressive than a trained sentence
encoder. `lexical` is an explicit labelled alternative; unsupported modes fail closed.
All knowledge files must match `knowledge/manifest.json` hashes; review and update
the manifest when documentation changes. Documentation stays local: the provider
sees only bounded fixed-vocabulary signal/state pairs. UI aggregate citations refer
to actual supplied evidence; related semantic chunk IDs are separately labelled
contextual documentation, never model evidence or proof of causality.

Confirm account-specific Gemini 2.5 Flash availability, zero-cost account quotas,
provider billing restrictions, data terms and currency/pricing headroom before setting
`AI_TERMS_APPROVED=true` and `AI_DISCLOSURE_APPROVED=true`. There is no paid/provider/model
fallback. Defaults remain free-only and disclosure-disabled. Test IAM, ACLs, CSI,
TLS, monitoring provenance and network enforcement in the approved production-like
environment before enabling. None of these external controls were exercised here.
