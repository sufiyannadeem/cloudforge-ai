# Batch 31 — release security configuration (not applied)

**PARTIAL; publication/deployment remain NO-GO.** Local baseline `868d813`.
Read-only GitHub checks on November 20, 2026 still show ruleset 24049172 with zero
approving reviews and only `Security Gate` required, and zero environments. No
settings, refs, PRs, registry artifacts, cloud resources or deployments changed.

## Prepared protection settings

`github/main-ruleset.json` preserves the active default-branch scope, no bypass
actors, deletion/force-push blocking, strict up-to-date checks and resolved threads.
It requires one approving review, dismissal on updates and last-push approval.
Both exact contexts `All CI Checks Passed` and `Security Gate` are tied to the
observed GitHub Actions integration 15368; tests compare names with real jobs.
There is no review-bypass actor or ruleset bypass entry. Code-owner enforcement
is not invented without a reviewed ownership policy.

`github/release-environment.example.json` is deliberately incomplete: its empty
reviewer list must be replaced with independently verified, trusted reviewer IDs.
It requires prevention of self-review and protected-branches-only access. The
publish workflow additionally requires manual dispatch on main and reads the
live environment policy before registry login. This check does not prove a human
approved this particular job; GitHub's enforced environment gate must do that.

Administrator bypass must be disabled and independently checked in the GitHub
environment UI. The REST policy check does not claim to prove this UI setting.
Keep ruleset bypass actors empty and restrict settings administration. A sole
maintainer cannot self-approve; arrange an independent trusted reviewer.

## Exact setup actions — human approval required; not executed

First re-read and diff the live ruleset; stop if it has acquired additional rules
that the prepared file would overwrite. After separate settings-change approval:

```sh
gh api repos/sufiyannadeem/cloudforge-ai/rulesets/24049172 > /tmp/current-cloudforge-ruleset.json
gh api --method PUT repos/sufiyannadeem/cloudforge-ai/rulesets/24049172 --input deploy/github/main-ruleset.json
```

Choose a real independent reviewer (not the workflow initiator). Resolve their
GitHub ID, verify trust/access, and prepare the environment payload locally:

```sh
: "${RELEASE_REVIEWER_LOGIN:?set the approved independent reviewer login}"
gh api "users/$RELEASE_REVIEWER_LOGIN" --jq .id > /tmp/cloudforge-release-reviewer-id
python3 - <<'PY'
import json
from pathlib import Path
reviewer=int(Path('/tmp/cloudforge-release-reviewer-id').read_text())
assert reviewer > 0
policy=json.loads(Path('deploy/github/release-environment.example.json').read_text())
policy['reviewers']=[{'type':'User','id':reviewer}]
with Path('/tmp/cloudforge-release-environment.json').open('x') as out:
    json.dump(policy,out,indent=2)
PY
```

Review that non-secret file, then only with explicit settings-change approval:

```sh
gh api --method PUT repos/sufiyannadeem/cloudforge-ai/environments/release --input /tmp/cloudforge-release-environment.json
```

In repository Settings → Environments → release, disable administrator bypass.
Re-read the ruleset and environment and retain independent UI evidence. Never
interpret prepared files or successful API writes alone as enforced protections.
These commands do not push code, create a PR or dispatch a workflow.

## Digest signing, provenance and consumer policy

The protected publish job installs immutable SHA-pinned cosign-installer v4.1.3
and Cosign v3.1.4. It alone receives `id-token: write`, `packages: write`, read-only
contents/actions; builds retain contents-read only. No persistent signing secret,
PAT, AWS credential, privileged runner or broad workflow permission is added.
Normal Docker registry authentication uses the job token via stdin.

The exact scanned archives and SBOM hashes are checked before push, without
rebuilding. Candidate tags include source SHA/run/attempt. Keyless signatures and
custom in-toto attestations reference the real registry digest, not a tag/config
ID. The predicate schema URI is defined in `scripts/release-images.py`; its fields
bind service/source/workflow/run/attempt to scanned config/archive/SBOM hashes.
It is an honest workflow release receipt, not a SLSA level, independent builder
attestation or proof that the source/runner is uncompromised. No Docker load-mode
BuildKit provenance is claimed. Existing trusted source/build actions remain
part of the trust boundary.

Before emitting `images.json`, and again on CLI selection, the pinned Cosign
verifier checks digest signatures and attestations with the exact workflow SAN,
GitHub OIDC issuer, certificate source SHA/repository/main ref/manual event.
Only then does the policy inspect verified DSSE statements for exact subject,
schema and source/run/attempt/artifact bindings. The operator must provide expected
repository/SHA/run/attempt independently; unsigned manifest values cannot choose
their own trusted signer or freshness. Malformed/missing/mismatched evidence fails
closed. No production insecure, wildcard-identity or log-skipping flag is used.

Registry writes precede digest signing. A mid-run failure can leave unapproved
candidate images/signatures; it never emits the consumable seven-image manifest.
Registry cleanup/retention and admission policy remain separate approved work.
Kubernetes admission verification is **not installed** by the CLI policy.

## Local evidence and hosted acceptance still required

- 42 focused release/CI/security regressions passed; three unrelated
  Terraform/history wrappers deselected. Offline pinned Cosign crypto drill passed.
  No full build, registry operation or hosted workflow was run.
- Python/JSON/YAML syntax, production verification-flag checks, staged Gitleaks
  and `git diff --check` passed. No secret values or persistent signing keys were
  added; temporary local test keys were removed.
- Focused regression checks cover policies, exact job names and permissions,
  archive/SBOM tampering, wrong subject/source/service/run/attempt/hashes, invalid
  signature process results, streamed DSSE output, failed signing without a release
  manifest and CLI refusal without trusted expected coordinates.
- `python3 scripts/test-release-signatures.py --cosign /path/to/reviewed/cosign`
  actually verifies signatures/DSSE and rejects changed bytes, wrong keys and
  changed signed provenance using temporary local keys (removed after the drill).
  Only that offline fixture uses an empty local trust/signing configuration and
  disables transparency verification: no log exists for these local test keys.
  It is not evidence for hosted certificates, Rekor or public trust roots.
- Official v3.1.4 tool bytes matched the SHA256 in read-only GitHub release asset
  metadata. The workflow pins the official integrity-checking installer commit.
  All-source/tool compromise and upstream trust are not eliminated by checksums.

After separate push/review approval, obtain exact-head CI/security success and
apply/verify protections. Test a denied non-main dispatch and publish=false build
first. Only after explicit **registry-publication approval**, test hosted OIDC,
Fulcio/Rekor availability, GHCR OCI signature/attestation storage and independent
consumer verification on all seven real digests. Test wrong identity/source/run,
absent signature and revoked/broken evidence. Review real reviewer/bypass behavior,
retention and digest admission before accepting a release. Do not weaken trust
checks to recover a failed test. [Batch 30](BATCH30_RELEASE_PREPARATION.md) remains
the historical PR/push plan; its statement that signing is unwired is superseded
locally, not by hosted evidence. All Batch 29 AWS/DB/audit gates remain open.
