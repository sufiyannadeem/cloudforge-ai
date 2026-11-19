# Batch 30 — GitHub release preparation

**Batch 31 update:** [local signing/protection configuration](BATCH31_RELEASE_SECURITY.md)
supersedes the signing-code gap below. GitHub protection enforcement and hosted
keyless acceptance remain unverified; this document retains its historical snapshot.

Read-only GitHub review, November 20, 2026. **NO-GO for publication/deployment.**
The authenticated account has repository administration visibility; no GitHub
settings, PRs, refs, workflows or registry artifacts were changed.

## Verified baseline and external blockers

- Before this preparation commit, local `75c2fbe` is 37 commits ahead of main
  `7eafd35` and 11 ahead of peeled `v1.0.0-rc1` / remote release branch `70f7464`,
  with no divergent commits. Remote main and annotated rc1 tag match local refs.
  The latest successful hosted release-branch CI run `44487952286` tested
  **70f7464**, not the newer local commits; it is not current release evidence.
- All 16 PR heads match the earlier review; all currently have failed checks.
  Patches were freshly downloaded and checked forward/reverse against exported
  main, rc1 and current files. None is wholly merged-equivalent. Applicability
  below is a textual check, not a successful dependency upgrade test.
- Main is protected by active ruleset **24049172**, no bypass actors, strict
  up-to-date `Security Gate` (Actions integration 15368), PRs, resolved threads,
  deletion/force-push blocking. Legacy branch-protection API returns 404 because
  a ruleset provides protection. **Zero** approving reviews are required;
  `All CI Checks Passed` is **not** required. Require both aggregate checks and
  at least one independent approval; enable last-push approval and dismiss stale
  reviews. Review code-owner protection for release workflows if an ownership
  policy is established. Do not remove existing protections/checks.
- GitHub lists **zero environments**; `release` returns 404. Before publication,
  an administrator must configure real independent reviewers, prevent self-review,
  disable admin bypass, and restrict release to protected branches. The workflow
  itself additionally restricts publication to manual main requests. Never assume
  a workflow environment name establishes approval: see [GitHub guidance](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).
- Manual seven-image build/scan preserves exact scanned archives, revision,
  config IDs and SBOM; selected workloads require real registry digests. The
  publish job now rejects missing/unreadable or inadequately protected environment
  settings **before registry login/push**. This closes the local approval-policy
  assumption; hosted execution/permissions remain unverified.
- No signing/attestation implementation is wired; `provenance: false` is explicit.
  Archive hashes/SBOMs/OCI labels are not signed digest provenance. Approve an
  established signer/attestation and consumer verification policy before release;
  bind actual registry digests to source SHA, workflow identity/run and SBOM.
  Do not enable publication merely because the new environment check passes.
- Fresh hosted vulnerability scans of all seven images and current source are
  mandatory. Existing old PR failures were observed, not attributed to dependency
  changes. [Batch 29](BATCH29_RELEASE_GATE.md) retains DB cutover, central audit,
  controller/IRSA/storage and live AWS/Kubernetes gates; none was resolved remotely.

## PR disposition — recommendations only

All patches apply to old main. Current applicability equals rc1 applicability.

| PR | rc1/current | Recommended action after release baseline integration |
| --- | --- | --- |
| #49 FastAPI | Applies | Retain; test ASGI/auth and locked dependencies. |
| #48 Pydantic | Applies | Retain; test validation/serialization with FastAPI. |
| #47 deployment pgx | Conflicts | Retain/rebase; preserve identity/x-text changes and SQL/race tests. |
| #46 project pgx | Conflicts | Retain/rebase; preserve accounts/migrations/security updates. |
| #45 infrastructure pgx | Conflicts | Retain/rebase; preserve approvals/TLS/security updates. |
| #43 psycopg | Conflicts | Retain/rebase; regenerate lock and run real PostgreSQL tests. |
| #41 Sonar action | Applies | Merge candidate only after reviewed green CI. |
| #35 setup-python | Applies | Merge candidate only after reviewed runner/CI compatibility. |
| #34 React | Conflicts | Retain/rework React and react-dom together; no partial update. |
| #33 Node types | Applies | Retain/rework to align with actual Node 22 runtime. |
| #32 eslint-config-next | Conflicts | Close as superseded only after release's 16.4.5 reaches main. |
| #29 Next.js | Conflicts | Close as superseded only after release's patched 16.4.5 reaches main. |
| #28 Prometheus Go client | Conflicts | Retain; coordinate Go 1.26 requirement with CI/images. |
| #27 ESLint 10 | Conflicts | Retain; major-version tooling compatibility requires separate tests. |
| #23 upload-artifact | Applies | Merge candidate after green CI; keep expanded matrix/guards. |
| #16 Uvicorn | Applies | Retain; run ASGI/lifespan/auth regressions. |

