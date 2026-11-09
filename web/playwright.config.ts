import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [
    ["list"],
    ["html", { open: "never" }],
    ["json", { outputFile: "test-results/results.json" }],
  ],
  workers: 1,
  use: {
    baseURL: "http://127.0.0.1:13000",
    trace: "retain-on-failure",
    serviceWorkers: "block",
  },
  projects: [
    {
      name: "chromium",
      testIgnore: /performance\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    ...(process.env.PERF_FIXTURE
      ? [
          {
            name: "performance",
            testMatch: /performance\.spec\.ts/,
            timeout: 120_000,
            use: { ...devices["Desktop Chrome"] },
          },
        ]
      : []),
    {
      name: "mobile-chromium",
      testMatch: /(?:accessibility|keyboard)\.spec\.ts/,
      use: { ...devices["Pixel 7"] },
    },
    {
      name: "firefox",
      testMatch: /(?:accessibility|keyboard)\.spec\.ts/,
      use: { ...devices["Desktop Firefox"] },
    },
  ],
  webServer: [
    {
      command: "../.venv/bin/python e2e/serve_sample_api.py",
      env: { PERF_FIXTURE: process.env.PERF_FIXTURE ?? "" },
      url: "http://127.0.0.1:18000/api/metrics",
      reuseExistingServer: false,
      timeout: 300_000,
      gracefulShutdown: { signal: "SIGINT", timeout: 5_000 },
    },
    {
      command: "pnpm start --hostname 127.0.0.1 --port 13000",
      url: "http://127.0.0.1:13000",
      env: { FLASK_API_URL: "http://127.0.0.1:18000" },
      reuseExistingServer: false,
      timeout: 120_000,
      gracefulShutdown: { signal: "SIGTERM", timeout: 5_000 },
    },
  ],
});
