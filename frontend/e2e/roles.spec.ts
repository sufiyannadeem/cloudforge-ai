import { expect, test, type Page } from "@playwright/test";

const projectName = process.env.E2E_PROJECT_NAME ?? "e2e20-" + process.env.E2E_DEVELOPER_USER;
const roles = [
  ["developer", "My project workspace"],
  ["sre", "Reliability operations"],
  ["platform-engineer", "Platform administration"],
] as const;
async function login(page: Page, role: string) {
  await page.goto("/login");
  await page.getByLabel("Username", { exact: true }).fill(process.env[`E2E_${role.toUpperCase().replace("-", "_")}_USER`]!);
  await page.getByLabel("Password", { exact: true }).fill(process.env.E2E_PASSWORD!);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}
for (const [role, title] of roles) {
  test(`${role} dashboard, navigation, and backend authorization`, async ({ page }) => {
    test.skip(!process.env.E2E_PASSWORD, "Provide local test account credentials");
    await login(page, role);
    await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible({ timeout: 15_000 });
    if (role === "developer") {
      await page.goto("/projects");
      await page.getByRole("button", { name: "+ Create project", exact: true }).click();
      await page.getByLabel("Project name", { exact: true }).fill(projectName);
      await page.getByLabel("Repository URL", { exact: true }).fill("https://example.test/e2e");
      await page.getByRole("button", { name: "Create project", exact: true }).click();
      await expect(page.getByRole("table")).toContainText(projectName);
    }
    if (role !== "platform-engineer") {
      await page.goto("/administration");
      await expect(page.getByRole("heading", { name: "Access denied", exact: true })).toBeVisible();
      const evidenceDenied = await page.request.get("/api/incidents/11111111-1111-4111-8111-111111111111/cost-evidence");
      if (role === "developer") expect(evidenceDenied.status()).toBe(403);
      const denied = await page.request.get("/api/proxy/project/admin/accounts");
      expect(denied.status()).toBe(403);
      const mutation = await page.request.post("/api/proxy/infrastructure/api/v1/resources/11111111-1111-4111-8111-111111111111/apply", { data: {plan_hash:"forged"} });
      expect(mutation.status()).toBe(403);
    } else {
      await page.goto("/administration");
      await expect(page.getByRole("heading", { name: "User management", exact: true })).toBeVisible();
      await expect(page.getByRole("table")).toContainText(process.env.E2E_PLATFORM_ENGINEER_USER!);
      const form = page.getByRole("form", { name: "Manage account" });
      const username = process.env.E2E_PLATFORM_ENGINEER_USER! + "-" + Date.now();
      await form.getByLabel("Username", { exact: true }).fill(username);
      await form.getByLabel("Password for new user").fill(process.env.E2E_PASSWORD!);
      await form.getByRole("button", { name: "Save account change" }).click();
      await expect(page.getByRole("status")).toContainText("Administrative change saved.");
      await expect(page.getByRole("table")).toContainText(username);
      await form.getByLabel(/^Action/).selectOption("set-role");
      await form.getByLabel("Username", { exact: true }).fill(username);
      await form.getByLabel(/^Role/).selectOption("sre");
      await form.getByRole("button", { name: "Save account change" }).click();
      await expect(page.getByRole("table").getByRole("row").filter({ hasText: username })).toContainText("sre");
      const membership = page.getByRole("form", { name: "Manage project membership" });
      await membership.getByLabel(/^Project/).selectOption({ label: projectName + " · Owner " + process.env.E2E_DEVELOPER_USER! });
      await membership.getByLabel(/^Member/).selectOption(username);
      await membership.getByLabel(/^Access/).selectOption("viewer");
      await membership.getByRole("button", { name: "Save membership" }).click();
      await expect(page.getByRole("list", { name: "Project memberships" })).toContainText(username);
      await expect(page.getByRole("heading", { name: "Account audit history" })).toBeVisible();
      const missingCSRF = await page.request.post("/api/proxy/project/admin/accounts", { data: { action: "revoke", username: "forged" } });
      expect(missingCSRF.status()).toBe(403);
    }
    await page.goto("/infrastructure");
    await expect(page.getByText("Unable to load infrastructure", { exact: false })).toHaveCount(0);
    await expect(page.getByRole("main")).toBeVisible();
    const csrf = await page.evaluate(() => decodeURIComponent(document.cookie.split(";").map((x) => x.trim()).find((x) => x.startsWith("cf_csrf="))!.slice(8)));
    const logout = await page.request.post("/api/auth/logout", { headers: { Origin: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3100", "X-CSRF-Token": csrf } });
    expect(logout.ok()).toBeTruthy();
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/login/);
  });
}
test("unsigned direct backend proxy access is denied", async ({ request }) => {
  const response = await request.get("/api/proxy/project/admin/accounts");
  expect(response.status()).toBe(401);
});
