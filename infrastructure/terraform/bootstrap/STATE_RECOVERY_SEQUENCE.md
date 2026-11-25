# State recovery and private runtime bootstrap sequence

Prepared against main `7f35fe412bdce6e8ab4f77049b2df2cb1665052b` on
2026-11-22. This is an execution order for review, **not authorization to create,
import, restore, migrate state, unlock, publish secrets, or apply anything**.
Do not execute old saved plans. Never print state, secret payloads or DSNs.

## Observations and recovery decision

Read-only identity: account `933018172228`, `cloudforge-admin`, region
`eu-west-1`. S3 ListBuckets returned empty; the configured
`cloudforge-ai-933018172228-tfstate` previously returned NoSuchBucket. IAM lists
only `cloudforge-local-workload` among CloudForge roles, no CloudForge managed
policies, and no OIDC providers. EKS/RDS inventories and CloudForge-named Secrets
Manager metadata in this region are empty. These observations are dated evidence,
not a guarantee about other accounts, other regions, or externally held backups.

No CloudForge bootstrap state/backup was found in the checkout, local Projects,
temporary directories, or filename search of the local home directory. Nine
state/backup files under Documents/Templates were inspected without printing
attributes; none had CloudForge resource matches. They are unrelated, not import
or recovery inputs. Do not copy them into this project.

The ignored `bootstrap.tfplan` and `tfplan-bootstrap` files have mode 0664. Both
embedded previous states are empty, serial 0, without lineage. Their current
embedded states contain only caller/partition data sources, no managed resources.
Neither proves a prior successful bootstrap or supplies managed state to recover.
Protect/quarantine these sensitive, obsolete plans under the owner's retention
policy; do not reuse them. No Terraform state contents or state-file permissions were changed
as part of this investigation.

No existing resource matching a bootstrap managed address has been identified
for import. `cloudforge-local-workload` is an existing dependency created outside
this module; it is not the runtime/provisioner role and must not be imported into
either address. Before choosing a fresh bootstrap, the owner must confirm the
account/region, approved backup locations and absence of another authoritative
state. An unavailable backup is an unresolved gate, not permission to invent state.

If a real backup is found, verify its provenance, checksum, lineage, serial,
resource IDs and ownership against read-only inventory. Keep it protected and
prepare a separate recovery review. If matching resources exist without state,
prepare an exact address-to-ID import proposal; do not execute it here. Never
infer a state ID or recover from an unrelated project. Review a fresh plan after
any separately approved recovery; old approvals/plans remain invalid.

## Ordered bootstrap gates

1. **Protect local state first.** Select an owner-only working directory and an
   approved encrypted/offsite recovery destination. Use restrictive creation
   permissions (`umask 077`), encrypted storage, access audit and tested recovery.
   Bootstrap currently uses a local backend: keep its eventual state and backups
   separate from the application backend. Do not initialize an empty replacement
   over an unresolved state. No encryption/backup destination is supplied here.

2. **Bind the real access-log destination.** The module requires an existing,
   distinct S3 log bucket in the same account/region. There are currently no owned
   buckets, so this prerequisite is absent. Its creation needs separate approval;
   the bootstrap does not create it. Verify encryption, public-access blocking,
   retention and log-delivery policy restricted to the state bucket ARN and source
   account before accepting the name. Do not invent a bucket name or log policy.

3. **Prepare the first bootstrap inputs privately.** After the recovery decision,
   use account `933018172228`, region `eu-west-1`, and requested state bucket
   `cloudforge-ai-933018172228-tfstate` (availability/ownership must be rechecked).
   Bind the reviewed existing log bucket and, only if its live trust is approved,
   `runtime_principal_arn=arn:aws:iam::933018172228:role/cloudforge-local-workload`.
   Leave `runtime_oidc_provider_arn` empty; exactly one trust source is required.
   Leave application bucket/secret/KMS allowlists empty and drift disabled.
   This trust dependency is not itself evidence of an approved workload identity.

4. **Review a new bootstrap plan under separate authorization.** Require provider
   account guard, AES256 state encryption, versioning Enabled, all public-access
   blocks, TLS-only policy, reviewed access logging, no force-destroy and the
   intentional 30-day noncurrent-version expiry. Decide whether that retention
   meets the approved recovery objective; versioning alone is not an offsite or
   immutable backup. Review every IAM action and replacement. Keep the resulting
   bootstrap state local/protected with a recovery copy. Execution is not part of
   this batch; do not silently migrate bootstrap state into a bucket it manages.

