# GitHub-hosted verification: resolved inputs and operator sequence

Current verdict: **inputs resolved; human approval and CI execution pending**.
No workflow was dispatched, database/cluster started, AWS called, image built, model
weights downloaded or inference performed locally. Only bounded public metadata,
checksums/schema sources and a verified 2.3MB actionlint validator were retrieved.

## Verified acquisition inputs

`ci/integration-acquisition.json` now contains actual verified values; do **not** copy
the old unbound template over it. Full hashes/URLs and source evidence are recorded in
[the lock](../ci/integration-acquisition.json) and [evidence](../ci/acquisition-evidence.json).
Its status remains `VERIFIED_INPUTS_PENDING_HUMAN_APPROVAL`, `reviewed_by: null`.
A metadata result is not a human review, signed release or integration success.

| Input | Verified pin | Authoritative public metadata |
| --- | --- | --- |
| Prometheus/promtool | 3.5.0; `e811827a…b46f39a` | [publisher checksums](https://github.com/prometheus/prometheus/releases/download/v3.5.0/sha256sums.txt), matching GitHub release asset digest |
| kubeconform | 0.6.7; `95f14e87…619d73` | [publisher checksums](https://github.com/yannh/kubeconform/releases/download/v0.6.7/CHECKSUMS) |
| Helm | 3.20.0; `dbb4c8fc…19b286` | [official checksum](https://get.helm.sh/helm-v3.20.0-linux-amd64.tar.gz.sha256sum) |
| kubectl | 1.35.0; `a2e984a1…60989` | [official checksum](https://dl.k8s.io/release/v1.35.0/bin/linux/amd64/kubectl.sha256) |
| Terraform | 1.17.2; `e6f16b2f…96605b` | [HashiCorp checksums](https://releases.hashicorp.com/terraform/1.17.2/terraform_1.17.2_SHA256SUMS) |
| Go | 1.26.11; `9849f4e0…c710ec` | [official download metadata](https://go.dev/dl/?mode=json&include=all), 66,999,944-byte linux-amd64 archive |
| actionlint | 1.7.12; `8aca8db9…49a3d8` | [publisher checksums](https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_checksums.txt), matching GitHub asset digest |
| AWS Terraform provider | 6.66.0; `156fe716…8cd523` linux-amd64 ZIP | [publisher checksums](https://releases.hashicorp.com/terraform-provider-aws/6.66.0/terraform-provider-aws_6.66.0_SHA256SUMS), present in both existing provider locks |
| PostgreSQL | `postgres:16-bookworm@sha256:d755a91aff87574a57060f86ecc0d55f83ccb51ceec6ec6f904c1210d018d998` | Official Docker Registry linux/amd64 child manifest; digest recomputed from manifest bytes, no layers fetched |
| glibc Python base | `python:3.12-slim-bookworm@sha256:1475c4f5b6bcb7d35e57661d6f5d7429ec4041275633c15f2b49350ac898276d` | Official Docker Registry linux/amd64 child manifest, no layers fetched |

Publisher checksums were retrieved separately from binaries; publisher signatures were
not independently verified. Except actionlint, complete binary/archive bodies were not
fetched locally. CI still checks every artifact body before extraction/execution, exact
binary versions and strict archive budgets/path/link rules. Format/layout mechanics
were tested for Go-root TAR, Terraform ZIP, raw kubectl and hostile links/traversal.

All 34 existing operational/test Python lock records have a published compatible
CPython 3.12/Linux wheel with an allowed hash according to official PyPI metadata.
Eight preparation-tool wheel hashes were also checked. No wheels were downloaded or
installed locally; actual resolution/install remains a hosted CI gate.

### Deterministic strict schemas — no unpublished bundle prerequisite

The existing acquisition script builds schemas from pinned official sources:

- Kubernetes 1.35.0 OpenAPI at commit `66452049f3d692768c39c797b21b793dce80314e`;
- Argo Rollouts 1.10.2 CRDs at `be8a6221c6c9751cd14497f31a2cb3c33690375a`;
- Secrets Store CSI 1.6.2 CRDs at `10cd116be04e012b283c0811618b182b20741e89`;
- the existing hash-bound vendored LBC CRDs (controller 2.14.1).

The pinned [Rollouts CI matrix](https://github.com/argoproj/argo-rollouts/blob/be8a6221c6c9751cd14497f31a2cb3c33690375a/.github/workflows/testing.yaml)
and [CSI CI matrix](https://github.com/kubernetes-sigs/secrets-store-csi-driver/blob/10cd116be04e012b283c0811618b182b20741e89/.github/workflows/e2e.yaml)
include Kubernetes 1.35.1. These are compatible offline schema candidates for the
1.35 target; no local controller/EKS compatibility result is asserted.

Generation closes internal reference dependencies, preserves explicitly open Kubernetes
maps, applies strict unknown-property checks to defined objects, and binds GVKs.
The metadata-only local derivation produced **314 schemas**, about 9.8MB, with bundle
manifest SHA256 `a9a9ba9365ff72a5f1710e8c2d20b3da28a99501c94ac7c884e5c9f9bf35bea8`.
All 314 schemas passed offline Draft-7 legality checks; CI must reproduce this
manifest and still run native kubeconform. No schema placeholders or permissive replacements
are supplied. CEL/admission/controller semantics still require separate release evidence.

A corrected source defect: kubeconform 0.6.7 uses **absolute filesystem paths**, not
`file://` URIs. Names use `{{.ResourceKind}}-{{.Group}}-{{.ResourceAPIVersion}}.json` to
avoid GVK collisions. The native gate has no default/remote/missing-schema fallback.

## Exact GitHub settings and pending approvals

1. Review the final source revision including both workflows, acquisition lock,
   preparation lock and synthetic corpus. Workflow definitions must be on the default
   branch for workflow_dispatch; select the reviewed dispatch ref afterward. Do not
   dispatch untrusted forks/refs on dedicated runners.
2. Create protected environments **release-verification**, **semantic-preparation**,
   **semantic-verification**. Require human reviewers, restrict branches/tags and disallow bypass according
   to the release policy. Apply the synthetic-CI-only solo-developer exception below
   when independent CI reviewers are unavailable; otherwise prevent self-review.
   Reviewers must be authorized to review these artifacts; product PE approvals remain separate.
3. Confirm the account/repository plan actually supports required reviewers. GitHub
   documents that on Free/Pro/Team these protection rules are public-repository-only;
   private/internal repository capability differs by plan. Do not substitute a manual
   flag for unavailable required-review protection. [GitHub review requirements](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/review-deployments).
4. In all three environments, only **after human review**, set:

   ```text
   CI_ACQUISITION_LOCK_SHA256=229740c6df87058f6c06162b908b8f48a9b408a5979ab6b5079492e0669e2d45
   CI_ACQUISITION_APPROVED=true
   ```

   Independently recompute that SHA from the checked-in lock. The human audit record
   is the protected environment/reviewer decision, not a fabricated `reviewed_by`
   field. Missing approval or mismatched hash stops acquisition.
5. In **semantic-preparation**, additionally set `SEMANTIC_PREPARATION_APPROVED=true`
   and `SEMANTIC_ARTIFACT_REVIEWER` to the actual human review statement/name. No bot,
   `github.actor` inference or default reviewer is used. This is required only when
   the operator genuinely authorizes the public pinned model/license, wheel preparation
   and the committed **synthetic** corpus. No actual review statement is set by this batch.
6. In **semantic-verification**, after inspecting the produced candidate, set
   `SEMANTIC_CANDIDATE_SHA256` to the independently recomputed hash of
   `semantic-candidate.tar.gz`. Do not auto-populate this from a previous job output;
   preparation is not approval. This value is deliberately unknown until preparation.
7. Require the exact same-commit statuses **integration-verification** and
   **semantic-gate** in branch/ruleset and release approval policy. Preparation emits
   **candidate-preparation-only**, which cannot satisfy semantic-gate. Select the actual
   check contexts after the first controlled runs. Neither source presence nor a
   green check from another SHA authorizes a release.
8. Allow only the commit-pinned checkout/upload/download actions used in source.
   Global permissions remain contents:read; semantic jobs alone add actions:read for
   exact-run evidence/artifact reads. No OIDC/package/repository write, AWS role or
   production secret is supplied. Candidate storage uses ordinary Actions artifacts,
   not image/package/release publication. No workflow is automatically dispatched.

## Solo-developer self-approval exception — synthetic CI only

A solo developer may explicitly review and approve their own runs in
**release-verification**, **semantic-preparation** and **semantic-verification**
only for the hosted synthetic-CI sequence above. For this narrow exception, those
three CI environments may allow self-review; required human review, restricted refs,
no bypass, explicit acquisition approval and hash binding remain required. This is
not approval by this document, a bot, a successful preparation job or an automatic flag.
Keep the acquisition lock pending until the actual human decision.

Record the approving human, date, exact source SHA, acquisition lock SHA256, run IDs
and attempts, synthetic-only scope and reason (solo developer) in the review audit.
For semantic verification, inspect the candidate separately and independently recompute
its inner archive SHA256 before setting the approval variable. The same person may
perform that second review; preparation output must never approve itself. No private
corpus, application/production credentials, AWS access, deployment or publication is
covered. Dedicated/private runs are outside this exception.

**Production release approval remains independent.** Keep prevention of self-review
and an authorized independent reviewer on production release/deployment environments
and retain fresh independent PE approval for production actions. Synthetic CI success
and solo-developer CI approval cannot satisfy or waive those gates. If no independent
production approver is available, production release remains blocked.

## Exact execution order (operator actions, not executed here)

Choose a final source SHA **S**. Changing code/locks/corpus afterward requires restarting
this sequence; candidate approval uses environment variables so it does not change S.

1. Manually run **Consolidated Release Verification**, `runner_profile=hosted`, at S.
   Approve its protected jobs after reviewing the locked inputs. Preflight validates
   the official PostgreSQL image before the service job starts. Native and PostgreSQL
   run concurrently; native runs Prometheus/Helm/Kustomize/strict schemas, filesystem-
   mirror Terraform validation and seven real TLS/Terraform cases. Database tests
   require all eight Python cases plus native Go atomic dispatch, with no test skips.
2. Record the successful integration run ID and exact attempt. No local PostgreSQL
   provisioning is needed: CI creates three new empty databases and unprivileged
   NOLOGIN roles on its ephemeral PostgreSQL 16 service, with synthetic data only.
3. Manually run **Approved Semantic Verification** at S with `operation=prepare`,
   `runner_profile=hosted`, the integration run ID and attempt. Obtain the separate
   semantic-preparation approval. Read-only GitHub API checks require the successful
   exact workflow/job, repository, S and attempt **before** model/wheel acquisition.
4. Preparation acquires MiniLM revision
   `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; ONNX publisher LFS SHA256 is
   `6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452`, 90,405,214 bytes.
   Tokenizer and Apache license bytes are independently pinned. It uses a PyPI-hash-
   locked pip-tools bootstrap, resolves binary wheels with hashes, then invokes the
   **existing** artifact/index preparation scripts on `ci/semantic-corpus` only.
   Embedding generation has sockets disabled after acquisition and uses one CPU.
   There is no Hub “latest”, model export, live incident, private knowledge or provider.
5. Download/inspect the retained candidate through Actions, independently hash the
   inner `semantic-candidate.tar.gz`, and approve it in semantic-verification. The
   action's outer artifact ZIP digest is **not** the inner candidate hash. Review
   provenance, actual generated wheel lock, license statement, synthetic corpus and
   model/index hashes. Candidate artifacts expire after **3 days**.
6. Run **Approved Semantic Verification** again at S with `operation=verify`, profile
   hosted, the same integration run/attempt and successful preparation run/attempt.
   The workflow checks both runs via the read-only API, downloads only the named
   same-repository artifact, verifies the independent candidate hash before extraction,
   and rechecks original model/corpus source pins and provenance. No automatic latest
   candidate selection is allowed.
7. Offline wheel resolution/install, real pretrained retrieval quality/negative
   fixtures, RSS and p95 must pass. Current proposed policy ceilings are 1024MiB RSS
   and 8000ms p95 (existing 1GiB/8s bounds), **not measured performance results**.
   The benchmark uses one CPU, a 2GiB virtual-memory limit and 180s outer timeout.
8. Bind both successful status/run records at S into the existing independent release
   review. Image build/OS-library compatibility/scan/SBOM/signatures, actual EKS/RDS
   IAM/TLS/egress, authoritative inventory, historical budget import and free-only
   Gemini availability/terms/disclosure remain mandatory production gates.

## Dedicated support and privacy

`runner_profile=dedicated` retains preloaded native schemas/provider mirrors, isolated
local test DSNs and existing approved private artifact mounts. It does not acquire
or bootstrap hosted resources. Require clean Linux/x64 dedicated runners with their existing custom labels.
Use only the isolated DSN secrets documented in source,
never generic DATABASE_URL or application/cloud credentials. Native schema locations
must now be absolute paths. Clean runners must have no ambient AWS/Google/Kubernetes
or application credentials; the guard also requires checked-out HEAD to match S.
Semantic dedicated verification still needs successful same-SHA integration evidence.

Hosted preparation/verification accepts only the committed synthetic corpus; candidate
selection compares its entire inventory/content to those source hashes. No production
runbooks, operational evidence, customer records, credentials or rejection history may
be uploaded. Dedicated private mounts are the path for private knowledge. Gemini's
approved aggregate-only disclosure, read-only AI, project isolation, rejected-effect
suppression, fresh independent PE approval and ₹360/₹400 accounting are unchanged.

## Quota, costs and remaining blockers

Planning estimates, not measurements: **9–22 Linux runner-minutes** for integration,
**10–25** for preparation and **5–15** for verification. Reserve about **120 minutes**
for configured timeout ceilings per complete cycle, excluding retries. Native/PostgreSQL
are parallel. Verify available repository concurrency, Docker Hub pull headroom, binary
wheel availability and outbound public acquisition access. No account quota was inspected.

Allow at least **500MiB free Actions artifact headroom** for one candidate capped at
400MiB; multiple candidates need more. Clean old candidates or allow expiry before
repeating when storage is limited. GitHub plan quotas and billing are account-specific;
verify Billing/Actions settings and spending controls before approval. [GitHub billing](https://docs.github.com/en/actions/concepts/billing-and-usage),
[limits](https://docs.github.com/en/actions/reference/limits). Runner/storage charges are
separate from the application inference budget; the ₹400 AI maximum is unchanged.

Locally verified this batch: official metadata/checksums, deterministic schema derivation,
actionlint 1.7.12 syntax, Bash/Python/job-reference inspection and **9 lightweight gate-
mechanics tests passed**. Native PostgreSQL/Prometheus/kubeconform/Terraform/TLS/model
integration jobs were **not executed**. Human approvals, protected settings, candidate
creation/review and same-SHA successful runs are the remaining operator dependencies.
