import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./e2e",
  workers: 1,
  timeout: 90_000,
  use: { baseURL: process.env.E2E_BASE_URL ?? "http://127.0.0.1:3100", headless: true },
  reporter: "list",
  outputDir: "/tmp/cloudforge-playwright-results",
});