5. **Verify deployed controls before any remote-backend initialization.** Future
   authorized provisioning must be followed by read-only checks of bucket owner,
   region, versioning, encryption, public blocks, policy, logging and role policies.
   Do not retrieve state contents into evidence. Verify permissions for two
   distinct scopes:
   - Deployment operator: reviewed Get/Put on
     `environments/dev/terraform.tfstate`; Get/Put/Delete only on its `.tflock`;
     scoped bucket listing/location. The runtime policy does not grant this key.
   - Infrastructure service: Get/Put on
     `cloudforge/resources/*/terraform.tfstate`; Get/Put/Delete on matching
     `.tflock` objects; no state DeleteObject. Provisioner assumption is a separate
     reviewed role chain, not direct admin credentials.
   Native locking uses `use_lockfile=true`; do not add DynamoDB or disable locking.
   Lock acquisition, contention, release and interrupted-operation reconciliation
   require separately approved operations because they write lockfiles. Never
   force-unlock without proving the owner stopped. Backend init/state migration
   and any state restoration require their own reviewed state decision.

6. **Create the private target only after preview authorization.** Resolve the
   real operator IAM role/SG and private routing/DNS, Free-plan/quotas/cost gates,
   pinned images/controllers, capacity, storage, network policy and teardown.
   Preserve API Gateway HTTPS → VPC Link → internal ALB → private EKS.
   After an approved EKS exists, read its actual issuer and verify/register its
   IAM OIDC provider under separate authorization; never fabricate the issuer.
   Switching runtime trust from the local role to IRSA is a separately reviewed
   change because the module permits exactly one trust source.

## Secrets Manager and private delivery

The restricted Free-plan profile stays **preseeded**, with ESO, AI, drift,
application AWS roles and tenant Terraform execution disabled. Do not attach a
provisioner/runtime role to preview applications merely because this bootstrap
can define one. Bootstrap existence does not authorize tenant provisioning.
Privately provision only the exact reviewed Kubernetes Secret names/keys, RDS CA
and monitoring TLS/identity inputs after deployment approval; never store values
in renderer JSON, Git, state evidence, shell history or command arguments.

Production ESO delivery is a separate profile and approval boundary:

1. Approve real per-service database/signing/session secret names, properties,
   account/region, independent credentials, KMS keys and rotation ownership.
   Create/version them only through separately approved secret tooling; this
   Terraform module creates neither Secrets Manager secrets nor their values.
2. Install a separately reviewed, pinned ESO controller and `external-secrets.io/v1`
   CRDs. Bind exact secret ARNs to `secret_sync_secret_arns` and only required
   customer keys to `secret_sync_kms_key_arns`. Review a fresh IAM plan. Trust must
   use the actual EKS issuer, audience `sts.amazonaws.com`, and subject
   `system:serviceaccount:cloudforge:cloudforge-secret-sync`.
3. Bind the resulting role to the namespace-local SecretStore JWT service account,
   with exact GetSecretValue/DescribeSecret resources and constrained KMS decrypt.
   Applications consume their existing service-specific Kubernetes Secret
   references; they must not receive the sync role or a blanket secret-read role.
   Dedicated infrastructure, FinOps, optional AI and drift roles are separate;
   only the roles actually authorized for that profile may be installed.
4. Verify private DNS, CA trust and egress to STS, Secrets Manager and any required
   KMS endpoint. The existing restricted runtime endpoint set is not proof of
   Secrets Manager reachability. Review exact interface endpoints or an approved
   NAT path, security groups, NetworkPolicies and costs; never open unrestricted
   egress to make synchronization work. Verify EKS Secret encryption and narrowly
   scoped controller/token/SecretStore/workload-edit permissions.
5. Validate synchronization by readiness/conditions and privately checked required
   keys, not Secret data dumps. Test cross-service access denial, missing-secret
   fail-closed behavior, rotation propagation and revocation. Environment-injected
   values need a reviewed restart/reload procedure. Keep direct Python secret
   loading opt-in disabled for ESO-delivered applications; if explicitly chosen
   instead, grant only that service's exact secret/key permissions.
6. Drain applications for ordered migrations: project 001–006, infrastructure
   001–013 with Terraform read-only, deployment 001–006, then AIOps one-shot schema,
   then explicit runtime grants. Check all 25 Go migration receipts. Keep
   `cf_migrator` credentials out of runtime pods, verify real RDS hostname/CA with
   verify-full, and retain separate FinOps project-read and audit-write DSNs.

The next safe action is owner review of the state/backup decision and real log
bucket/operator/secret bindings. Do not apply, import, force-unlock, restore state
or create AWS resources from this document without separate explicit approval.
