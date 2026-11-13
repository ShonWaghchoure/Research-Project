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
| **2** | Matching and clearing engine | ✅ **Done** |
| 3 | Reputation, defenses, fairness | ⬜ Pending |
| 4 | Simulator and baselines | ⬜ Pending |
| **5** | Smart contracts | ✅ **Done** |
| **6** | Backend foundation | ✅ **Done** |
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
make reset-db   # wipe volumes, re-migrate, seed demo participants
make gen-api    # OpenAPI → frontend/src/api/schema.d.ts
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

## Phase 2 Smoke Test Results

```
pytest tests/engine/ -v
  41 passed
  - grid: 13-node feeder, path(), pi matrix
  - matching/clearing: qty caps, p_ref clearing, zero-capacity block,
    unconstrained equivalence, ~3:1 proportional share, rho_min gate,
    EV urgency, deterministic hashes, line loadings within capacity
  - benchmark: n=50 ~0.06s, n=100 ~0.20s, n=200 ~0.91s
  - hashing: canonical JSON, order-invariant input_root / result_hash
  - EV: urgency clips, V2G sell qty

pytest -v                 →  43 passed (~9s)    # pricing + clearing + health
ruff check .              →  All checks passed
mypy app                  →  Success: no issues found in 20 source files
Hash determinism          →  identical across two local runs
Docker hash identity      →  match_local_expected True (linux/amd64)
```

Built:
- `backend/app/engine/grid.py` — radial feeder, `path`, `build_pi_matrix`, 13-node fixture
- `backend/app/engine/matching.py` — vectorized cvxpy QP (Clarabel/OSQP/SCS)
- `backend/app/engine/clearing.py` — `clear_interval` (price → match → Wh repair → hash)
- `backend/app/engine/hashing.py` — canonical JSON, keccak256, Merkle `input_root`, `result_hash`
- `backend/app/engine/ev.py` — urgency limit price + V2G sell qty

Tests: `backend/tests/engine/test_{grid,matching via clearing,clearing,hashing,ev}.py`

---

## Phase 5 Smoke Test Results

```
npx hardhat test
  26 passed
  - MockINR: 2 decimals, daily faucet
  - Registry: stake/register uniqueness, cooldown withdraw,
    slash-only-by-settlement, operator suspend, admin params
  - Settlement: open/commit/deposit/postClearing/settleBatch,
    escrow shortfall, never-reveal, double-settle, pause, payment floor
  - ReputationAnchor: postRoot + Merkle verifyScore
  - Scenarios: full 10-participant interval + settle + reputation root
  - Ping (Phase 0) still green

npx hardhat coverage     →  stmts 100% / lines 100%  (branch ~68%; >90% stmts/lines)
REPORT_GAS=true hardhat test → gas report OK (settleBatch avg ~161k)
npx hardhat run scripts/deploy.ts --network hardhat
  → writes contracts/deployments/localhost.json
    (MockINR, Registry, ReputationAnchor, Settlement, Ping)
Slither                 → not available (install needs Rust/cbor2 wheel)
```

Built:
- `contracts/contracts/MockINR.sol`
- `contracts/contracts/Registry.sol`
- `contracts/contracts/Settlement.sol`
- `contracts/contracts/ReputationAnchor.sol`
- `contracts/scripts/deploy.ts` — deploy order + role wiring + JSON export

Tests: `contracts/test/{MockINR,Registry,Settlement,ReputationAnchor,Scenarios,Ping}.ts`

---

## Phase 6 Smoke Test Results

```
pytest -v
  134 passed (~42s)
  - api: SIWE nonce/verify JWT, role gates, participant create/patch/validation,
    admin config GET/PUT + audit_log
  - engine + reputation suites still green
  - health: postgres/redis/chain probes

ruff check .              →  All checks passed
mypy app                  →  Success: no issues found in 41 source files

Acceptance
  python scripts/siwe_login.py --account-index 1
    → ok:true, JWT issued, GET /me returns Hardhat demo participant
  Non-admin GET /admin/config
    → HTTP 403 {"detail":"insufficient role"}
  Admin GET /admin/config
    → HTTP 200 (MarketParams keys from config table)
  make reset-db
    → migrate + seed: 13 feeder_nodes, 12 lines, 20 users, 20 participants, 24 config
      roles: 1 admin, 1 operator, 18 participant
  make gen-api
    → frontend/src/api/schema.d.ts (openapi-typescript 7.13.0)
```

Built:
- `backend/app/db/models.py` — SQLAlchemy 2 models (users → audit_log / transactions)
- `backend/alembic/versions/364439bcf300_phase6_backend_foundation.py`
- `backend/app/api/{auth,participants,admin}.py` — SIWE JWT, /me, profiles, config + audit
- `backend/app/core/{security,config_store,limiter,logging}.py`
- `backend/app/db/seed.py` — feeder fixture + 20 Hardhat wallets + default config
- `backend/scripts/siwe_login.py`, `backend/scripts/gen_ts_client.sh`
- `frontend/src/api/schema.d.ts` — generated OpenAPI types

Tests: `backend/tests/api/test_{auth,participants,admin_config}.py`

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
