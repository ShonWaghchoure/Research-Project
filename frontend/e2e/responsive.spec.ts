import { expect, test } from "@playwright/test";

/**
 * Acceptance: works at 375, 768 and 1440 px.
 * Each page must render without horizontal scroll and without console errors.
 * Screenshots go to test-results/screens/ for review.
 */
const WIDTHS = [375, 768, 1440] as const;
const PAGES = ["/", "/onboarding", "/dashboard", "/trade", "/status", "/market"] as const;

for (const width of WIDTHS) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height: width === 375 ? 812 : 900 } });

    for (const path of PAGES) {
      test(`renders ${path}`, async ({ page }) => {
        const errors: string[] = [];
        page.on("pageerror", (e) => errors.push(e.message));
        page.on("console", (m) => {
          // Browsers log failed WebSocket handshakes during reconnect; those are expected.
          if (m.type() === "error" && !/WebSocket/i.test(m.text())) errors.push(m.text());
        });

        await page.goto(path);
        await expect(page.locator("h1")).toBeVisible();
        await page.waitForLoadState("networkidle").catch(() => undefined);

        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow, "no horizontal scroll").toBeLessThanOrEqual(0);

        const name = path === "/" ? "landing" : path.slice(1);
        await page.screenshot({ path: `test-results/screens/${name}-${width}.png`, fullPage: true });
        expect(errors, "console errors").toEqual([]);
      });
    }
  });
}
