import assert from "node:assert/strict";
import test from "node:test";
import {
  canAccessPage, canExecuteTerraform, canWriteProject, dashboardCapabilities,
  dashboardDestination, dashboardProfiles, navigationFor, pageDecision, selectAuthorizedProject,
} from "../src/lib/role-access.ts";

test("verified roles resolve distinct dashboards and only authorized navigation", () => {
  const roles = ["platform-engineer", "sre", "developer"];
  assert.equal(new Set(roles.map((role) => dashboardProfiles[role].title)).size, 3);
  for (const role of roles) {
    assert.equal(dashboardDestination(role, "/dashboard"), "/dashboard");
    assert.ok(navigationFor(role).every(({ items }) => items.every(({ href }) => canAccessPage(role, href))));
  }
  const links = (role) => navigationFor(role).flatMap(({ items }) => items.map(({ href }) => href));
  assert.ok(links("platform-engineer").includes("/administration"));
  assert.ok(links("sre").includes("/slo"));
  assert.ok(links("developer").includes("/project-costs"));
  assert.ok(!links("developer").includes("/finops"));
  assert.ok(!links("sre").includes("/administration"));
});

test("direct protected navigation and login destinations fail closed", () => {
  assert.equal(pageDecision(null, "/dashboard"), "sign-in");
  assert.equal(pageDecision("developer", "/administration"), "deny");
  assert.equal(pageDecision("developer", "/administration/users"), "deny");
  assert.equal(pageDecision("developer", "/incidents/id"), "deny");
  assert.equal(pageDecision("developer", "/observability"), "allow");
  assert.equal(dashboardDestination("developer", "/finops?region=one"), "/dashboard");
  assert.equal(dashboardDestination("developer", "/projects?create=1"), "/projects?create=1");
  assert.equal(pageDecision("platform-engineer", "/administration"), "allow");
});

test("developer metrics use scoped views and project selection rejects foreign IDs", () => {
  assert.deepEqual(dashboardCapabilities("developer"), {
    platformTelemetry: false, accountCosts: false, approvalQueue: false, administration: false,
  });
  assert.equal(dashboardCapabilities("sre").platformTelemetry, true);
  assert.equal(dashboardCapabilities("sre").approvalQueue, false);
  assert.equal(dashboardCapabilities("platform-engineer").approvalQueue, true);
  const projects = [{ id: "mine" }];
  assert.equal(selectAuthorizedProject(projects, "someone-elses"), undefined);
  assert.equal(selectAuthorizedProject(projects, "mine"), projects[0]);
});

test("Terraform execution and project mutations use separate permissions", () => {
  assert.equal(canExecuteTerraform("platform-engineer"), true);
  assert.equal(canExecuteTerraform("sre"), false);
  assert.equal(canExecuteTerraform("developer"), false);
  assert.equal(canExecuteTerraform(undefined), false);
  assert.equal(canWriteProject("developer", "viewer"), false);
  assert.equal(canWriteProject("developer", "maintainer"), true);
  assert.equal(canWriteProject("sre", "maintainer"), true);
  assert.equal(canWriteProject("sre", undefined), false);
});
