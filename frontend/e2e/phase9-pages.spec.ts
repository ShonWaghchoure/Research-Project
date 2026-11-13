import { expect, test } from "@playwright/test";

/**
 * Phase 9 acceptance: every market-view page loads without console errors.
 * Proof verification is covered when a Hardhat node is reachable; otherwise the
 * page still renders the verifier idle state cleanly.
 */
const PAGES = [
  { path: "/market", title: "Market" },
  { path: "/grid", title: "Grid map" },
  { path: "/reputation", title: "Reputation" },
  { path: "/fairness", title: "Fairness lab" },
] as const;

test.describe("Phase 9 market views", () => {
  for (const { path, title } of PAGES) {
    test(`visits ${path} without console errors`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", (e) => errors.push(e.message));
      page.on("console", (m) => {
        if (m.type() === "error" && !/WebSocket/i.test(m.text())) errors.push(m.text());
      });

      await page.goto(path);
      await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
      await page.waitForLoadState("networkidle").catch(() => undefined);

      // Charts / map should mount without throwing.
      if (path === "/market") {
        await expect(page.getByText(/Price against the tariff band/i)).toBeVisible();
        await expect(page.getByText(/Trades feed/i)).toBeVisible();
      }
      if (path === "/grid") {
        await expect(page.getByRole("img", { name: /feeder tree/i })).toBeVisible();
      }
      if (path === "/fairness") {
        await expect(page.getByRole("heading", { name: "Jain index" })).toBeVisible();
        await expect(page.getByText(/Baselines over time/i)).toBeVisible();
      }
      if (path === "/reputation") {
        await expect(page.getByText(/Connect a wallet/i)).toBeVisible();
      }

      expect(errors, "console errors").toEqual([]);
    });
  }
});
