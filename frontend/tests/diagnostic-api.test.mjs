import assert from "node:assert/strict";
import test from "node:test";
import { frontendApi } from "../src/lib/frontend-api.ts";

test("diagnostic capture sends only a deployment ID and uses CSRF-protected POST", async (t) => {
  const original = Object.getOwnPropertyDescriptor(globalThis, "document");
  Object.defineProperty(globalThis, "document", { configurable: true, value: { cookie: "cf_csrf=verified%20token" } });
  t.after(() => {
    if (original) Object.defineProperty(globalThis, "document", original);
    else delete globalThis.document;
  });
  const calls = [];
  t.mock.method(globalThis, "fetch", async (path, options) => {
    calls.push({ path, options });
    return Response.json(options.method === "POST" ? { id: "capture" } : []);
  });
  await frontendApi.deployments.diagnostics("deployment");
  await frontendApi.deployments.captureDiagnostic("deployment");
  assert.equal(calls.length, 2);
  const path = "/api/proxy/deployment/api/v1/deployments/deployment/diagnostics";
  assert.equal(calls[0].path, path);
  assert.equal(calls[0].options.headers["X-CSRF-Token"], undefined);
  assert.equal(calls[1].path, path);
  assert.equal(calls[1].options.method, "POST");
  assert.equal(calls[1].options.headers["X-CSRF-Token"], "verified token");
  assert.equal(calls[1].options.body, undefined);
});
