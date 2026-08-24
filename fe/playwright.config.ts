import { defineConfig } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL?.replace(/\/+$/, "");

if (!baseURL) {
  throw new Error("PLAYWRIGHT_BASE_URL is required; do not silently run production-readiness tests against a fixture.");
}

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  reporter: "list",
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
});
