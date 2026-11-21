import assert from "node:assert/strict";
import { createHash, createHmac } from "node:crypto";
import test from "node:test";
import { serviceAssertion } from "../src/lib/service-identity.ts";

test("assertions bind verified identity, target, and approval body", (t) => {
  const name = "CLOUDFORGE_FRONTEND_INFRASTRUCTURE_KEY";
  const key = "infrastructure-test-identity-key-32-bytes";
  const previous = process.env[name];
  process.env[name] = key;
  t.after(() => {
    if (previous === undefined) delete process.env[name];
    else process.env[name] = previous;
  });
  const url = new URL("https://infra.example/api/v1/resources/id/apply?test=1");
  const expiry = Math.floor(Date.now() / 1000) + 10;
  const body = new TextEncoder().encode('{"plan_hash":"reviewed"}');
  const user = { sub: "operator", role: "platform-engineer", exp: expiry };
  const [payload, signature] = serviceAssertion("infrastructure", url, "POST", user, body.buffer).split(".");
  assert.equal(signature, createHmac("sha256", key).update(payload).digest("hex"));
  const claims = JSON.parse(Buffer.from(payload, "base64url").toString());
  assert.equal(claims.iss, "frontend");
  assert.equal(claims.aud, "infrastructure");
  assert.equal(claims.target, url.pathname + url.search);
  assert.equal(claims.method, "POST");
  assert.equal(claims.role, user.role);
  assert.equal(claims.exp, expiry);
  assert.equal(claims.body, createHash("sha256").update(body).digest("hex"));
  assert.notEqual(serviceAssertion("infrastructure", url, "POST", user, body.buffer).split(".")[0], payload);
});
