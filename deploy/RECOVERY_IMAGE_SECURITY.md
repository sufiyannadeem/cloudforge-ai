# Recovery image security review — 2026-11-19

The old cached PostgreSQL image had 47 HIGH / 1 CRITICAL findings. No finding
was suppressed. Findings are package matches, not demonstrated exploit chains.

| Package / location | Installed | Fixed package/toolchain floor | Reachability assessment |
| --- | --- | --- | --- |
| krb5-libs (16 findings) | 1.22.2-r1 | 1.22.3-r0 | Many findings require a KDC/kadmind/PKINIT server, which the PostgreSQL container does not run. GSS/NegoEx paths may matter if configured; not universally non-exploitable. |
| libxslt (3) | 1.1.43-r3 | 1.1.43-r4 | Requires attacker-influenced XML/XSLT processing; PostgreSQL extensions/SQL permissions can affect reachability. No malicious document exploit attempted. |
| musl / musl-utils (2 matches) | 1.2.6-r2 | 1.2.6-r3 | Shared libc code is widely linked; DNS/input exposure depends on actual callers. Treat as applicable rather than dismissing it. |
| zlib (1) | 1.3.2-r0 | 1.3.2-r1 | Compressed-input paths can be relevant to tooling/extensions. No untrusted archive exploit attempted. |
| /usr/local/bin/gosu Go stdlib (26) | go1.24.6 | Per-CVE versions below; currently supported fixed branches include 1.26.10 / 1.27.3 | gosu is a privilege-switch/exec helper, not an HTTP/TLS server. TLS resumption/parser findings are not demonstrated reachable through its normal entrypoint path. No VEX exclusion used. |

The CRITICAL CVE-2025-68121 requires TLS session resumption after mutation of
ClientCAs/RootCAs. That behavior is not part of gosu's user-switching path;
this is source-based reachability assessment, not a general exploitability proof.
The entire vulnerable helper/runtime is removed instead of hiding findings.

