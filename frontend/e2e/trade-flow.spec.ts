import { expect, test } from "@playwright/test";

/**
 * connect → onboard → submit a position → see the trade appear.
 * Uses demo account 2 so it does not collide with seeded accounts used elsewhere.
 * Needs a local Hardhat node with fresh contracts deployed.
 */
test("a participant can onboard, commit, reveal and see the trade", async ({ page }) => {
  // Any page error or hydration warning anywhere in the flow fails the test.
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", (m) => {
    if (m.type() === "error" && !/WebSocket/i.test(m.text())) errors.push(m.text());
  });

  await page.goto("/onboarding");

  // 1. Connect
  await page.getByTestId("demo-1").click();

  // 2. Sign in
  await page.getByTestId("siwe").click();

  // 3. Profile
  await page.getByTestId("display-name").fill("E2E house");
  await page.getByTestId("save-profile").click();

  // 4–5. Faucet, then stake + register. Onboarding skips steps already done on chain
  // (e.g. when this account was registered by an earlier run), so drive whichever
  // step is showing until the wizard reports completion.
  const faucet = page.getByTestId("faucet");
  const register = page.getByTestId("register");
  const done = page.getByTestId("go-trade");
  for (let i = 0; i < 4 && !(await done.isVisible()); i++) {
    await expect(faucet.or(register).or(done)).toBeVisible({ timeout: 30_000 });
    if (await faucet.isVisible()) await faucet.click();
    else if (await register.isVisible()) await register.click();
    await expect(faucet).toBeHidden({ timeout: 60_000 });
  }
  await expect(page.getByText("You are set up")).toBeVisible({ timeout: 60_000 });

  // Trade
  await page.getByTestId("go-trade").click();
  await expect(page.getByRole("heading", { name: "New position" })).toBeVisible();

  // Sell needs no escrow; limit at the feed-in floor so it always clears.
  await page.getByRole("radio", { name: /sell/i }).check({ force: true });
  await page.getByLabel(/quantity/i).fill("1.5");
  await page.getByLabel(/minimum price/i).fill("3");

  const submit = page.getByTestId("submit-position");
  await expect(submit).toBeEnabled({ timeout: 60_000 }); // waits for the COMMIT window
  await submit.click();

  await expect(page.getByText("Confirmed on chain")).toBeVisible({ timeout: 30_000 });
  // Reveal happens automatically when the window opens.
  await expect(page.getByText(/Revealed and verified/)).toBeVisible({ timeout: 60_000 });

  // Trade appears after clearing.
  await expect(page.getByTestId("trade-row").first()).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTestId("trade-row").first()).toContainText("1.5");

  // A full reload keeps the wallet connection and the signed-in session.
  await page.goto("/dashboard");
  await expect(page.getByText("Your last trades")).toBeVisible();
  await expect(page.getByRole("button", { name: "Disconnect wallet" })).toBeVisible();
  await expect(page.getByTestId("trade-row").first()).toBeVisible();

  // Disconnecting survives a reload too: no silent auto-connect.
  await page.getByRole("button", { name: "Disconnect wallet" }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "Connect" })).toBeVisible();

  expect(errors, "page errors or hydration warnings").toEqual([]);
});
