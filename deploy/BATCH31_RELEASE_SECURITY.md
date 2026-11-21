# Batch 31 — release security configuration

**Current policy:** [solo-maintainer GitHub setup](github/SOLO_MAINTAINER.md)
supersedes the original independent-review design. The approved settings were
read back in Batch 33: ruleset 24049172 requires PRs, zero reviews, strict
`All CI Checks Passed` and `Security Gate` checks, no bypass actors and no
force-push/deletion. `release` restricts protected branches, requires no reviewers
and has `can_admins_bypass: false`. No independent approval is claimed.

Batch 33.1 pins the top-level environment API field in
`github/release-environment.example.json` and requires literal false in the
publish preflight. Missing, true or malformed values block registry login.
The branch and reviewer checks remain in force. Owners can change settings;
this is not protection against a compromised owner. See the current setup for
read-only verification commands; future mutations require explicit approval.

**PARTIAL; publication/deployment remain NO-GO.** Batch 32 hosted CI and the
six-image Security Gate passed at `0c3d7abd`. The manual seven-image release
workflow, registry publication and hosted keyless verification remain unverified.
Platform RBAC and Terraform/remediation approvals are unchanged.

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
re-read the already applied protections. Test a denied non-main dispatch and publish=false build
first. Only after explicit **registry-publication approval**, test hosted OIDC,
Fulcio/Rekor availability, GHCR OCI signature/attestation storage and independent
consumer verification on all seven real digests. Test wrong identity/source/run,
absent signature and revoked/broken evidence. Review real branch/bypass behavior,
retention and digest admission before accepting a release. Do not weaken trust
checks to recover a failed test. [Batch 30](BATCH30_RELEASE_PREPARATION.md) remains
the historical PR/push plan; its statement that signing is unwired is superseded
locally, not by hosted evidence. All Batch 29 AWS/DB/audit gates remain open.
