# PR #59 SonarCloud confirmed findings and corrections

Read-only SonarCloud API retrieval on 2026-11-25 confirmed analysis at
`3f88fc056c1cd8e88be94b6cafb174cc80f68f30`, analysis date
`2026-11-25T07:20:00+0000`. Quality gate: reliability **C (3)** and security **E (5)**;
required rating A (1). The API returned exactly **18 open issues** (one bug,
13 vulnerabilities, four code smells), corroborated by GitHub check 139045457172.
The table uses original analysis locations, not post-fix line numbers.

Sources: [PR analysis](https://sonarcloud.io/dashboard?id=sufiyannadeem_cloudforge-ai&pullRequest=59),
[issue inventory](https://sonarcloud.io/api/issues/search?componentKeys=sufiyannadeem_cloudforge-ai&pullRequest=59&resolved=false&ps=100),
[quality gate](https://sonarcloud.io/api/qualitygates/project_status?projectKey=sufiyannadeem_cloudforge-ai&pullRequest=59).
Each issue can be opened by its exact key through the PR issue inventory.

| Issue ID | Rule ID | Sonar severity | Original file:line | Root cause / correction |
| --- | --- | --- | --- | --- |
| `AaIRjv4yPU6mhNqn42wj` | `yaml:S2068` | MAJOR | `.github/workflows/consolidated-release-verification.yml:113` | Replaced the literal service password with a dedicated environment-secret reference. |
| `AaIRjv4yPU6mhNqn42wk` | `secrets:S6698` | BLOCKER | `.github/workflows/consolidated-release-verification.yml:142` | Removed the literal DSN password; all hosted DSNs use the same dedicated synthetic-only secret. Bootstrap requires a matching random 64-hex value and still rejects non-loopback/non-test targets. |
| `AaIRjv4yPU6mhNqn42wl` | `secrets:S6698` | BLOCKER | `.github/workflows/consolidated-release-verification.yml:154` | Removed the literal DSN password; all hosted DSNs use the same dedicated synthetic-only secret. Bootstrap requires a matching random 64-hex value and still rejects non-loopback/non-test targets. |
| `AaIRjv4yPU6mhNqn42wm` | `secrets:S6698` | BLOCKER | `.github/workflows/consolidated-release-verification.yml:155` | Removed the literal DSN password; all hosted DSNs use the same dedicated synthetic-only secret. Bootstrap requires a matching random 64-hex value and still rejects non-loopback/non-test targets. |
| `AaIRjv4yPU6mhNqn42wn` | `secrets:S6698` | BLOCKER | `.github/workflows/consolidated-release-verification.yml:156` | Removed the literal DSN password; all hosted DSNs use the same dedicated synthetic-only secret. Bootstrap requires a matching random 64-hex value and still rejects non-loopback/non-test targets. |
| `AaIRjv2HPU6mhNqn42wY` | `kubernetes:S6865` | MAJOR | `deploy/kubernetes/inference/aiops-patch.yaml:15` | Disabled token automount explicitly in the strategic patch, matching the base Deployment. |
| `AaIRjv2HPU6mhNqn42wW` | `kubernetes:S6864` | MAJOR | `deploy/kubernetes/inference/aiops-patch.yaml:16` | Made the existing 512Mi memory limit explicit in the patch; no effective budget reduction. |
| `AaIRjv2HPU6mhNqn42wX` | `kubernetes:S6897` | MAJOR | `deploy/kubernetes/inference/aiops-patch.yaml:16` | AIOps patch explicitly retains the base 128Mi storage request; inference worker now requests 16Mi ephemeral storage. |
| `AaIRjv2HPU6mhNqn42wZ` | `kubernetes:S6892` | MAJOR | `deploy/kubernetes/inference/aiops-patch.yaml:16` | Made the existing 200m CPU request explicit in the patch. |
| `AaIRjv2HPU6mhNqn42wa` | `kubernetes:S6873` | MAJOR | `deploy/kubernetes/inference/aiops-patch.yaml:16` | Made the existing 256Mi memory request explicit in the patch. |
| `AaIRjv4EPU6mhNqn42wb` | `kubernetes:S6897` | MAJOR | `deploy/kubernetes/inference/workload.yaml:34` | AIOps patch explicitly retains the base 128Mi storage request; inference worker now requests 16Mi ephemeral storage. |
| `AaIRjv4EPU6mhNqn42wc` | `kubernetes:S6870` | MAJOR | `deploy/kubernetes/inference/workload.yaml:34` | Bounded inference ephemeral storage at 64Mi, retaining the existing 8Mi memory-backed temporary volume and CPU/memory controls. |
| `AaIRjv4SPU6mhNqn42wg` | `pythonsecurity:S8707` | MAJOR | `scripts/ci/acquire-integration-inputs.py:35` | Removed the arbitrary --lock CLI option; loading accepts only the exact checked-in lock path before reading and still enforces the environment-approved hash and human approval. |
| `AaIRjv4SPU6mhNqn42wf` | `pythonsecurity:S5144` | MAJOR | `scripts/ci/acquire-integration-inputs.py:109` | Downloader reconstructs the URL authority from literal approved hosts, validates immediately before network use and also canonicalizes allowlisted redirects. Rejects control characters, backslashes, userinfo, private/literal hosts, alternate ports and unapproved origins; checksum and byte limits remain. |
| `AaIRjv4SPU6mhNqn42we` | `python:S4143` | MAJOR | `scripts/ci/acquire-integration-inputs.py:191` | Removed the redundant temporary assignment in recursive reference closure; insert the copied definition once before descending. Recursive-schema tests preserve cycle handling and strictness. |
| `AaIRjv4IPU6mhNqn42wd` | `pythonsecurity:S6096` | BLOCKER | `scripts/ci/prepare-semantic-artifacts.py:94` | Archive creation now builds fresh TarInfo entries from validated relative names and no-follow regular-file descriptors; rejects symlinks, linked parents, path escapes and special files. The reported sink is archive creation rather than extraction; no issue was marked false-positive or suppressed. |
| `AaIRjv4WPU6mhNqn42wh` | `pythonsecurity:S8707` | MAJOR | `scripts/verify-consolidated-release.py:110` | Report output accepts only a new JSON basename in the current workspace, opened relative to a directory descriptor with exclusive/no-follow flags; arbitrary paths and overwrites are rejected. |
| `AaIRjv4gPU6mhNqn42wi` | `pythonsecurity:S8707` | MAJOR | `services/aiops-service/app/knowledge_config.py:37` | Knowledge retrieval accepts only the operator-configured corpus mount (or built-in default), rejecting traversal and linked roots before manifest reads. Hosted preparation explicitly passes its already approved corpus mount in the environment. Project scoping and reviewed hashes remain mandatory as before. |

## Regression validation

- 50 focused security/RAG tests passed; one real pretrained-artifact test skipped.
- Nine existing consolidated gate-mechanics tests passed with cached system Python.
- Full AIOps suite with sockets disabled: 295 passed, 10 integration/artifact skips.
- Final Kustomize render checks non-root identity, read-only filesystem, privilege
  controls, explicit resource budgets and disabled automount on both Deployments.
  Cached Trivy config scan on both rendered Deployments: no HIGH/CRITICAL findings,
  with no ignore file. Secret and whitespace scans must also pass before commit.
- No scanner suppression, exclusion, gate change or false-positive marking was made.
  No approval field was fabricated and no acquisition lock bytes were changed.
  Application AI/provider prompts, read-only tools, immutable approval/rejection
  contracts and inference budget controls are unchanged.

## Remaining external prerequisites

The protected `release-verification` environment needs a dedicated
`SYNTHETIC_CI_POSTGRES_PASSWORD` secret containing 32 cryptographically random bytes
encoded as 64 lowercase hexadecimal characters. Never reuse a production credential.
No secret was generated, configured or committed during this work. The workflow
cannot pass its synthetic database bootstrap until this prerequisite is configured.
Existing explicit human approvals remain required; the secret grants no approval.

SonarCloud must automatically analyze the pushed revision before a new quality-gate
verdict can be claimed. These local checks do not execute Sonar's hosted analyzer.
Integration/artifact skips are not runtime or production-release evidence. No manual
workflow dispatch, PR merge, protection change, cloud provisioning, paid inference,
local Kubernetes or heavy dependency download was performed.