Never replace release files with old PR snapshots. Rebase/regenerate dependency
patches individually after baseline integration. Recheck every head/check before
any approved merge/close; neither operation was performed here.

## Exact operator sequence — commands prepared, not executed

1. Review this local diff/commit and protections above; obtain **push approval**.
   Use a normal fast-forward push, never force, and stop on rejection:

   ```sh
   git status --short
   git log -1 --oneline
   git push origin HEAD:refs/heads/feat/aws-terraform-foundation
   gh run list --repo sufiyannadeem/cloudforge-ai --branch feat/aws-terraform-foundation --limit 10 --json databaseId,headSha,workflowName,status,conclusion
   ```

2. Require fresh CI/security runs on that exact pushed SHA. Inspect each run with
   `gh run view RUN_ID --repo sufiyannadeem/cloudforge-ai --log-failed` and
   `gh run watch RUN_ID --repo sufiyannadeem/cloudforge-ai --exit-status` (substitute
   actual IDs returned above). No skipped/absent job substitutes for required
   success. With separate PR-creation approval, open the integration PR:

   ```sh
   gh pr create --repo sufiyannadeem/cloudforge-ai --base main --head feat/aws-terraform-foundation --title 'Integrate reviewed CloudForge release foundation' --body 'Integrates the locally verified platform and security foundation. Review deploy/BATCH29_RELEASE_GATE.md and deploy/BATCH30_RELEASE_PREPARATION.md. Publication and deployment remain blocked pending hosted provenance, approvals and external acceptance.'
   ```

3. Require exact-head PR CI/security checks plus independent review and stronger
   main rules. Merge only with separate authorization. After main includes the
   baseline, obtain cleanup approval; revalidate #29/#32 as superseded and only
   then run `gh pr close 29 --repo sufiyannadeem/cloudforge-ai` and
   `gh pr close 32 --repo sufiyannadeem/cloudforge-ai`. Retain/rebase the others
   according to the table; no batch merges.

4. After the workflow exists on main and **separate hosted-run approval**, run
   the build/scan-only path (no publication):

   ```sh
   gh workflow run release-images.yml --repo sufiyannadeem/cloudforge-ai --ref main -f publish=false
   gh run list --repo sufiyannadeem/cloudforge-ai --workflow release-images.yml --limit 5 --json databaseId,headSha,status,conclusion
   ```

   Require seven successful builds/scans, exact source SHA, SBOM and archive
   bindings; publish job must be skipped. Review new findings without broad
   suppressions. Signing configuration, approval settings, retention and digest
   verification must be accepted separately before any `publish=true` request.
   No publish command is authorized or run by this preparation.

No release tag is moved/created. Approved publication, when implemented and
authorized, must verify real registry digests and signatures/attestations before
the existing immutable-manifest renderer; it is never deployment authorization.

## Focused local evidence

- 27 release-image/CI/security regression tests pass; three unrelated
  Terraform/history wrappers deselected. Environment tests reject missing policy,
  wrong environment, absent reviewers, self-review and unrestricted/custom-policy
  branches; workflow ordering checks require validation before registry login.
- `git diff --check` and staged Gitleaks secret scan passed.
  No all-image build, hosted dispatch, push, PR mutation, image publication,
  cloud operation or deployment was performed.
