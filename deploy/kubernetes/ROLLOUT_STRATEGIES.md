# Deployment strategies

Rolling remains the default. Existing clients need not send `strategy`. New
requests can send `{ "type": "rolling", "max_surge": 1, "max_unavailable": 0 }`,
`{ "type": "blue-green" }`, or `{ "type": "canary" }`. Limits are integer pod
counts, 0–2, and rolling requires at least one nonzero limit. Each revision records
its strategy and verified requester. Progressive configuration is immutable; create
a new revision instead of editing an approved target.

All strategies use the existing readiness/liveness probes and ten seconds of
minimum readiness. Optional `strategy.readiness_gates` contains up to four unique
qualified Pod condition names. A separately installed condition controller must set
those gates; missing conditions block readiness. Selecting a gate does not install
its controller. Rollback uses the existing API to create and queue a fresh revision
with an earlier successful immutable image in the same project/environment/namespace,
retaining the current strategy and its checks. Simulated/unknown history is not a
Kubernetes rollback source.

## Argo prerequisites and opt-in

Install a reviewed, pinned Argo Rollouts controller and v1alpha1 CRDs independently.
Do not deploy an unreviewed `latest` controller. Review its own controller RBAC,
admission, network access, availability and AnalysisRun retention separately from
the application service account. This repository does not install it automatically.
The executor uses Kubernetes APIs, not a locally installed Argo CLI plugin.

Keep `ARGO_ROLLOUTS_ENABLED=false` until acceptance. Then set it to `true` and set
`ARGO_ANALYSIS_TEMPLATE` to the approved namespace-local Prometheus template name.
Compose exposes both settings; the offline Kubernetes renderer accepts
`rollouts.enabled` and `rollouts.analysis_template`. Canary requests fail closed if
the template is absent/unverified. Simulation cannot enable progressive requests, and a queued progressive request fails explicitly if the worker mode changes to simulation.
Argo blue-green/canary images must be pinned by SHA256 digest.

Apply deployment migration `006_rollout_strategies.sql` through the existing runner
before serving the new image. Legacy rows receive rolling defaults and no invented
requester. `deployment_promotions` retains the signed actor, nonce, exact resource
UID/version, project/environment/image/configuration binding, approval time and
submitted/uncertain outcome. The deployment database login needs read access only to
`auth_users(username, role, active)` for this verification, not passwords or session
tokens. Approval is immediate, not a reusable grant: signed
request expiry, atomic one-use claims and Kubernetes preconditions all apply.

For each project, supplement the existing Role with
`project-rollout-rbac-example.yml` after substituting the verified UUID/template
name. It grants namespace-local Rollout create/get/patch and status get/patch, and
get-only access to one approved AnalysisTemplate. It grants no template/AnalysisRun
creation, Secrets, exec, deletion or cluster administration. Only administrators may
edit the AnalysisTemplate. Argo itself creates/manages AnalysisRuns. Existing project
membership checks, signed service identities, CSRF and backend role checks remain.

### Initial baseline and migration are explicit prerequisites

