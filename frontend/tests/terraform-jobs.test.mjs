import assert from "node:assert/strict";
import test from "node:test";
import { waitForTerraformJob } from "../src/lib/terraform-jobs.ts";

function pollingFixture(t, states) {
  const originalFetch = globalThis.fetch;
  const originalTimeout = globalThis.setTimeout;
  let calls = 0;
  globalThis.setTimeout = (callback) => originalTimeout(callback, 0);
  globalThis.fetch = async (url, options) => {
    assert.equal(url, "/resources/resource/jobs/11111111-1111-1111-1111-111111111111");
    assert.equal(options.cache, "no-store");
    calls++;
    return Response.json(states.shift());
  };
  t.after(() => { globalThis.fetch = originalFetch; globalThis.setTimeout = originalTimeout; });
  return () => calls;
}
const receipt = () => Response.json({ id: "11111111-1111-1111-1111-111111111111" }, { status: 202 });

test("queued operation polls until durable result instead of resubmitting", async (t) => {
  const count = pollingFixture(t, [{ status: "running" }, { status: "succeeded", response_code: 200, response: { status: "active" } }]);
  const result = await waitForTerraformJob(receipt(), "/resources/resource");
  assert.equal(count(), 2);
  assert.deepEqual(await result.json(), { status: "active" });
});
test("interrupted mutation requires reconciliation", async (t) => {
  const count = pollingFixture(t, [{ status: "interrupted" }]);
  await assert.rejects(waitForTerraformJob(receipt(), "/resources/resource"), /Reconcile Terraform state/);
  assert.equal(count(), 1);
});
test("failed operation preserves server error and is never retried", async (t) => {
  const count = pollingFixture(t, [{ status: "failed", response_code: 409, response: { error: { message: "approval expired" } } }]);
  const result = await waitForTerraformJob(receipt(), "/resources/resource");
  assert.equal(result.status, 409);
  assert.equal(count(), 1);
});
