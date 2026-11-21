import assert from "node:assert/strict";
import test from "node:test";
import { frontendApi } from "../src/lib/frontend-api.ts";

test("drift requests bind the resource and include CSRF on capture only", async (t) => {
  const document = Object.getOwnPropertyDescriptor(globalThis, "document");
  Object.defineProperty(globalThis, "document", { configurable: true, value: { cookie: "cf_csrf=token" } });
  t.after(() => {
    if (document) Object.defineProperty(globalThis, "document", document);
    else delete globalThis.document;
  });
  const path = "/api/proxy/infrastructure/api/v1/resources/resource%2Fid/drift";
  const unavailable = { id: 1, status: "unavailable", findings: null };
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(url, path);
    assert.equal(options.body, undefined);
    assert.equal(options.headers["X-CSRF-Token"], options.method === "POST" ? "token" : undefined);
    return Response.json(options.method === "POST" ? unavailable : []);
  });
  assert.deepEqual(await frontendApi.infrastructure.driftHistory("resource/id"), []);
  assert.deepEqual(await frontendApi.infrastructure.scanDrift("resource/id"), unavailable);
});