Argo skips progressive steps for an initial release, and can initially activate a
blue-green revision without pausing. CloudForge therefore **rejects initial Argo
activation** rather than claiming a preview/analysis approval that never occurred.
Start with a verified successful digest-pinned native release, and independently
review its migration using the
[upstream migration guidance](https://argo-rollouts.readthedocs.io/en/stable/migrating/).
No automatic native-controller deletion or migration is implemented here.

Before choosing a progressive strategy, the native Deployment with that workload
name must be absent and a controller-observed Rollout must own a healthy stable
ReplicaSet. Preserve the project/environment labels and stable pod-template
`cloudforge.ai/revision-id` matching the successful database record. Verify the
stable image, namespace, controller UID and readiness. Use the
`cloudforge-rollouts` server-side field manager during the reviewed handoff;
CloudForge never forces field-ownership conflicts. Unverified baselines or overlapping
native/Argo controllers are rejected. A degraded canary can be retried/rolled back
only if its known stable ReplicaSet is healthy and the prior attempt is terminal.

Argo owns active Service hash selectors; the platform never reapplies that Service.
Blue-green needs its active selector pinned to the stable hash. Basic canary needs
the existing shared Service to select only the workload name, without a stable hash.
Changing those routing modes needs a separately reviewed migration. Keep the Argo
feature enabled while progressive workloads exist; reverting to native delivery is
not an automatic flag change. Only one running execution may own a workload scope.

## Blue-green approval and preview

Argo creates the new revision behind a namespace-local preview Service and pauses
with `autoPromotionEnabled=false`. UI preview reads live, revision-matched controller
and pod state; it does not expose a public URL or invent a healthy preview. Preview
Service access requires approved project networking. The exact new hash must be
selected and all new pods, including additional readiness conditions, must be Ready.

A different, active Platform Engineer must check consent and submit **Approve and
promote preview**. Developer/SRE/service identities, self-approval, changed resource
versions, expired/unbound signatures, unhealthy pods and replay are rejected. The
backend revalidates the approver in PostgreSQL and patches only the Argo pause
status using UID/resourceVersion/revision tests. It never sets `promoteFull`, skips
analysis or enables future auto-promotion. HTTP 202 means submitted, not healthy.
An interrupted/uncertain promotion stays consumed and audited; reconcile before any
new action. Rollback creates another gated revision and requires promotion again.

## Canary analysis and traffic semantics

Canary uses Argo steps 20, 50 and 100, a 60-second pause at each step and inline
Prometheus analysis. These are **replica proportions, not weighted traffic**. Two
replicas plus surge provide coarse distribution through the shared Service; sticky
connections and load balancing can differ substantially. No traffic router,
Ingress weight, mesh or AWS load-balancer configuration is created or claimed.
Existing router/hash-pinned canary configuration is rejected, not silently inherited.

`rollout-analysis-template.example.yml` is deliberately unverified. Replace the
namespace/address and adapt the real workload metric/labels; platform-service HTTP
metrics are not application evidence. Verify namespace and
`rollouts_pod_template_hash` attribution, the status label and scrape freshness before
an administrator sets `cloudforge.ai/evidence-verified=true`. The sample policy
requires at least 30 measured requests in five minutes, fresh samples within 60
seconds, and 99% success across five 30-second measurements. Low/no traffic, missing
labels, empty/NaN results, stale evidence and provider errors do not pass. Review
those thresholds for the actual application's request volume and generate controlled
local traffic before acceptance. Clients cannot supply PromQL or template names. Dry-run analysis and indirect template
composition are rejected; this API supports direct Prometheus metrics only.

Argo handles failed analysis, progress-deadline abort and stable ReplicaSet restoration.
CloudForge only observes status; it never implements its own traffic/rollback loop.
Each worker observation waits at most 30 minutes, verifies observed generation/current stable hash and
ready revision pods, and records success/failure in existing attempt history. A
missing controller, inconclusive pause or timeout requires manual reconciliation,
not optimistic success. Pending blue-green approvals remain safely paused. Worker
leases renew during observation; restart recovery observes without reapplying and
shutdown preserves recoverable ownership state.

## Local validation and acceptance

Focused Go tests use command-runner fixtures; PostgreSQL tests use disposable schemas
in the existing local container. `monitoring/prometheus/rollout-analysis.test.yml`
contains synthetic healthy, failing, stale, low-volume, missing-label, missing-data
and foreign-project cases, exercised with the existing Prometheus image:

```sh
docker run --rm --network none --entrypoint /bin/promtool \
  -v "$PWD/monitoring/prometheus/rollout-analysis.test.yml:/tests/rollout-analysis.test.yml:ro" \
  prom/prometheus:v3.5.0 test rules /tests/rollout-analysis.test.yml
```

Generated blue-green/canary fixtures were parsed and checked offline against the
[official stable Rollout CRD](https://github.com/argoproj/argo-rollouts/blob/stable/manifests/crds/rollout-crd.yaml).
This is not controller acceptance. No local Kubernetes cluster was available; the
configured EKS context was not contacted. Before deployment, use an explicitly
verified local/sandbox context to test controller/CRD absence, baseline handoff,
server-side ownership and UID/version conflicts, actual preview routing, independent
promotion, real analysis failure/abort, stable traffic restoration, readiness gates,
worker restart/shutdown, cross-project denial and new-revision rollback. Controller
retention and namespace admission/isolation are required target-environment checks.
