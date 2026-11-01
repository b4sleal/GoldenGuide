import { defineConfig, devices } from "@playwright/test";

// Smoke test of the production build in a real browser. The API is mocked per test (page.route),
// so it needs no backend, database or LLM.
const PORT = 4173;

export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  use: { baseURL: `http://localhost:${PORT}`, trace: "retain-on-failure" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"] } },
    { name: "phone", use: { ...devices["Pixel 7"] } },
  ],
  webServer: {
    // Playwright starts a separate shell; pnpm shims may be unavailable even when launched via Corepack.
    command: `corepack pnpm build && corepack pnpm preview --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
