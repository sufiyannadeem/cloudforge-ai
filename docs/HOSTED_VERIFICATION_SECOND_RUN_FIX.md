# Second hosted Consolidated Release Verification: focused fixes

Reviewed the complete 1,392-line log and all job/step results of
[run 45572638680](https://github.com/sufiyannadeem/cloudforge-ai/actions/runs/45572638680)
at main `030d1326b682dc5dadae1dfc619912abaa14be5b`.

## Confirmed root causes and corrections

1. **Prometheus fixture setup:** `slo-evidence.test.yml` names a generated
   `slo-evidence-rules.yml`. The native gate previously invoked promtool directly
   without generating that file, so availability, request-success and latency
   expectations all returned no samples. Extracted the existing fixture-generation
   logic into `prepare_fixture()` and reuse it from both the native gate and legacy
   Docker helper. The native test runs with the generated file and unchanged fixture
   together in a temporary working directory. Production recording rules, expected
   sample values, 45-second freshness, latency threshold, coverage logic and existing
   seven-day-to-five-minute/36,288-to-18 scaling are unchanged. Other fixtures keep
   their own working directories.
2. **Official IntOrString conversion:** pinned Kubernetes OpenAPI defines
   `io.k8s.apimachinery.pkg.util.intstr.IntOrString` as `type: string` with
   `format: int-or-string`; it does not use the CRD extension. The converter only
   handled `x-kubernetes-int-or-string`, causing valid numeric probe/service ports
   to fail. `strict_schema()` now handles both representations as an integer/string
   type union, including definitions closed by `standalone()`. It retains existing
   anyOf/oneOf/allOf branch constraints rather than overwriting anyOf. Defined-object
   unknown-field checks and all source pins remain. Regression tests reject booleans,
   fractional numbers, null, arrays, objects, unknown fields and invalid CRD branch
   values. No missing-schema fallback or permissive replacement was introduced.
3. **Go fixture SQL parameter inference:** PostgreSQL's full statement log pinpoints
   the fixture INSERT at `deployment_remediation_integration_test.go:139`, not the
   production claim UPDATE. It reports `$2`, text versus character varying, where
   the same parameter populated a varchar incident ID and entered
   `cloudforge_remediation_current_state(text,text)`. The fixture now explicitly
   types its four text parameters and project UUID at every use. A real integration
   subtest prepares this exact INSERT and verifies PostgreSQL parameter OIDs before
   inserting. Production claim SQL, transaction/locking order, authorization,
   independent approval, expiry, immutable contract, concurrency and replay checks
   are untouched; the rest of the integration scenario remains mandatory.
4. **Final line-7 AssertionError:** correct downstream aggregation. Plan succeeded,
   native and postgres-hosted failed, and the inactive dedicated job skipped. The
   unchanged aggregate assertion must reject those results. Cached regressions still
   require every active gate to succeed.

## Acquisition revision — separate human approval required

Only the schema bundle manifest value changed in the acquisition lock. The original
bundle was reproduced from the same pinned source bytes before the converter change;
the revised bundle was reproduced twice and all 314 schemas passed Draft-7 legality
checks. No tool, provider, image, model, wheel, bootstrap/corpus hash or source pin
was changed. Generated schema bodies remain temporary build outputs, not committed
assets. The acquisition evidence records the revised derivation and pending review.

| Artifact | Previous SHA256 | Revised SHA256 |
| --- | --- | --- |
| Schema bundle manifest | `a9a9ba9365ff72a5f1710e8c2d20b3da28a99501c94ac7c884e5c9f9bf35bea8` | `297ea2fa316ae6ab3f4fc96b7111d5613bb685493bb9fb0c6bdb3e7e2191f482` |
| Acquisition lock | `229740c6df87058f6c06162b908b8f48a9b408a5979ab6b5079492e0669e2d45` | `8f73972d01681d32e3c3e817fc176dc15b19bb93893da1bfab8578fa2846759e` |
| Acquisition evidence JSON | `44a94a0aa7efbf6034a317fa36a3f5ce4ce7e48a02605fe14ff9d08b4b1cc5c0` | `dd4da8e11ca5d52417a1d16d932439695f0e5f8aaf3522ee6767d9dc2afd0233` |

The revised generation changes **28 of 314** schema files. Source retrieval was
bounded to five existing hash-pinned official OpenAPI/CRD documents plus the vendored
CRD (5,114,630 total source bytes). No native tool, dependency, model or provider
was downloaded. Existing lock `reviewed_by: null`, pending status and explicit
human/hash gates remain. No environment variable or approval setting was updated.
Review the revised source/evidence and independently recompute the new lock hash
before approving it in all three protected CI environments. Old-hash approval must
fail for this lock. Semantic candidates/runs must bind the new exact reviewed SHA.
Historical review documents retain the old hashes as historical evidence; active
operator instructions and status point to the revised lock.

## Verification performed

- **54 cached Python checks passed, 3 deselected**: new schema/fixture regressions,
  first-run ordering and mandatory aggregate regressions, consolidated mechanics and
  selected CI hardening. Real Terraform and the redundant in-test Gitleaks invocation
  were not selected locally; required hosted checks were not removed or skipped.
- **Actual cached Prometheus 3.5.0 promtool passed:** syntax-only configuration,
  all five rule files (76 rules), and all six rule fixtures, including unchanged SLO
  availability=1/0, success=1/0.8 and latency=1/0.5 expectations. One-shot cached Docker
  execution used no pull, no network, read-only input/root filesystems and a bounded
  temporary filesystem; no Prometheus server or cluster was started. Initial local
  read-only-root invocation failed because promtool needs temporary storage; the
  corrected harness grants only /tmp and passes.
- **314 generated schemas:** all Draft-7 legal; reproducible manifest. Actual Helm
  lint/template and Kustomize renders plus the existing Rollouts/RBAC examples
  produced 52 objects. All 52 validate against the revised strict schemas using
  cached Python jsonschema; the old schemas reject 16 of the same objects.
  Native kubeconform was unavailable locally and is not claimed as passed.
- **Go integration target compilation passed** with already cached Go 1.26.11,
  GOPROXY=off and GOTOOLCHAIN=local, using `go test -tags integration ... -run '^$'`.
  This compiles but deliberately executes no PostgreSQL integration test. Initial
  compile hit the sandbox's read-only default Go cache; a /tmp build cache resolved it
  without downloading. No successful PostgreSQL/atomic-claim result is claimed.
- Changed-source parsing, Go formatting, exact 10-file pending scope, full
  tracked/unignored source secret scan and whitespace checks passed. No files staged.

## Remaining gates and observed log boundaries

The reviewed run passed module/provider mirroring and actionlint after the first-run
fix. Helm and Kustomize passed. It progressed beyond the mandatory eight Python
PostgreSQL cases to the failing Go fixture. Server-log privilege denials are expected
negative ACL tests, not additional independent blockers. No other independent failed
step was found. Native Terraform/TLS checks were not reached after native validation
failed and must still execute. The new Go parameter-OID regression and full atomic
claim scenario also require real hosted PostgreSQL execution.

After protected review/merge and separate approval of the revised acquisition hash,
an authorized operator must run verification at the new source SHA. This work does
not merge the PR, dispatch workflows, change protections/approvals, call AWS, run
paid inference, start local Kubernetes or download heavy local dependencies.

## Source-publication authorization

The user explicitly authorized source publication of this reviewed 10-file correction
on `codex/fix-second-hosted-verification`, including the revised acquisition lock,
schema bundle manifest hash and evidence, with expected acquisition SHA256
`8f73972d01681d32e3c3e817fc176dc15b19bb93893da1bfab8578fa2846759e`.
The earlier staging attempt was rejected by automatic approval review pending that
explicit authorization; it staged no files and was not bypassed.

This authorization covers staging, committing, pushing and opening a protected-main
PR only. It does not grant CI acquisition, protected-environment approval changes,
workflow dispatch, PR merge or production release. The lock keeps `reviewed_by: null`
and `VERIFIED_INPUTS_PENDING_HUMAN_APPROVAL`; separate hash review and CI approval
remain required before the revised inputs can be acquired by hosted verification.
