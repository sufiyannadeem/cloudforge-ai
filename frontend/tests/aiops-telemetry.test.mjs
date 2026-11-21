import assert from "node:assert/strict";
import { createHmac } from "node:crypto";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";
import { serviceAssertion } from "../src/lib/service-identity.ts";

const require = createRequire(import.meta.url);

function load(path, aliases) {
  const source = readFileSync(new URL(path, import.meta.url), "utf8");
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  });
  const exports = {};
  Function("require", "exports", outputText)((id) => Object.hasOwn(aliases, id) ? aliases[id] : require(id), exports);
  return exports;
}

test("telemetry proxies sign the exact outbound target and return parsed operator results", async (t) => {
  const { NextRequest } = require("next/server");
  const key = "test-only-frontend-to-aiops-key-32-bytes";
  const env = "CLOUDFORGE_FRONTEND_AIOPS_KEY";
  const previous = process.env[env];
  process.env[env] = key;
  t.after(() => {
    if (previous === undefined) delete process.env[env];
    else process.env[env] = previous;
  });
  const config = { serviceConfig: { aiops: "https://aiops.example" } };
  const { backendRequest } = load("../src/lib/dashboard-api.ts", {
    "@/lib/service-identity": { serviceAssertion },
    "@/lib/server-config": config,
    "@/lib/observability-api": {},
    "@/lib/role-access": {},
  });
  let role = "platform-engineer";
  let calls = 0;
  let expectedTarget;
  t.mock.method(globalThis, "fetch", async (url, options) => {
    calls++;
    const target = new URL(url);
    assert.equal(target.pathname + target.search, expectedTarget);
    assert.equal(options.method, "GET");
    const [payload, signature] = options.headers["X-CloudForge-Identity"].split(".");
    assert.equal(signature, createHmac("sha256", key).update(payload).digest("hex"));
    const claims = JSON.parse(Buffer.from(payload, "base64url"));
    assert.equal(claims.aud, "aiops");
    assert.equal(claims.iss, "frontend");
    assert.equal(claims.role, role);
    assert.equal(claims.target, expectedTarget);
    assert.equal(claims.method, "GET");
    return Response.json({ service: "deployment-service", insufficient_data_count: 1 });
  });
  const proxy = load("../src/lib/aiops-telemetry-proxy.ts", {
    "@/lib/auth": {
      SESSION_COOKIE: "cf_session",
      verifySessionToken: async (token) => token === "verified"
        ? { sub: "operator", role, exp: Math.floor(Date.now() / 1000) + 25 }
        : null,
    },
    "@/lib/dashboard-api": { backendRequest },
    "@/lib/server-config": config,
  });
  const request = (path, authorized = true) => new NextRequest("https://console.example" + path, {
    headers: { "x-cloudforge-role": "platform-engineer", ...(authorized ? { cookie: "cf_session=verified" } : {}) },
  });
  const routes = {
    slo: load("../src/app/api/slo/route.ts", { "@/lib/aiops-telemetry-proxy": proxy }),
    anomaly: load("../src/app/api/anomalies/summary/route.ts", { "@/lib/aiops-telemetry-proxy": proxy }),
  };
  expectedTarget = "/api/v1/slo/summary?service=deployment-service";
  const slo = await routes.slo.GET(request("/api/slo?ignored=1"));
  assert.equal(slo.status, 200);
  assert.equal((await slo.json()).insufficient_data_count, 1);
  role = "sre";
  expectedTarget = "/api/v1/anomalies/summary?service=deployment+service&window_minutes=60&step_seconds=60";
  const anomaly = await routes.anomaly.GET(request("/api/anomalies/summary?step_seconds=60&service=deployment%20service"));
  assert.equal(anomaly.status, 200);
  assert.equal((await anomaly.json()).service, "deployment-service");
  assert.equal((await routes.slo.GET(request("/api/slo", false))).status, 401);
  role = "developer";
  assert.equal((await routes.anomaly.GET(request("/api/anomalies/summary"))).status, 403);
  assert.equal(calls, 2);
});
