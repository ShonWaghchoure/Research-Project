import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end: connect → onboard → submit a position → see the trade.
 * Needs a local Hardhat node with contracts deployed (make dev does this, or:
 *   cd contracts && npx hardhat node & npx hardhat run scripts/deploy.ts --network localhost).
 * The mock Phase 7 API and the Next dev server are started here.
 */
const MOCK_PORT = 8001;

export default defineConfig({
  testDir: "./e2e",
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `MOCK_DEV_LOGIN=1 MOCK_INTERVAL_SECONDS=60 PORT=${MOCK_PORT} node mock/server.mjs`,
      url: `http://localhost:${MOCK_PORT}/health`,
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: `NEXT_PUBLIC_API_URL=http://localhost:${MOCK_PORT} npm run dev`,
      url: "http://localhost:3000",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
