import assert from "node:assert/strict";
import test from "node:test";
import { frontendApiRequest } from "../src/lib/frontend-api.ts";

test("project create, edit and delete send the existing session CSRF token", async (t) => {
  const document = Object.getOwnPropertyDescriptor(globalThis, "document");
  Object.defineProperty(globalThis, "document", { configurable: true, value: { cookie: "cf_csrf=project-token" } });
  t.after(() => {
    if (document) Object.defineProperty(globalThis, "document", document);
    else delete globalThis.document;
  });
  t.mock.method(globalThis, "fetch", async (_url, options) => {
    assert.equal(options.headers["X-CSRF-Token"], "project-token");
    return options.method === "DELETE" ? new Response(null, { status: 204 }) : Response.json({});
  });
  for (const method of ["POST", "PATCH", "DELETE"]) {
    await frontendApiRequest("/api/proxy/project/projects/project", { method });
  }
});
