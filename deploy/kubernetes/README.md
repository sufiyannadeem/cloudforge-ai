# Verify CloudForge on an authorized cluster

Resolve the [AWS bootstrap prerequisites](../../infrastructure/terraform/bootstrap/README.md) before provisioning real AWS resources. Check the AWS account and intended EKS ARN. Select a Kubernetes context explicitly, then confirm its endpoint matches the intended cluster. A workstation's current context is not proof of the application's target.

```sh
aws sts get-caller-identity --query Account --output text
aws eks describe-cluster --name "${EKS_CLUSTER_NAME:?}" --region "${AWS_REGION:?}" --query 'cluster.{ARN:arn,Endpoint:endpoint,Status:status}'
kubectl --context "${KUBE_CONTEXT:?}" config view --minify -o jsonpath='{.clusters[0].cluster.server}'
```

The Kubernetes example uses in-cluster ServiceAccount credentials. Its deployment worker checks API reachability without needing access to services in `kube-system`. External workers using the production Compose configuration still need their approved EKS workload identity and kubeconfig. Image pull credentials belong in the target cluster, managed separately from the CloudForge signing keys.

For each authorized project, an administrator must pre-create the `cf-<project UUID>` namespace and review the namespace-scoped [Role and RoleBinding template](project-deployment-rbac-example.yml). Substitute the exact project UUID and apply the manifest to the intended cluster only after approval. The worker does not need permission to create namespaces or delete workloads. Verify the grant from an administrator authorized to impersonate the ServiceAccount.

```sh
namespace="cf-${PROJECT_UUID:?}"
actor="system:serviceaccount:cloudforge:cloudforge-deployment-service"
kubectl --context "$KUBE_CONTEXT" -n "$namespace" auth can-i create deployments.apps --as="$actor"
kubectl --context "$KUBE_CONTEXT" -n "$namespace" auth can-i patch services --as="$actor"
kubectl --context "$KUBE_CONTEXT" -n "$namespace" auth can-i watch deployments.apps --as="$actor"
kubectl --context "$KUBE_CONTEXT" -n "$namespace" auth can-i list replicasets.apps --as="$actor"
kubectl --context "$KUBE_CONTEXT" -n "$namespace" auth can-i get pods --subresource=log --as="$actor"
kubectl --context "$KUBE_CONTEXT" -n "$namespace" auth can-i delete deployments.apps --as="$actor"
```

The first five checks should allow access and the last should deny it. Check an unrelated namespace with the same identity and confirm access is denied there as well.

After explicit approval, submit two revisions through the Deployment UI in a disposable project. Use trusted digest-pinned images whose containers serve `/health` on port 8080. Run them individually and verify **Kubernetes** execution, Ready replicas, bounded logs, and attempt history. Roll back from the second revision and confirm the new execution uses the earlier successful digest in the same project, environment, and namespace. Rollback creates a new revision, which the UI queues through the normal deployment route. If queuing fails, retry the pending revision. Simulated, legacy-unknown, and mutable-tag releases are ineligible as Kubernetes rollback sources.

Use the UI's **Logs and health** for current state. Restart counts require Prometheus to scrape kube-state-metrics with pod UID, namespace, pod, and container labels. Unavailable metrics should remain unavailable. The AWS runbook covers provider IDs, live resource reads, estimated costs, and cleanup. Projects need verified attribution for actual cost data.

The service retains Kubernetes execution records. After cleanup approval, an administrator should identify the exact Deployment and Service in the project namespace, verify their project and revision metadata, and remove those workload objects using the cluster's cleanup process. Recheck the namespace with read-only queries. Only then proceed with any independently approved AWS teardown.

