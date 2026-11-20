# Batch 32 — runtime image CVE remediation

**Local image gates PASS; fresh hosted acceptance remains UNVERIFIED.**
Baseline: commit `041676d1da9286a30cef6e8061b421ad27f9a580`,
[Security run 44786869766](https://github.com/sufiyannadeem/cloudforge-ai/actions/runs/44786869766).
No push, PR/settings mutation, image publication, AWS/EKS access or deployment ran.

| Image | Hosted HIGH / CRITICAL | Final local HIGH / CRITICAL |
| --- | --- | --- |
| Project | 4 / 0 | 0 / 0 |
| Infrastructure | 11 / 0 | 0 / 0 |
| Deployment | 4 / 0 | 0 / 0 |
| AIOps | 48 / 0 | 0 / 0 |
| FinOps | 48 / 0 | 0 / 0 |
| Frontend | 10 / 0 | 0 / 0 |

[Machine-readable classification](BATCH32_IMAGE_CVES.json) identifies all 125
hosted package findings, affected images, installed/fixed versions, CVEs, status,
root cause, job IDs and final local image IDs. Repeated CVEs across packages/images
are findings, not unique CVEs. Fixed-version null means the hosted report supplied
no distribution fix; no patched version was invented. No new suppression,
ignore-unfixed setting, severity downgrade or scan bypass was introduced.

## Root causes and minimal corrections

- **Go services:** the builder shipped Go 1.25.14 even though unit tests passed.
  Its standard library triggered CVE-2026-111943, -78667, -78669 and -97031. Official
  [Go release history](https://go.dev/doc/devel/release) verifies supported Go
  **1.26.11**. All three builders are pinned to its real registry digest; the four
  module minimums agree, so setup-go's existing go-version-file wiring tests the
  shipped compiler. Existing dependency versions and sums remain unchanged.
- **Terraform:** the shipped 1.16.4 executable independently contained vulnerable
  Go 1.26.8, go-jose 4.1.4 and x/net 0.58.0. Official
  [Terraform 1.17.2](https://github.com/hashicorp/terraform/releases/tag/v1.17.2)
  is digest-pinned; CI validation matches it. Actual binary metadata confirms
  Go **1.26.10**, go-jose **4.1.6**, x/net **0.62.0**; it was not rebuilt with
  locally replaced vendor dependencies. Both application and Terraform binaries
  independently scan clean. CLI/state/approval behavior uses the same implementation,
  with existing runner tests and offline mock-provider checks retained.
- **Python:** Debian 13.7 runtime packages caused the 48 findings in each image,
  including util-linux, ACL, ncurses, SQLite, systemd, Perl and zlib. Most had no
  fixed Debian version in the report; zlib's reported fix was
  `1:1.3.dfsg+really1.3.1-1+deb13u1`. Digest-pinned official Python 3.12/Alpine 3.24
  removes that Debian dependency graph. Both locked application dependency sets
  and hash-only binary-wheel installation remain unchanged. CA certificates,
  libstdc++ and non-root users are preserved. The first Alpine scan found 16
  HIGHs in its **system** Kerberos 1.22.2-r1, not Psycopg. A targeted version
  constraint installs the vendor's [krb5-libs 1.22.3-r0](https://pkgs.alpinelinux.org/packages?name=krb5-libs&branch=v3.24),
  preserving GSSAPI/native support rather than deleting required libraries.
- **Frontend:** all ten findings were under the official Node image's global
  `/usr/local/lib/node_modules/npm` tree: brace-expansion 2.0.2, ip-address 10.1.0,
  pacote 19.0.2/20.0.1, picomatch 4.0.3 and sigstore 3.1.0. A diagnostic scan of
  the same Node base independently confirmed the paths/CVEs. These were not the
  application's locked production dependencies, so no unnecessary lockfile or
  Next/React upgrade was made. The digest-pinned Alpine runner copies only the
  Node executable plus Next standalone/static/public output, with libstdc++/CA
  certificates and the existing non-root user. npm/Yarn/Corepack are absent from
  runtime layers; this is not merely a deletion hiding old packages in base layers.
  This follows [official Node multi-stage guidance](https://github.com/nodejs/docker-node/blob/main/docs/BestPractices.md)
  and the installed Next standalone deployment guide.

## Rebuild and scan evidence

All six Dockerfiles were rebuilt locally with Buildx, named `service_identity`
contexts for Go, and local `cloudforge-b32-SERVICE:local` tags. Valid build cache
was reused; no registry tag was pushed. Base digests were obtained from actual
official image pulls, not fabricated. Local config IDs in the evidence are **not
published registry digests**. Only linux/amd64 was built/tested.

Official Buildx 0.39.1 and Trivy **0.76.2** assets matched SHA256 values obtained
from GitHub release metadata. Trivy matches the failed hosted scanner version.
Database: **2026-11-20T13:11:33Z**, downloaded freshly for this run; policy bundle
was also refreshed. Final scans ran serially after an initial parallel scan hit
a cache-lock error; a missing/failed scan was never counted as zero findings.

Every final image passed this policy (output path/tag vary by service):

```sh
trivy image --cache-dir /tmp/cloudforge-b32-trivy-cache --skip-db-update --image-src docker --scanners vuln,secret,misconfig --severity HIGH,CRITICAL --ignore-unfixed=false --ignorefile /dev/null --exit-code 1 --format json --output /tmp/cloudforge-b32-evidence/SERVICE-scan-final.json cloudforge-b32-SERVICE:local
```

The skip-db-update flag follows the explicit successful database refresh; it does
not use the stale system cache. Final vulnerability, secret and misconfiguration
results are zero for all six. There are **no remaining reported unfixable HIGH/
CRITICAL findings** in these candidate images. The hosted gate stays unchanged
and its earlier failed result is not overwritten or waived.

## Focused regression/integration evidence

- All four Go modules passed `go test -mod=readonly -race -count=1 ./...` under
  the verified Go 1.26.11 toolchain; existing dependency versions stayed fixed.
- **56** release/security/CI/toolchain tests passed; three unrelated legacy wrappers
  deselected. New tests bind module/compiler and shipped/validated Terraform
  versions; existing gate failure/approval/signature tests remain enforced.
- Actual final non-root Alpine runtimes, read-only root: **26 AIOps + 13 FinOps**
  security/API tests passed. One optional FinOps capture API PostgreSQL test skipped
  without its dedicated DSN; this is not claimed as executed.
- Disposable PostgreSQL fixture `cf-drill-8a8f7f2624e24299b32ffd29ddd7bb3f` passed
  all 23 migrations, AIOps native migration, seven runtime principals, negative
  DDL/account/approval checks, hostname-verified TLS, non-owner startup and drift
  concurrency/fencing. Optional candidate-image inputs avoid retagging existing
  images. FinOps native libpq TLS plus actual scoped read and audit INSERT/readback
  passed separately; cleanup failures: none. Evidence:
  `/tmp/cloudforge-b32-database-final/evidence.json`.
- Terraform 1.17.2, network disabled and disposable module copy: fmt, validate and
  **six mock-provider plan tests** passed using the cached provider. No apply or
  AWS calls ran; this does not prove live resource lifecycle compatibility.
- All six image builds passed; frontend standalone build and three role/CSRF/
  rollout test files passed. The final Node-only image starts non-root with a
  read-only root, returns login **200**, and redirects an unauthenticated dashboard
  to login. Required service/monitoring URLs were provided as loopback fixtures;
  no backend availability or authenticated full-browser workflow was fabricated.
- All six Dockerfiles passed HIGH/CRITICAL configuration scans. Python syntax,
  staged Gitleaks and `git diff --check` passed; no new security exception was added.

Detailed local build/scan/test logs: `/tmp/cloudforge-b32-evidence/`.
Fresh hosted CI, registry digest/signature acceptance, other architectures and
actual AWS/EKS acceptance remain separately authorized gates. No production
readiness or live exploitability conclusion follows from zero scanner findings.
