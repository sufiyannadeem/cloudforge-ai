import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);

function load(path, aliases = {}) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const exports = {};
  Function("require", "exports", code)((id) => Object.hasOwn(aliases, id) ? aliases[id] : require(id), exports);
  return exports;
}

const { default: ProfileMenu } = load("../src/components/layout/ProfileMenu.tsx");

for (const [role, label] of Object.entries({ "platform-engineer": "Platform Engineer", sre: "SRE", developer: "Developer" })) {
  test(`profile renders verified ${role} data inside the disclosure`, () => {
    const html = renderToStaticMarkup(createElement(ProfileMenu, {
      viewer: { username: "account-name", email: "account@example.test", role, csrfToken: "private-token" },
    }));
    assert.match(html, /<details[^>]*><summary[^>]*aria-label="Profile"/);
    assert.match(html, /account-name/);
    assert.match(html, /account@example\.test/);
    assert.ok(html.includes(`<dd>${label}</dd>`));
    assert.match(html, />Sign Out<\/button>/);
    assert.doesNotMatch(html, /private-token/);
  });
}

test("profile has a compact mobile trigger, viewport-bounded panel and absent email state", () => {
  const html = renderToStaticMarkup(createElement(ProfileMenu, {
    viewer: { username: "legacy", role: "developer", email: null, csrfToken: "" },
  }));
  assert.match(html, /hidden max-w-32 truncate sm:inline/);
  assert.ok(html.includes("max-w-[calc(100vw-2rem)]"));
  assert.match(html, /<dd>Not provided<\/dd>/);
});

test("profile and logout require the authenticated session and revocation clears both cookies", async () => {
  const { NextRequest } = require("next/server");
  const csrf = load("../src/lib/csrf.ts");
  let revoked = false;
  const auth = {
    SESSION_COOKIE: "cf_session", CSRF_COOKIE: "cf_csrf",
    verifySessionToken: async (token) => token === "valid" && !revoked
      ? { sub: "account", role: "sre", email: null, csrf: "csrf", exp: 2_000_000_000 }
      : null,
    sessionCSRF: (token) => token === "valid" ? "csrf" : null,
    revokeSession: async (token) => { assert.equal(token, "valid"); revoked = true; return true; },
  };
  const { GET } = load("../src/app/api/auth/session/route.ts", { "@/lib/auth": auth });
  const { POST } = load("../src/app/api/auth/logout/route.ts", { "@/lib/auth": auth, "@/lib/csrf": csrf });
  const origin = "https://cloudforge.example";
  const request = (operation, headers, method = "GET") => new NextRequest(origin + "/api/auth/" + operation, { headers, method });
  const cookies = { host: "cloudforge.example", cookie: "cf_session=valid; cf_csrf=csrf" };
  assert.equal((await GET(request("session", { "x-cloudforge-role": "platform-engineer" }))).status, 401);
  const session = await GET(request("session", { ...cookies, "x-cloudforge-role": "platform-engineer" }));
  assert.equal(session.headers.get("cache-control"), "no-store");
  assert.deepEqual(await session.json(), { authenticated: true, username: "account", role: "sre", email: null, csrfToken: "csrf", expiresAt: 2_000_000_000 });
  assert.equal((await POST(request("logout", { ...cookies, origin }, "POST"))).status, 403);
  assert.equal(revoked, false);
  const logout = await POST(request("logout", { ...cookies, origin, "x-csrf-token": "csrf" }, "POST"));
  assert.equal(logout.status, 200);
  assert.equal(logout.cookies.get("cf_session").maxAge, 0);
  assert.equal(logout.cookies.get("cf_csrf").maxAge, 0);
  assert.equal((await GET(request("session", cookies))).status, 401);
});
