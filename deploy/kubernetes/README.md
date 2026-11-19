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
