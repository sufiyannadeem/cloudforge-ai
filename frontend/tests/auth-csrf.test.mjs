import assert from "node:assert/strict";
import test from "node:test";
import { matchesCSRF, originMatchesRequest, secureAuthCookies, publicOrigin } from "../src/lib/csrf.ts";

test("mutations require the current session CSRF value in both places", () => {
  assert.equal(matchesCSRF("session-value", "session-value", "session-value"), true);
  assert.equal(matchesCSRF("session-value", "session-value", "other"), false);
  assert.equal(matchesCSRF("session-value", undefined, "session-value"), false);
  assert.equal(matchesCSRF(null, "session-value", "session-value"), false);
});

test("cross-origin mutations are rejected", () => {
  const url = "https://cloudforge.example/api/auth/logout";
  assert.equal(originMatchesRequest("https://cloudforge.example", url, "cloudforge.example"), true);
  assert.equal(originMatchesRequest("https://attacker.example", url, "cloudforge.example"), false);
  assert.equal(originMatchesRequest("http://cloudforge.example", url, "cloudforge.example"), false);
  assert.equal(originMatchesRequest(null, url, "cloudforge.example"), false);
});

test("only explicit loopback HTTP can use insecure authentication cookies", (t) => {
  const key = "CLOUDFORGE_AUTH_COOKIE_SECURE";
  const previous = process.env[key];
  t.after(() => {
    if (previous === undefined) delete process.env[key];
    else process.env[key] = previous;
  });
  delete process.env[key];
  assert.equal(secureAuthCookies("http://localhost:3000"), true);
  process.env[key] = "false";
  assert.equal(secureAuthCookies("http://localhost:3000"), false);
  assert.equal(secureAuthCookies("https://localhost:3000"), true);
  assert.equal(secureAuthCookies("http://cloudforge.example"), true);
});


test("private HTTP uses the pinned public HTTPS origin and rejects forged hosts", (t) => {
  const previous = process.env.CLOUDFORGE_PUBLIC_ORIGIN;
  t.after(() => { if (previous === undefined) delete process.env.CLOUDFORGE_PUBLIC_ORIGIN;
    else process.env.CLOUDFORGE_PUBLIC_ORIGIN = previous; });
  process.env.CLOUDFORGE_PUBLIC_ORIGIN = "https://public.execute-api.example";
  const internal = "http://frontend:3000/api/auth/login";
  assert.equal(originMatchesRequest("https://public.execute-api.example", internal, "internal-alb"), true);
  assert.equal(originMatchesRequest("https://evil.example", internal, "evil.example"), false);
  assert.equal(originMatchesRequest("http://public.execute-api.example", internal, "internal-alb"), false);
  assert.equal(publicOrigin(internal), "https://public.execute-api.example");
  process.env.CLOUDFORGE_PUBLIC_ORIGIN = "https://public.execute-api.example/path";
  assert.equal(originMatchesRequest("https://public.execute-api.example", internal, "internal-alb"), false);
});

test("production rejects localhost HTTP exceptions and always secures auth cookies", (t) => {
  const keys = ["NODE_ENV", "CLOUDFORGE_LOCAL_DEV", "CLOUDFORGE_PUBLIC_ORIGIN", "CLOUDFORGE_AUTH_COOKIE_SECURE"];
  const before = Object.fromEntries(keys.map(key => [key, process.env[key]]));
  t.after(() => keys.forEach(key => { if (before[key] === undefined) delete process.env[key]; else process.env[key] = before[key]; }));
  process.env.NODE_ENV = "production";
  process.env.CLOUDFORGE_LOCAL_DEV = "true";
  process.env.CLOUDFORGE_AUTH_COOKIE_SECURE = "false";
  for (const host of ["localhost", "127.0.0.1", "[::1]"]) {
    const origin = `http://${host}:3000`;
    process.env.CLOUDFORGE_PUBLIC_ORIGIN = origin;
    assert.throws(() => publicOrigin(origin), /Invalid public origin/);
    assert.equal(secureAuthCookies(origin), true);
    assert.equal(originMatchesRequest(origin, origin, `${host}:3000`), false);
  }
  process.env.NODE_ENV = "development";
  process.env.CLOUDFORGE_PUBLIC_ORIGIN = "http://localhost:3000";
  assert.equal(publicOrigin("http://localhost:3000"), "http://localhost:3000");
  assert.equal(secureAuthCookies("http://localhost:3000"), false);
});
