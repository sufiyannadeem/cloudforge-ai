# Solo-maintainer GitHub release setup

Prepared locally at the owner's request; **GitHub settings are not applied**.
This replaces the independent GitHub reviewer assumptions in Batches 30–31.
It does not change platform RBAC, project isolation, Terraform saved-plan approval,
rollout promotion or AIOps remediation authorization. Production acceptance remains
blocked; no push, PR action, publication or deployment is authorized by this file.

## Concrete configuration

- `main-ruleset.json`: PR required, **zero** approving reviews, no code-owner or
  last-push approval requirement, conversation resolution retained. Both exact
  `All CI Checks Passed` and `Security Gate` contexts use the observed Actions
  integration 15368, with strict updates. No bypass actors, force-push or deletion.
  Existing stale-review dismissal does not require anyone to submit a review.
- `release-environment.example.json` is now a complete solo-mode payload: no
  reviewers, no self-review restriction and protected-branches-only access.
  The workflow requires main separately. There is no environment approval wait
  or claim of independent review; publication is an explicit manual opt-in.
- In Settings → Environments → release, disable **Allow administrators to bypass
  configured protection rules** if supported/exposed. If GitHub hides this control
  with no reviewer/timer protection, record that limitation; do not invent a REST
  field or claim an approval gate exists. The runtime API check verifies branch
  restrictions, not the UI bypass setting. Owners can still edit repository
  settings later; this configuration is not protection against a compromised owner.

The release helper accepts a branch-restricted environment with no required
reviewers (including an explicitly empty reviewer rule), and rejects missing/wrong
environment, open/custom-pattern branch policy or actual/malformed reviewer
requirements. It never falls back to bypassing a gate.

## Workflow and local evidence

All external Actions in CI, Security, SonarQube and release workflows are pinned
to full commit SHAs. Workflow defaults are contents-read; only the main-only
publish job receives actions-read, packages-write and OIDC token-write. Existing
job-token/bot approval settings are not expanded. Repository-wide SHA enforcement
is not enabled by local pinning.

`workflow_dispatch` publication defaults to false. Seven image builds/scans must
succeed before publish; no continue-on-error bypass is added. Vulnerability/secret/
misconfiguration scans fail on HIGH/CRITICAL including unfixed findings; SBOM-only
steps are inventories, not substitute vulnerability gates. Signature/provenance
checks remain digest-bound to source, workflow, run/attempt, archive and SBOM; no
trust checks, permissions or signing identities are relaxed for solo use.

Executing the real Security Gate shell exposed a pre-existing nested-quoting
SyntaxError even with all dependencies successful. A quoted Python heredoc fixes
that wrapper without changing gate decisions. Regression tests execute both real
gate steps: PR failures, cancellations, missing and skipped dependencies reject
even with commit skip markers; only all-success passes.

Focused release/CI/security tests cover the solo policy, both check names, gate
dependencies, permissions, action pins, scan failure behavior, default-disabled
publication and existing signing rejection paths. Hosted workflow runs, actual
keyless certificates/transparency and registry behavior are still unverified for
these local commits; prior offline crypto evidence is not a hosted release test.

Local result: **54 passed**, three unrelated Terraform/history wrappers deselected.
Both gate shell steps ran with synthetic dependency results; no hosted workflow
was dispatched. No full build or image publication was performed.
Python/JSON/YAML syntax, staged Gitleaks and `git diff --check` passed.

## Approval boundary and next exact actions

Read-only GitHub inspection on November 20, 2026: ruleset **24049172** already has
zero reviews/no last-push requirement/no bypass actors, but requires only Security
Gate. There are **no environments**. Actions is enabled, default token permissions
are read, bot PR approval is disabled, and global SHA enforcement is false.

**Stop for explicit approval before any of the following writes.** Proposed first
phase changes only settings: add the missing exact CI check while preserving the
solo rules above; create release with the prepared payload; disable administrator
bypass in the UI where available, and read back evidence. No push, PR action,
workflow dispatch, registry publication or deployment is included in that approval.

Prepared commands, **not executed** (run from the repository root):

```sh
gh api repos/sufiyannadeem/cloudforge-ai/rulesets/24049172
# Stop and review if live rules differ from the inspected baseline.
gh api --method PUT repos/sufiyannadeem/cloudforge-ai/rulesets/24049172 --input deploy/github/main-ruleset.json
gh api --method PUT repos/sufiyannadeem/cloudforge-ai/environments/release --input deploy/github/release-environment.example.json
```

After the approved changes, verify with read-only commands:

```sh
gh api repos/sufiyannadeem/cloudforge-ai/rulesets/24049172
gh api repos/sufiyannadeem/cloudforge-ai/rules/branches/main
gh api repos/sufiyannadeem/cloudforge-ai/environments/release
```

Expected: active PR rule, zero reviews, last-push/code-owner approval false, both
strict exact check contexts/app IDs, empty bypass actors, deletion/force-push blocks,
release protected-branches-only and no required-reviewer rule. Retain actual UI
evidence or the unsupported-control limitation for administrator bypass.

Next obtain separate approval for a normal push of `feat/aws-terraform-foundation`,
then creating the integration PR. Require fresh exact-head CI/Security success
before a separately approved owner merge; no independent approval is required.
After the workflow exists on main, separately authorize `publish=false` hosted
build/scan validation. Registry publication (`publish=true`), hosted signing and
consumer verification require another explicit approval; no deployment is implied.
