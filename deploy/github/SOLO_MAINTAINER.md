# Solo-maintainer GitHub release setup

**Status (Batch 33 read-back):** approved GitHub settings are applied: ruleset
24049172 requires both aggregate checks, and `release` restricts protected branches
with no reviewers and `can_admins_bypass: false`. This is recorded evidence, not a
claim that future settings cannot drift.
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
- The environment PUT payload explicitly sets `can_admins_bypass: false`.
  The publish preflight requires the GET response to contain literal JSON false;
  true, missing, null, numbers, strings and containers fail closed before registry
  login. This is a top-level environment field, not a reviewer/protection-rule
  entry. If unavailable, publication remains blocked; there is no fallback.
  Owners can still edit settings; this does not protect against a compromised owner.

The release helper accepts a branch-restricted environment with no required
reviewers (including an explicitly empty reviewer rule), and rejects missing/wrong
environment, open/custom-pattern branch policy or actual/malformed reviewer
requirements or administrator bypass not explicitly disabled. It never falls back
to bypassing a gate.

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
publication and existing signing rejection paths. Batch 32 hosted CI and the
six-image Security Gate passed at `0c3d7abd`.
The manual seven-image release workflow (including PostgreSQL), actual keyless
certificates/transparency and registry publication remain unverified; CI success
is not a hosted release test.

Historical solo-setup local result: **54 passed**, three unrelated Terraform/history wrappers deselected.
Both gate shell steps ran with synthetic dependency results; no hosted workflow
was dispatched. No full build or image publication was performed.
Python/JSON/YAML syntax, staged Gitleaks and `git diff --check` passed.

## Approval boundary and next exact actions

The Batch 33 read-back confirmed active ruleset **24049172**: PR required,
zero reviews, both exact aggregate checks with strict updates, no bypass actors,
and deletion/force-push blocked. The `release` environment has protected-branch
restrictions, no reviewer requirement and administrator bypass disabled.
No independent human GitHub approval is claimed. Platform approvals are unchanged.

The committed environment payload now reproduces the observed bypass restriction.
Any future settings mutation requires separate explicit approval; do not reapply
payloads without backing up and comparing live settings. No settings mutation,
push, PR action, workflow dispatch or publication is authorized by this document.

Verify current enforcement with read-only commands:

```sh
gh api repos/sufiyannadeem/cloudforge-ai/rulesets/24049172
gh api repos/sufiyannadeem/cloudforge-ai/rules/branches/main
gh api repos/sufiyannadeem/cloudforge-ai/environments/release
```

Expected: active PR rule, zero reviews, last-push/code-owner approval false, both
strict exact check contexts/app IDs, empty bypass actors, deletion/force-push blocks,
release protected-branches-only, no required-reviewer rule, and top-level
`can_admins_bypass: false`. Missing/unsupported bypass evidence blocks publication.

Next obtain separate approval for a normal push of `feat/aws-terraform-foundation`,
then creating the integration PR. Require fresh exact-head CI/Security success
before a separately approved owner merge; no independent approval is required.
After the workflow exists on main, separately authorize `publish=false` hosted
build/scan validation. Registry publication (`publish=true`), hosted signing and
consumer verification require another explicit approval; no deployment is implied.
