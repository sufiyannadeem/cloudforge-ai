# Reviewed image handoff (Batch 28)

`.github/workflows/release-images.yml` is manual, builds/scans all six services
plus the hardened PostgreSQL image, and preserves the exact scanned image archives
with SHA-256, local config ID, source revision and SBOM. Publishing downloads only
artifacts from that same workflow run, checks all archive bindings first, loads
and checks each image ID, and pushes without rebuilding. The output `images.json`
contains actual registry digests, never guessed hashes or local config IDs.

The current [solo-maintainer setup](github/SOLO_MAINTAINER.md) requires a `release`
environment restricted to protected branches, without required reviewers. The
workflow additionally restricts publication to main. Disable administrator bypass
where GitHub exposes that setting; do not claim a second-person approval gate.
Protect the workflow/source branch and both required CI checks;
review GHCR package permissions and artifact storage limits/retention. No workflow
or environment was invoked/configured by this local change. Build/scan jobs have
read-only repository permission. Only the approved publish job gets package-write
and artifact-read permission. It has no AWS or deployment permission.

Publishing is disabled by default and allowed only for an explicit manual
main-branch request. This is **PARTIAL / hosted verification BLOCKED**, not a
claim of independent approval or verified hosted enforcement.
The publish job now checks the actual GitHub environment before downloading
artifacts or logging into GHCR. Missing/unreadable policy or unrestricted branches
fails closed. Unexpected required reviewers are rejected to prevent solo lockout.
It requires
protected-branches-only policy (not custom patterns); main protection and disabled
administrator bypass must still be verified against actual GitHub settings. This
configuration check does not prove signed provenance or human approval.
Batch 31 wires pinned Cosign 3.1.4 keyless signing and a custom signed
scanned-image release predicate. Only the protected publish job has OIDC and
package-write permission. The predicate binds source SHA, workflow/run/attempt,
service, scanned config ID, archive SHA256 and SBOM SHA256 to the actual registry
digest. This is a scanned-build handoff receipt, not hermetic/SLSA-certified
BuildKit provenance; `provenance: false` on the archive-only Docker build remains
intentional. [Signing design and limits](BATCH31_RELEASE_SECURITY.md) remain valid;
the solo setup supersedes its independent-review prerequisites for GitHub only.

Images initially receive unique candidate tags. After upload, Cosign signs and
attests each exact digest. All seven signatures and signed claims must verify
before `images.json` is emitted/uploaded. Failed signing can leave candidate
images in GHCR; registry publication is not atomic and must not imply promotion.
No consumer should trust a candidate tag or an unsigned manifest. Verification
requires the exact workflow/main identity, GitHub issuer, source SHA, event/ref,
repository and expected run/attempt. No transparency/certificate checks are
disabled. Trust policy, registry retention, network access and real hosted
keyless execution still require separately authorized acceptance.

After an approved hosted run, use its immutable manifest with real non-secret
release inputs in an existing private review workspace. CLI paths must remain
inside the current directory; JSON inputs use bounded no-follow descriptors,
and symlinked files/directories or outside paths are rejected. From repo root:

```sh
REPO_ROOT="$PWD"
cd "${REVIEW_WORKSPACE:?directory containing deployment-inputs.json and images.json}"
umask 077
python3 "$REPO_ROOT/scripts/release-images.py" --config deployment-inputs.json --manifest images.json --repository sufiyannadeem/cloudforge-ai --revision "${APPROVED_SHA:?}" --run-id "${APPROVED_RUN_ID:?}" --run-attempt "${APPROVED_RUN_ATTEMPT:?}" --output reviewed-release-inputs.json
python3 "$REPO_ROOT/scripts/render-kubernetes.py" --config reviewed-release-inputs.json > reviewed-release.yml
```

Check renderer CLI help if using a different version; never overwrite an approved
release artifact. Install the reviewed pinned Cosign tool first. Take expected
SHA/run/attempt from maintainer-reviewed hosted evidence, never from the
untrusted manifest itself. CLI selection verifies signatures/provenance against
the registry before writing renderer inputs; old unsigned manifests fail closed.
The six workload images are pinned to registry digests; the
PostgreSQL digest is also retained as `database_client_image`. Monitor/controller
images require their own reviewed digests. Production Compose requires explicit
image variables rather than `:prod` defaults, distinct verified DB DSNs and CA.
An environment substitution alone does not prove a digest exists: production
acceptance must compare the reviewed manifest and registry scan/provenance.

No registry publication, build of all seven images, cloud access, cluster change
or Terraform execution was performed locally. Tests cover artifact tampering,
incomplete/tag-only manifests, local publish refusal, signed-claim binding,
failed signing and workflow approval wiring. Separate offline crypto fixtures use
disposable keys; they do not establish Fulcio/Rekor/OIDC or GHCR acceptance.
