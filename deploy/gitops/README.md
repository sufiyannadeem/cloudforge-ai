# Argo CD reconciliation preparation (Batch 28)

Use established Argo CD; no controller is installed or custom controller added.
Supply real credential-free HTTPS repository, reviewed **manifest commit SHA**,
repository-relative rendered-release directory, Argo namespace and verified IdP
operator groups in `inputs.example.json`. Missing values fail closed. Frontend
role/actor headers are not Argo identity or membership proof.

```sh
python3 scripts/prepare-gitops.py --config /path/to/reviewed-gitops-inputs.json --output /tmp/reviewed-argocd.yml
```

This writes AppProject/Application YAML only. The project allows only the exact
source repo and `cloudforge` destination; no cluster resources, raw Secret, RBAC
or tenant Rollout kinds are allowed. Reconciliation is pinned to a Git SHA,
self-heals, does not automatically prune and has bounded retries. HPA-owned
replicas are ignored, not image/approval fields. No deletion finalizer is added.
Operators must still review destructive sync/prune operations independently.

The platform application manages core services, not application deployments in
`cf-PROJECT_UUID` namespaces. Native/Argo tenant controller ownership and human
promotion/approval stay with deployment-service. Terraform remains read-only in
the rendered foundation. GitOps never invokes Terraform apply/destroy or creates
human approvals. Changes enabling execution require the existing approval gates.

Renderer output now includes bounded **Sync hooks** in waves -5 through -1:
project migrations, infrastructure, deployment, AIOps and runtime grants. CA,
service accounts, network rules and external-secret references precede hooks;
core Deployments follow. Migration pods have no API token, no runtime signing
keys or IRSA provisioning role, only the separate migration DSN and CA. They do
not match HTTP Service selectors. Missing secrets/DB TLS fail hook startup; no
runtime migration fallback exists. Failed hooks must be reviewed; additive
migration receipts protect retries. Grant SQL is a non-secret ConfigMap.

Before any sync, a DBA must complete reviewed role/bootstrap ownership handoff
and create credentials: [database runbook](../postgres/README.md). Configure the
real public DB CA ConfigMap and exact secret properties. Install/review Argo CD
and ESO CRDs/controllers, namespace, controller RBAC, private repo credentials,
trusted SSO groups, external-secret health and network reachability separately.
Do not grant developers Argo sync or migration-Secret access. Argo administrators
and the approved Git repository remain trust roots, not isolated by AppProject
alone. Controller privileges and SSO were not validated locally.

Plain `kubectl apply` ignores Argo waves/hooks: do not apply all generated objects
at once and assume ordering. Use approved Argo reconciliation or explicitly run
the ordered migration/grant procedure before runtime workloads. Existing data
must not be reassigned or revoked automatically. No existing cluster was touched.

**PARTIAL:** offline structural/security tests and built-in Kubernetes validation.
**BLOCKED:** reviewed controller version/digest/CRDs, actual Application sync,
repository/SSO access, ESO readiness, maintenance drain and live reconciliation.
Image signing/admission and hosted publication remain separate release gates.
