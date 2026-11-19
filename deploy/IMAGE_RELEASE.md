# Reviewed image handoff (Batch 28)

`.github/workflows/release-images.yml` is manual, builds/scans all six services
plus the hardened PostgreSQL image, and preserves the exact scanned image archives
with SHA-256, local config ID, source revision and SBOM. Publishing downloads only
artifacts from that same workflow run, checks all archive bindings first, loads
and checks each image ID, and pushes without rebuilding. The output `images.json`
contains actual registry digests, never guessed hashes or local config IDs.

Before enabling publication, administrators must preconfigure the `release`
environment with independent reviewers, prevent self-review/bypass and constrain
it to protected main. Protect the workflow/source branch and required CI checks;
review GHCR package permissions and artifact storage limits/retention. No workflow
or environment was invoked/configured by this local change. Build/scan jobs have
read-only repository permission. Only the approved publish job gets package-write
and artifact-read permission. It has no AWS or deployment permission.

Publishing is disabled by default and allowed only for an explicit manual
main-branch request. This is **PARTIAL / hosted verification BLOCKED**, not a
claim that an environment with missing reviewer configuration is protected.
The publish job now checks the actual GitHub environment before downloading
artifacts or logging into GHCR. Missing/unreadable policy, absent reviewers,
permitted self-review or unrestricted branches fails closed. It requires
protected-branches-only policy (not custom patterns); main protection and disabled
administrator bypass must still be independently verified. This configuration
check does not prove signed provenance or replace GitHub's approval enforcement.
Signing/attestation policy and registry retention must be configured and verified
before production acceptance. SBOM/metadata are not cryptographic provenance.

After an approved hosted run, use its immutable manifest with real non-secret
release inputs:

```sh
python3 scripts/release-images.py --config /path/to/deployment-inputs.json --manifest /path/to/images.json --output /tmp/reviewed-release-inputs.json
python3 scripts/render-kubernetes.py --config /tmp/reviewed-release-inputs.json > /tmp/reviewed-release.yml
```

Check renderer CLI help if using a different version; never overwrite an approved
release artifact. The six workload images are pinned to registry digests; the
PostgreSQL digest is also retained as `database_client_image`. Monitor/controller
images require their own reviewed digests. Production Compose requires explicit
image variables rather than `:prod` defaults, distinct verified DB DSNs and CA.
An environment substitution alone does not prove a digest exists: production
acceptance must compare the reviewed manifest and registry scan/provenance.

No registry publication, build of all seven images, cloud access, cluster change
or Terraform execution was performed locally. Tests cover artifact tampering,
incomplete/tag-only manifests, local publish refusal and workflow approval wiring.
