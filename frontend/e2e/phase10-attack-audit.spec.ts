import { expect, test } from "@playwright/test";

const MOCK_API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8001";

const DEMO_WALLET = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"; // demo-0

/**
 * The admin UI only trusts a session that belongs to the connected wallet, so connect the
 * demo wallet first, then attach an admin session for that same address and reload.
 * (A token alone, with no wallet, is rejected by the session guard.)
 */
async function signInAsAdmin(page: import("@playwright/test").Page, path: string) {
  await page.goto(path);
  await page.getByRole("button", { name: "Connect" }).click();
  await page.getByTestId("demo-0").click();
  await expect(page.getByRole("button", { name: "Disconnect wallet" })).toBeVisible();

  const res = await fetch(`${MOCK_API}/auth/dev-login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role: "admin", address: DEMO_WALLET }),
  });
  expect(res.ok).toBeTruthy();
  const tok = (await res.json()) as { access_token: string; role: string; address: string };
  await page.evaluate((session) => {
    sessionStorage.setItem(
      "ftp2p.session",
      JSON.stringify({
        state: {
          token: session.access_token,
          address: session.address,
          role: session.role,
          me: { user_id: 1, address: session.address, role: session.role, participant: null },
        },
        version: 0,
      }),
    );
  }, tok);
  await page.reload();
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
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));

    await signInAsAdmin(page, "/attack");
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

  test("an admin token without the matching wallet connected is not trusted", async ({ page }) => {
    // Session for the admin address, but no wallet connected: the guard drops it.
    const res = await fetch(`${MOCK_API}/auth/dev-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: "admin" }),
    });
    const tok = (await res.json()) as { access_token: string; role: string; address: string };
    await page.addInitScript((session) => {
      sessionStorage.setItem(
        "ftp2p.session",
        JSON.stringify({ state: { token: session.access_token, address: session.address, role: session.role, me: null }, version: 0 }),
      );
    }, tok);
    await page.goto("/admin");
    await expect(page.getByText(/Sign in with an admin wallet/i)).toBeVisible();
    await expect(page.getByText(/Market parameters/i)).toHaveCount(0);
  });

  test("non-admin cannot use admin console APIs via UI", async ({ page }) => {
    await page.goto("/admin");
    await expect(page.getByRole("heading", { level: 1, name: "Admin" })).toBeVisible();
    await expect(page.getByText(/Sign in with an admin wallet/i)).toBeVisible();
    await expect(page.getByText(/Market parameters/i)).toHaveCount(0);
  });
});
