# Demo script (≈ 10 minutes)

Prerequisites: `make demo` (or `make dev`) already running. Browser at
http://localhost:3000. Use a **Demo wallet** (#1–#3) from the connect menu, or
MetaMask on Hardhat (`http://127.0.0.1:8545`, chain id `31337`) with a pre-funded
key from `backend/app/db/hardhat_accounts.py` (**local only**).

Admin UI needs Hardhat account **#0** (`0xf39F…2266`).

---

## 1. Landing and live price (1 min)

1. Open `/` — brand + enter the app.
2. Open `/dashboard` or `/market` — live \(p_{\mathrm{ref}}\), SDR, recent trades.
3. Confirm `/status` shows postgres, redis, and chain RPC healthy.

## 2. Onboard a prosumer (1–2 min)

1. Connect Demo wallet #2 (participant).
2. Go to `/onboarding` — register type **prosumer**, pick a feeder node, set PV/battery if prompted.
3. SIWE login should issue a JWT (sessionStorage).

## 3. Submit a position through the interval (3 min)

1. Open `/trade`.
2. Wait until the interval is in **COMMIT** (dashboard / trade header).
3. Choose buy or sell, quantity, submit **commit** (escrow / MockINR faucet if needed).
4. When **REVEAL** opens, reveal the same position.
5. Watch **CLEARING → SETTLED**: trades appear; explorer / tx hash on trade detail when posted.
6. Optional: copy interval id for the audit step.

## 4. Market and grid (1 min)

1. `/market` — price band, depth, trades feed.
2. `/grid` — 13-node feeder; click a node; note line loadings after clearing.

## 5. Reputation and proof (1 min)

1. `/reputation` — your score, components, tier ladder.
2. Run **ProofVerifier**: fetch proof → `ReputationAnchor.verifyScore` on-chain (true when anchored).

## 6. Attack lab (1–2 min)

1. Connect as **admin** (account #0) or use admin JWT.
2. `/attack` — scenario **Sybil farm**.
3. Run with defenses **off**, note attacker profit meter.
4. Run with defenses **on** — profit should collapse / shrink.
5. (Optional) `/admin` — flag queue, sim speed, config.

## 7. Audit re-run (1 min)

1. `/audit` — enter a cleared interval id (from market or status).
2. Compare stored vs recomputed hashes.
3. As operator/admin, **Re-run** — hashes should match for an honest clearing.

## 8. Results and limitations (1 min)

1. Skim [`RESULTS.md`](RESULTS.md) figure table (simulation findings).
2. State limitations: simulated meters, DC-style grid, trusted-but-verifiable operator,
   parameters tuned in simulation — not a field trial.

---

## Demo wallet cheat-sheet

| Role | Account | Address (prefix) |
|------|---------|------------------|
| Admin / operator key on chain | #0 | `0xf39F…2266` |
| Operator user (seeded) | #1 | `0x7099…79C8` |
| Participant demos | #2–#19 | Hardhat defaults |

Faucet: MockINR `faucet()` from the trade / onboarding flow when balances are low.

## If something is stuck

- `/health` degraded → check Docker postgres/redis and Hardhat log (`.demo/hardhat.log`).
- No intervals → `DEMO_MODE=1` and scheduler running on the API process.
- Wrong contracts → re-run deploy and `npm run sync-contracts` in `frontend/`.