Primary references: [PostgreSQL support](https://www.postgresql.org/support/versioning/),
[official image source](https://github.com/docker-library/postgres/blob/master/16/alpine3.24/Dockerfile),
[Alpine security database](https://secdb.alpinelinux.org/v3.24/main.json),
[Go critical advisory](https://pkg.go.dev/vuln/GO-2026-4337),
[gosu source](https://github.com/tianon/gosu/blob/1.20/main.go),
[su-exec privilege/signal semantics](https://github.com/ncopa/su-exec).

## Replacement and compatibility

PostgreSQL **16.16** remains on the supported 16.x major. The official image
`postgres:16.16-alpine@sha256:1d5b02d3a9941fbd52437db4107f8c52d6297dac553ca1e5c299ebb3756b4857`
fixes the 22 OS matches but still ships the 26 Go matches. A minimal local
derivative (`recovery/Postgres.Dockerfile`) replaces gosu with signed-repository
Alpine `su-exec=0.3-r0`, preserving both executable names. The final runtime is
copied from that cleaned filesystem into a fresh stage so deleted vulnerable
Go binaries are absent from distributed lower layers as well. Build tests check named
and numeric UID/GID switching; real initdb, logical/WAL restore and server startup
must pass before acceptance. No entrypoint, database privilege or approval bypass
is introduced. The final image defaults to UID/GID 70:70, retaining the official
entrypoint and SIGINT shutdown. Existing/mounted storage must be prepared for
that UID; never change ownership of existing production volumes automatically.
Only newly created fixture mounts receive explicit root initialization.

The actual **local image config digest** is pinned in
`recovery/postgres-image.json`; the upstream registry digest is independently
pinned in the Dockerfile. No derivative registry digest is invented: publishing,
multi-architecture images and production deployment remain outside this task.
Rebuilding can change the local config digest; inspect, scan and validate it before
updating the pin. The drill fails closed when the pinned local image is missing.
Existing Compose containers/data are not changed by this selection.

```sh
docker pull postgres:16.16-alpine@sha256:1d5b02d3a9941fbd52437db4107f8c52d6297dac553ca1e5c299ebb3756b4857
docker build --pull=false -f deploy/recovery/Postgres.Dockerfile -t cloudforge-postgres:recovery-16.16 deploy/recovery
docker image inspect cloudforge-postgres:recovery-16.16 --format '{{.Id}}'
# Compare with the reviewed pin; do not silently update it.
python3 scripts/test-recovery-chaos.py --output-dir /tmp/cloudforge-patched-recovery-UNIQUE
```

Final Trivy 0.76.2 image scan: **0 HIGH / 0 CRITICAL**, without ignore-unfixed,
VEX or new exceptions. Database updated 2026-11-19 07:06:49 UTC, still within its
next-update interval during testing. This is not a claim of zero lower-severity
or undiscovered vulnerabilities. No existing Compose image/data was replaced.

## Exact original findings and scanner fixed versions

These are scanner-reported versions for the original image, not claims that an
obsolete Go branch is still supported. No CVEs are excluded from the replacement
scan. Preserve current vendor database checks before release use.

| CVE | Package | Fixed versions | Severity |
| --- | --- | --- | --- |
| CVE-2026-107364 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112315 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112316 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112317 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112318 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112319 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112320 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112321 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112322 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-112323 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-118380 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-119079 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-40355 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-40356 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-71199 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-71200 | krb5-libs | 1.22.3-r0 | HIGH |
| CVE-2026-125350 | libxslt | 1.1.43-r4 | HIGH |
| CVE-2026-87636 | libxslt | 1.1.43-r4 | HIGH |
| CVE-2026-9947 | libxslt | 1.1.43-r4 | HIGH |
| CVE-2026-107891 | musl | 1.2.6-r3 | HIGH |
| CVE-2026-107891 | musl-utils | 1.2.6-r3 | HIGH |
| CVE-2026-85091 | zlib | 1.3.2-r1 | HIGH |
| CVE-2025-68121 | stdlib | 1.24.13, 1.25.7, 1.26.0-rc.3 | CRITICAL |
| CVE-2025-61726 | stdlib | 1.24.12, 1.25.6 | HIGH |
| CVE-2025-61729 | stdlib | 1.24.11, 1.25.5 | HIGH |
| CVE-2026-111943 | stdlib | 1.26.10, 1.27.3 | HIGH |
| CVE-2026-25679 | stdlib | 1.25.8, 1.26.1 | HIGH |
| CVE-2026-27145 | stdlib | 1.25.11, 1.26.4 | HIGH |
| CVE-2026-32280 | stdlib | 1.25.9, 1.26.2 | HIGH |
| CVE-2026-32281 | stdlib | 1.25.9, 1.26.2 | HIGH |
| CVE-2026-32283 | stdlib | 1.25.9, 1.26.2 | HIGH |
| CVE-2026-33811 | stdlib | 1.25.10, 1.26.3 | HIGH |
| CVE-2026-33814 | stdlib | 1.25.10, 1.26.3 | HIGH |
| CVE-2026-33818 | stdlib | 1.25.13, 1.26.6, 1.27.0-rc.3 | HIGH |
| CVE-2026-39820 | stdlib | 1.25.10, 1.26.3 | HIGH |
| CVE-2026-39821 | stdlib | 1.25.13, 1.26.6, 1.27.0-rc.3 | HIGH |
| CVE-2026-39822 | stdlib | 1.25.12, 1.26.5, 1.27.0-rc.2 | HIGH |
| CVE-2026-39836 | stdlib | 1.25.10, 1.26.3 | HIGH |
| CVE-2026-42499 | stdlib | 1.25.10, 1.26.3 | HIGH |
| CVE-2026-42504 | stdlib | 1.25.11, 1.26.4 | HIGH |
| CVE-2026-56853 | stdlib | 1.25.13, 1.26.6, 1.27.0-rc.3 | HIGH |
| CVE-2026-56858 | stdlib | 1.25.13, 1.26.6, 1.27.0-rc.3 | HIGH |
| CVE-2026-56859 | stdlib | 1.25.13, 1.26.6, 1.27.0-rc.3 | HIGH |
| CVE-2026-56860 | stdlib | 1.25.13, 1.26.6, 1.27.0-rc.3 | HIGH |
| CVE-2026-56862 | stdlib | 1.25.13, 1.26.6, 1.27.0-rc.3 | HIGH |
| CVE-2026-78667 | stdlib | 1.26.9, 1.27.2 | HIGH |
| CVE-2026-78669 | stdlib | 1.26.9, 1.27.2 | HIGH |
| CVE-2026-97031 | stdlib | 1.26.9, 1.27.2 | HIGH |
