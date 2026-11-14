import { expect, test } from "@playwright/test";

const MOCK_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

async function injectAdminSession(page: import("@playwright/test").Page) {
  const res = await fetch(`${MOCK_API}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role: "admin" }),
  });
  expect(res.ok).toBeTruthy();
  const tok = (await res.json()) as {
    access_token: string;
    role: string;
    address: string;
  };

  await page.addInitScript((session) => {
    sessionStorage.setItem(
      "ftp2p.session",
      JSON.stringify({
        state: {
          token: session.access_token,
          address: session.address,
          role: session.role,
          me: {
            user_id: 1,
            address: session.address,
            role: session.role,
            participant: null,
          },
        },
        version: 0,
      }),
    );
  }, tok);
}

test.describe("Phase 10 attack lab and audit", () => {
  test("opens audit page and loads a report", async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await page.goto("/audit");
    await expect(page.getByRole("heading", { level: 1, name: "Audit" })).toBeVisible();

    const health = (await (await fetch(`${MOCK_API}/health`)).json()) as {
      demo_audit_interval_id?: number;
    };
    const intervalId = health.demo_audit_interval_id;
    expect(intervalId).toBeTruthy();

    await page.getByLabel(/Interval id/i).fill(String(intervalId));
    await page.getByRole("button", { name: /Load report/i }).click();
    await expect(page.getByRole("heading", { name: "Input root" })).toBeVisible();
    await expect(page.getByText(/Merkle leaves/i)).toBeVisible();
    await expect(page.getByText(/Block explorer/i)).toBeVisible();
    expect(errors, "console errors").toEqual([]);
  });

  test("admin can run an attack scenario", async ({ page }) => {
    await injectAdminSession(page);

    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await page.goto("/attack");
    await expect(page.getByRole("heading", { level: 1, name: "Attack lab" })).toBeVisible();
    await expect(page.getByRole("radio", { name: /Sybil farm/i })).toBeVisible();

    await page.getByRole("button", { name: /Run off then on/i }).click();
    await expect(page.getByText(/Defenses off — attacker-group gain/i)).toBeVisible({
      timeout: 60_000,
    });
    // Profit bars fill after both mock runs return.
    await expect(page.getByText("48000 paise", { exact: true })).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText("1200 paise", { exact: true })).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText(/Off:.*defenses off/i)).toBeVisible();
    await expect(page.getByText(/On:.*defenses on/i)).toBeVisible();

    expect(errors, "console errors").toEqual([]);
  });

  test("non-admin cannot use admin console APIs via UI", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.getByRole("heading", { level: 1, name: "Admin" })).toBeVisible();
    await expect(page.getByText(/Sign in with an admin wallet/i)).toBeVisible();
    await expect(page.getByText(/Market parameters/i)).toHaveCount(0);
  });
});