The deployment diagnostics panel captures one verified pod at a time. Events and Metrics API reads require the additional project Role entries. [Metrics Server](https://kubernetes.io/docs/tasks/debug/debug-cluster/resource-metrics-pipeline/) or a compatible adapter is required for CPU and memory. Diagnostic history stores the signed actor and structured evidence. It stores no log lines or event messages and executes no remediation.

For the Cloud Cost Detective audit history, apply project-service migration `005_finops_anomaly_audit.sql` and configure `FINOPS_AUDIT_DATABASE_URL` with a separate PostgreSQL login granted SELECT and INSERT on `finops_anomaly_captures`. Keep the project cost attribution DSN read-only. Audit capture and history are operator-only, use the current AWS account, and make no billing changes.

## Production integration gate

Apply the project, deployment, and infrastructure migrations before rolling out the API images. Verify the migration receipts with a database operator login.

```sql
SELECT version FROM schema_migrations
WHERE version IN ('005_finops_anomaly_audit.sql',
                  '005_deployment_diagnostics.sql',
                  '011_terraform_drift.sql')
ORDER BY version;
```

For FinOps, grant the audit login `USAGE` on the application schema and only `SELECT, INSERT` on `finops_anomaly_captures`. Set `FINOPS_AUDIT_DATABASE_URL` through the existing secret reference. Restart only FinOps when rotating this credential. Verify a signed operator request can read audit history and a Developer is denied.

Use the [AWS verification and cleanup runbook](../../infrastructure/terraform/bootstrap/README.md#approved-live-verification-and-cleanup) for service costs, provisioned IDs, and teardown. Before requesting apply approval, confirm account, region, bucket controls, provisioner trust, and the runtime identity from the running workload. Validate Cost Explorer under that workload identity. Project cost results require verified attribution and may be delayed by billing ingestion.

After an independently approved sandbox deployment, confirm current Kubernetes health and capture diagnostics, verify the cost audit receipt, and scan an active resource from Infrastructure. Drift findings should distinguish provider changes from desired changes. Compare receipts with the signed actor and resource, then use an unrelated Developer account to confirm isolation. Use fresh, independently approved plans for cleanup. Keep state history and record any retained billable resources.

## Read-only runtime filesystems and deployment RBAC

All six application containers use a read-only root filesystem. The infrastructure service requires an existing `cloudforge-terraform-workspaces` PVC in the `cloudforge` namespace, mounted at `/var/lib/cloudforge/terraform`. With the example's two replicas, provide shared ReadWriteMany storage so either replica can read the exact approved plan after a restart. Size and back up that storage for provider binaries and saved plans. An ephemeral workspace would lose approval-bound artifacts.

Infrastructure and deployment CLI temporary files/caches use the bounded `/tmp` emptyDir with a writable HOME. Terraform update-check writes are disabled. The frontend mounts `/app/.next/cache` and `/tmp` as bounded emptyDirs. Pod fsGroup matches the non-root runtime UID for these mounts. Python images disable bytecode writes; their application directories remain read-only. Validate storage ownership and capacity in the intended cluster before rollout.

The deployer RoleBinding targets only `cf-PROJECT_UUID`. ReplicaSets need list permission for ownership checks; named ReplicaSet get was removed. Pod get/list, pod-log get, warning-event list and pod-metrics get support the verified diagnostics path. Rollout status requires Deployment get/list/watch. `kubectl apply` requires get/create/patch on Deployments and Services.

Two path-and-check-specific exceptions in `trivy-rbac-exceptions.yaml` apply only to the project deployer Role manifest.

- `KSV-0048` allows Deployment creation/patching for the executor's dynamically named workloads.
- `KSV-0056` allows Service creation/patching for the generated project workloads.

Kubernetes RBAC cannot constrain create operations to a dynamic resource-name prefix. These permissions can modify workload/network specifications within the bound namespace and can indirectly expose that namespace's service accounts or secrets. Use dedicated project namespaces with appropriate admission and workload-isolation controls. The Role grants no direct Secret API, pod exec, deletion, namespace management, node access or RBAC administration permissions. The CI action passes this YAML ignore file explicitly. Other manifests and check IDs remain enforced. No global scanner suppression is added.

## Render the deployment foundation (Batch 22)

Do not apply `cloudforge-secrets-example.yml` directly. It intentionally contains
placeholder Secrets/identities/images. `scripts/render-kubernetes.py` reuses its
workloads, removes every example Secret, and emits ClusterIP Services, probes,
ExternalSecrets, the Terraform ConfigMap, RWX PVC, and default-deny NetworkPolicies.
It performs no API calls. Install PyYAML using the existing Python environment.

```sh
cp deploy/kubernetes/deployment-inputs.example.json /tmp/cloudforge-deployment-inputs.json
# Edit this non-secret JSON with reviewed, real references; every null must be resolved.
services/aiops-service/.venv/bin/python scripts/render-kubernetes.py \
  --config /tmp/cloudforge-deployment-inputs.json > /tmp/cloudforge-rendered.yml
```

Only redirect successful output into a release artifact. Missing/invalid inputs
produce no manifest. Do not place secret values in the inputs. Image references
must be published `registry/repository@sha256:<64 hex characters>` digests, not tags.
Record provenance and the previous compatible digests. The renderer checks syntax,
not registry existence or signatures.

Supply account/region-matching infrastructure runtime, provisioner, FinOps, and
secret-sync role ARNs. Infra and FinOps use distinct service accounts. Deployment
uses only its in-cluster API token and existing project-scoped RoleBindings; no AWS
role is granted. AIOps defaults to AI disabled, not mock success. To enable Bedrock,
set `ai.provider=bedrock`, an approved `ai.model`, `ai.guardrail_id`, a published
numeric `ai.guardrail_version`, and `roles.aiops-service` with scoped model and
guardrail permissions. Missing/DRAFT guardrails fail closed before inference;
intervened model output is rejected. The guardrail and its IAM permission must be
approved and verified in AWS separately; the renderer does not create them. Other app API tokens are not automatically mounted; IRSA
uses its own projected identity token. No application receives the sync role.

Install and review External Secrets Operator with `external-secrets.io/v1` CRDs
before using the rendered namespace-local SecretStore/ExternalSecrets. The store
uses JWT federation through `cloudforge-secret-sync`, following the
[official AWS provider configuration](https://external-secrets.io/latest/provider/aws-secrets-manager/).
The operator needs permission to request that service account's token and manage
only intended namespace Secrets. Restrict who can edit SecretStores, ExternalSecrets,
service accounts and workload specs; possession of those permissions can expose
secrets indirectly. Kubernetes Secret encryption at rest, access audit and controller
installation remain cluster prerequisites. No static AWS access keys are emitted.

`secrets` maps exactly the referenced Kubernetes Secret names to full existing
Secrets Manager ARNs and explicit JSON properties. No wildcard search or `dataFrom`
extraction is used. Reuse each independent caller/receiver signing key through its
existing shared reference; never reuse keys between distinct audiences. Configure
FinOps audit and attribution logins separately with existing least-privilege grants.
Use a verified TLS database URL and the required CA trust; the renderer never reads
or validates secret payloads. Target Secrets are retained if remote data disappears;
revocation requires explicit rotation and workload restart. Environment variables do
not hot-reload after a secret refresh. Verify operator Ready conditions and all
required Secret keys before starting applications.

Bootstrap now accepts `secret_sync_secret_arns` and optional
`secret_sync_kms_key_arns` for a dedicated exact-subject OIDC role; pass the existing
EKS OIDC provider. KMS decryption is constrained to regional Secrets Manager and the
approved secret encryption contexts. No secrets or KMS keys are created. Supply
`application_bucket_names` for the exact application buckets approved for S3
lifecycle operations; the default empty set grants no application-bucket permissions.
The state bucket remains explicitly denied to the provisioner. Scope the separate
FinOps role to its required read-only APIs; bootstrap does not provision that role.

The selected storage class must actually support **ReadWriteMany**, encryption,
backup and cross-node mounts with the configured fsGroup. The renderer neither
invents a class nor creates an EFS filesystem/CSI driver. Test failover with two
infra replicas and persisted saved-plan artifacts before enabling Terraform writes.
Protect that PVC: approved plans and provider data can contain sensitive values.

The CNI must enforce NetworkPolicy. Supply reviewed CIDRs for PostgreSQL (5432),
the Kubernetes API (443), and required AWS/provider-registry HTTPS endpoints (443).
No default-route CIDR is accepted. Allow only the selected ingress-controller
namespace/app to reach frontend; complete TLS termination there. DNS allows the
standard kube-system kube-dns selector; adapt/review for NodeLocal DNS or other
cluster DNS. Monitoring uses supplied namespace and app selectors `prometheus`,
`grafana`, `alertmanager`; those services and their own ingress/egress policies must
exist. AWS endpoint CIDRs, NAT/DNAT behavior, proxy requirements and registry/provider
download destinations must be verified with the target CNI. Policies restrict
network reachability, not IAM/API authorization or TLS identity.

Review the rendered artifact and validate against the actual cluster schemas before
separately approving deployment. Apply foundation objects first, wait for secrets
and storage, then start **one project-service replica** to finish migrations. Start
infrastructure/deployment, then AIOps/FinOps, then frontend; scale project-service
only after its migration receipt verification. Do not apply all Deployments at once
on an empty database. Probes establish application listener readiness after startup;
they do not prove AWS permissions or continuously validate downstream services.
Frontend probes use TCP so no session/CSRF bypass endpoint is introduced.
Terraform remains `TERRAFORM_READ_ONLY=true`; changing that requires separate approval
of backend, role chain, locking and live acceptance prerequisites. No project RBAC
or Terraform approval requirement is removed by this renderer.
