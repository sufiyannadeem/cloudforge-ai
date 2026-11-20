import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import ts from "typescript";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as roles from "../src/lib/role-access.ts";
const require = createRequire(import.meta.url);
function load(path, aliases = {}) {
  const code = ts.transpileModule(readFileSync(new URL(path, import.meta.url), "utf8"), {
    fileName: path, compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX },
  }).outputText;
  const exports = {};
  Function("require", "exports", code)((id) => Object.hasOwn(aliases, id) ? aliases[id] : require(id), exports);
  return exports;
}
test("administration buttons explicitly submit their respective forms", () => {
  const Component = load("../src/components/administration/AccountAdministration.tsx").default;
  const html = renderToStaticMarkup(createElement(Component));
  assert.equal((html.match(/<button type="submit"/g) ?? []).length, 2);
});
test("dashboard errors use locale comparison and retain all failures", async (t) => {
  const { getDashboardData } = load("../src/lib/dashboard-api.ts", {
    "@/lib/service-identity": { serviceAssertion: () => "fixture" },
    "@/lib/server-config": { serviceConfig: Object.fromEntries(["project", "infrastructure", "deployment"].map((key) => [key, "https://fixture.invalid"])) },
    "@/lib/observability-api": {},
    "@/lib/role-access": { dashboardCapabilities: () => ({}) },
  });
  t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 503 }));
  let comparisons = 0;
  const compare = String.prototype.localeCompare;
  t.mock.method(String.prototype, "localeCompare", function (other) { comparisons++; return compare.call(this, other); });
  const data = await getDashboardData({ role: "developer", sub: "fixture" });
  assert.equal(data.errors.length, 3);
  assert.ok(comparisons > 0);
});

test("deduplicated dashboard cards preserve role filtering", () => {
  const Component = load("../src/components/dashboard/PlatformCommandCenter.tsx", {
    "next/link": { default: ({ children, ...props }) => createElement("a", props, children) },
    "@/lib/role-access": roles,
  }).default;
  for (const role of ["developer", "sre", "platform-engineer"]) {
    const html = renderToStaticMarkup(createElement(Component, { role }));
    assert.match(html, /href="\/deployments"/);
    assert.equal(html.includes('href="/administration"'), role === "platform-engineer");
    assert.equal(html.includes('href="/slo"'), role !== "developer");
    assert.equal(html.includes('href="/project-costs"'), role === "developer");
  }
});
