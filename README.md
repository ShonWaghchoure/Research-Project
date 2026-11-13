# Fair and Trustworthy P2P Energy Trading (Smart Grid 2.0)

A web app that runs a simulated 15-minute peer-to-peer energy market:
SDR-based pricing, reputation-gated and grid-aware matching, commit-reveal bidding,
on-chain escrow and settlement, and a manipulation-resistant reputation system.

> **Stack:** Solidity + Hardhat · FastAPI · PostgreSQL · Redis · web3.py · Next.js · wagmi · Tailwind · shadcn/ui

---

## Phase Status

| Phase | Name | Status |
|-------|------|--------|
| **0** | Walking skeleton | ✅ **Done** |
| **1** | Pricing engine (SDR) | ✅ **Done** |
| 2 | Matching and clearing engine | ⬜ Pending |
| 3 | Reputation, defenses, fairness | ⬜ Pending |
| 4 | Simulator and baselines | ⬜ Pending |
| 5 | Smart contracts | ⬜ Pending |
| 6 | Backend foundation | ⬜ Pending |
| 7 | Market lifecycle | ⬜ Pending |
| 8 | Frontend foundation | ⬜ Pending |
| 9 | Frontend market views | ⬜ Pending |
| 10 | Attack lab, audit, admin | ⬜ Pending |
| 11 | Experiments | ⬜ Pending |
| 12 | Hardening, deploy, docs | ⬜ Pending |

---

## Quick Start

```bash
git clone https://github.com/<your-username>/fair-and-trustworthy.git
cd fair-and-trustworthy
cp .env.example .env   # fill in your secrets
make dev               # starts everything — docker, hardhat node, backend, frontend
```

Then open [http://localhost:3000](http://localhost:3000).

---

## Repository Layout

```
fair-and-trustworthy/
├── contracts/                # Solidity (Hardhat 2 + OpenZeppelin 5)
│   ├── contracts/            # .sol source files
│   ├── scripts/deploy.ts     # deploy → contracts/deployments/<network>.json
│   └── test/                 # Hardhat TypeScript tests
├── backend/                  # Python 3.12 (FastAPI)
│   ├── app/
│   │   ├── api/              # Route handlers
│   │   ├── core/             # Config (pydantic-settings) + global params
│   │   ├── db/               # SQLAlchemy models + session
│   │   ├── engine/           # PURE functions: pricing, matching, clearing, hashing
│   │   ├── reputation/       # PURE functions: score, tiers, sybil, fairness
│   │   ├── sim/              # Headless simulator + bots + baselines
│   │   ├── chain/            # web3.py client + nonce manager
│   │   └── workers/          # APScheduler jobs: clock, clearing, poster, meter, reputation
│   ├── alembic/              # DB migrations
│   └── tests/                # pytest (unit + integration)
├── frontend/                 # Next.js 14 App Router + wagmi 2 + Tailwind
│   └── src/app/              # Pages: health dashboard → full market UI
├── docker-compose.yml        # postgres:16-alpine (port 5433) + redis:7-alpine
├── Makefile                  # dev · test · lint · reset-db
├── .env.example              # all required variables
├── .github/workflows/ci.yml  # contracts + backend + frontend on every PR
└── docs/
    ├── DECISIONS.md          # design decision log
    ├── ARCHITECTURE.md       # (Phase 12)
    ├── MATH.md               # (Phase 12)
    └── RESULTS.md            # (Phase 11)
```

---

## Make Targets

```bash
make dev        # docker up → hardhat node → deploy contracts → backend → frontend
make test       # contracts (hardhat) + backend (pytest) + frontend (next build)
make lint       # ruff + mypy + next lint
make reset-db   # wipe volumes, re-migrate
```

---

## Global Parameters

| Symbol | Value | Meaning |
|--------|-------|---------|
| `p_fit` | 300 paise/kWh | Feed-in tariff (floor price) |
| `p_ret` | 800 paise/kWh | Retail tariff (ceiling price) |
| `interval` | 900 s (demo: 30–60 s) | Market interval length |
| `k` | 2 | SDR exponent |
| `alpha` | 0.7 | Price smoothing factor |
| `c` | 3 | Quantity cap multiplier (median) |
| `R_ref` | 0.8 | Reputation weight reference |
| `rho_min` | 0.3 | Minimum reputation to participate |
| `R_cap` | 0.9 | Reputation cap for matching bonus |
| `beta` | ≤ 5% of (p_ret − p_fit) | Matching fairness weight |
| `(w_del, w_rev, w_hon, w_col)` | (0.45, 0.15, 0.20, 0.20) | Reputation score weights |
| `(alpha0, beta0)` | (1, 2) | Beta prior |
| `kappa` | 3 | Failure penalty multiplier |
| `H` | 672 intervals | Forgetting half-life |
| `f` | 0.1 | Shortfall penalty fraction |

---

## Phase 0 Smoke Test Results

```
GET /health
{
  "status": "ok",
  "postgres": "ok",
  "redis": "ok",
  "chain_rpc": "ok",
  "block_number": 0,
  "chain_id": 31337
}

npx hardhat test  →  3 passing (1s)
pytest -v         →  2 passed (3.23s)
ruff check .      →  All checks passed
mypy app          →  Success: no issues found in 14 source files
next build        →  ✓ Compiled successfully, route / = 99.9 kB
```

---

## Phase 1 Smoke Test Results

```
pytest tests/engine/test_pricing.py -v
  17 passed (2.16s)
  - 5 worked SDR→price values (0.25→7.71, 0.5→7.00, 1→5.50, 2→4.00, 4→3.29)
  - edge cases: empty / zero demand / zero supply / smoothing / median cap / reputation
  - 4 Hypothesis property tests × 200 examples each

pytest -v         →  19 passed (5.24s)   # pricing + health
ruff check .      →  All checks passed
mypy app          →  Success: no issues found in 15 source files
```

Built: `backend/app/engine/pricing.py` (`Position`, `PriceResult`, `compute_reference_price`, `price_impact`)
Tests: `backend/tests/engine/test_pricing.py`

---

## Environment Variables

See [`.env.example`](.env.example) for all required variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `CHAIN_RPC_URL` | EVM RPC endpoint (default: Hardhat localhost) |
| `CHAIN_ID` | Chain ID (31337 for local Hardhat) |
| `OPERATOR_PRIVATE_KEY` | Operator wallet private key (testnet only) |
| `JWT_SECRET` | Secret for signing JWTs |
| `INTERVAL_SECONDS` | Market interval length in seconds |
| `PING_CONTRACT_ADDRESS` | Deployed Ping contract address |

---

## Contributing

This project follows the phase-by-phase build plan in [`GEMINI.md`](GEMINI.md).
Each phase is a separate commit. Do not start a phase until the previous one passes all acceptance checks.

> **Note:** Postgres is mapped to host port `5433` (not `5432`) to avoid conflicts with other local services.
