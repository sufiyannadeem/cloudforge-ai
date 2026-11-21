# Reliability preparation (Batch 24)

The offline renderer adds six CPU HPAs (default 2–4 replicas, 70% target),
PDBs, bounded startup/readiness/liveness checks, rollout stabilization and
hostname/zone spreading. Kubernetes 1.30+, two eligible nodes in two zones,
metrics-server and sufficient capacity are prerequisites. HPA owns replicas;
release manifests omit that field. Wait for the observed two-replica floor
before admitting traffic. Readiness checks database connectivity; liveness does
not. Migration transactions share a database advisory lock; preserve the
project-first schema order in the release checklist.

Infrastructure-service disables HPA scale-down and automatic node eviction;
its PDB allows zero voluntary disruptions. Terraform runs are synchronous:
disable new execution, drain and reconcile before maintenance or manual scale-down.
PDBs cannot prevent direct deletion, node failure or Deployment rolling updates.
Termination budgets reduce interruption risk but do not guarantee Terraform
completion. Durable remote state/locking, HA PostgreSQL and encrypted, backed-up
cross-zone RWX workspaces remain external prerequisites.

Budget database capacity before raising replicas: three Go services each allow
10 connections per pod (120 at four replicas), plus Python, readiness and admin
connections. A local PostgreSQL default of 100 is not sufficient for that ceiling.
Keep application/DB quotas and storage/ephemeral capacity aligned.

Tenant Deployments and Argo Rollouts retain strategy ownership and receive
startup probes, termination budgets and soft topology preferences. No competing
tenant HPA or PDB is introduced. Approval, lease and rollout gates are unchanged.

## Operator evidence

Platform Engineer/SRE dashboards use fixed namespace-bound kube-state-metrics
queries and reject stale/invalid evidence. Missing exporter data displays N/A.
Review `kube-state-metrics-values.example.yml`, pin its image/chart and configure
Prometheus to scrape the actual private exporter endpoint. Preserve monitoring
network selectors. This file does not install an exporter or metrics-server.
Developers cannot query the platform scaling endpoint.

## Node autoscaling: review-only artifacts

Use upstream Cluster Autoscaler, not a custom controller. Copy
`node-autoscaling-inputs.example.json` outside the repository and supply verified
account, region, cluster version, reviewed chart version, matching image digest,
exact ASG ARNs and a dedicated IRSA role/OIDC provider. No resources are invented.
CLI paths must stay in the current private review directory (no symlinks or
outside paths). Inputs are read through bounded no-follow descriptors; the
output must be a new single child directory in that workspace. From the repository root:

```sh
REPO_ROOT="$PWD"
cd "${REVIEW_WORKSPACE:?private directory containing reviewed-inputs.json}"
umask 077
python3 "$REPO_ROOT/scripts/prepare-node-autoscaler.py" --config reviewed-inputs.json --output-dir cloudforge-node-review
helm template cloudforge-node-autoscaler /path/to/reviewed-cluster-autoscaler-chart --namespace kube-system --kubeconfig /dev/null --values cloudforge-node-review/values.yml > cloudforge-node-review/upstream.yml
kubectl --kubeconfig=/dev/null kustomize cloudforge-node-review > cloudforge-node-review/rendered.yml
```

These commands render only. Review the generated IAM/trust and final manifests;
the upstream chart needs the included standard Kustomize readiness/startup patch.
Chart 9.60.0 was rendered locally; no controller was installed. Match the controller
minor to the target Kubernetes minor, verify provenance/digest and review updates.
Two replicas elect one active leader. Regional Describe inventory requires
Resource `*`; scaling writes require exact ASGs and both ownership tags. Upstream
cluster-wide node reads/updates and pod eviction RBAC are intrinsic to this
controller; do not grant those permissions to application service accounts.

Before activation, verify node-group tags, min/max capacity, zone capacity,
IRSA/STS access, safe eviction, node prices/quotas and network paths. Resolve the
existing EKS generator's `desired_size` ownership: an approved Terraform ownership
handoff is required so later Terraform applies do not reset autoscaler changes.
This preparation does not modify existing Terraform lifecycle semantics.

Live HPA scaling, database failover, drain/termination, PDB enforcement,
metrics delivery, node scaling and rollout recovery are **unverified**. Rehearse
these in a separately authorized cluster before production acceptance.

Security scan: rendered application manifests pass HIGH/CRITICAL checks with
only the existing exact-path project deployment RBAC exceptions. The reviewed
upstream node chart still triggers two HIGH KSV-0056 findings for cluster-wide
Endpoints create/patch and named `cluster-autoscaler` Endpoints get/update.
No suppression was added. Review a lease-only RBAC variant against the exact
controller version before activation; this remains an external-controller
release gate, not an application permission grant.
