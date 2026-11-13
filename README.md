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
| **3** | Reputation, defenses, fairness | ✅ **Done** |
| **4** | Simulator and baselines | ✅ **Done** |
| **5** | Smart contracts | ✅ **Done** |
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

## Phase 3 Smoke Test Results

```
pytest tests/reputation/ -v
  86 passed
  - score: worked table (0 -> 0.098, 1 -> 0.276, 2 -> 0.400, 5 -> 0.606, 20 -> 0.856, 50 -> 0.936),
    failure ~3x success, zero-volume adds no evidence, forgetting (Trusted -> lost when
    delivery stops; old failures fade), reveal-miss penalty, pro-rated partial delivery
  - tiers: spec tier rules, volume cap, newcomer cold start (Probation, can trade, reaches
    Trusted in 100 perfect intervals), idle decay never suspends, hysteresis at boundaries
  - shortfall: hand-computed compensation / penalty / pro-rated payment in integer paise
  - sybil: wash-trading pair c_i = 1.0, diversified trader c_i = 0.0, 3-member ring caught by
    Louvain (internal ratio 0.99), IsolationForest outlier, PV plausibility, energy balance
  - fairness: Jain (1, 0.25), Gini (0, 0.75), HHI, small-actor parity, price impact via
    pricing.price_impact, reputation mobility, welfare efficiency, report metrics
  - Hypothesis property tests (R, Jain and Gini always in range; success never lowers R)

ruff check .              →  All checks passed
mypy app                  →  Success: no issues found
```

Built:
- `backend/app/reputation/params.py` — Phase 3 thresholds, read from `core/params.py`
- `backend/app/reputation/score.py` — Beta reputation with forgetting and lower confidence bound
- `backend/app/reputation/tiers.py` — tiers, volume cap, hysteresis, `matching_reputation` hand-off
- `backend/app/reputation/shortfall.py` — compensation, penalty, pro-rated payment (paise)
- `backend/app/reputation/sybil.py` — collusion (PC/RR), Louvain communities, IsolationForest, false-report checks, flags
- `backend/app/reputation/fairness.py` — spec metrics plus report metrics (seller satisfaction,
  bill saving, revenue uplift, surplus split, matching rate, grid trust density, grid-backup frequency)

Tests: `backend/tests/reputation/test_{score,tiers,shortfall,sybil,fairness}.py`

Integration note for Phases 4 and 7: build each `Position` with
`reputation = matching_reputation(state, tier)` and cap `qty_kwh` at `volume_cap_kwh(...)`.
Design decisions and sources: `docs/DECISIONS.md` (Phase 3).

---

## Phase 4 Smoke Test Results

```
python -m app.sim.cli simulate --scenario honest --participants 100 --days 7 --seed 42 --out results/honest_b3
  → finished in ~43 s; intervals / trades / reputation / flags / fairness / participants CSVs,
    summary.json, config.json (git commit), timing.csv
  → buyer bill saving 9.5%, seller revenue uplift 15.2%, 1,728 kWh traded P2P
  → 0 line violations, 67,200 signed meter readings verified, 0 failed
Same seed, two 7-day runs  →  all CSVs byte-identical (timing.csv excluded)

python -m app.sim.cli compare --scenario honest --participants 100 --days 1 --seed 42 --out results/cmp
  mode   buyer bill saving %  seller revenue uplift %  total gain (INR)  line violations
  B0                    0.00                     0.00              0.00                0
  B1                    5.10                    14.44            721.92                0
  B2                    7.50                     3.70            602.42                0
  B3                    7.35                     4.69            618.47                0

pytest tests/sim/ -v
  42 passed
  - models: load shape, clear-sky PV, seeded weather, battery limits,
    EV reserve + departure-target guard (V2G), signed meter tamper detection
  - bots and baselines: each behaviour, B1 fixed price, B2 proportional 3:1
  - runner: identical outputs for the same seed, 100-participant day with no
    line violations, lazy / non-revealer / ring end with lower reputation,
    B1-B3 buyer bills below B0, P2P never overloads a tight feeder,
    every one of the 19 scenarios runs

pytest -v                 →  171 passed    # phases 0-4
ruff check .              →  All checks passed
mypy app                  →  Success: no issues found in 33 source files
```

Built:
- `backend/app/sim/forecast.py` — household load, solar with cloud forecast vs actual, battery, EV
- `backend/app/sim/meters.py` — secp256k1-signed meter readings (deterministic keys)
- `backend/app/sim/bots.py` — honest, lazy, strategic, collusion ring, Sybil, price manipulator,
  false reporter, defector, non-revealer
- `backend/app/sim/baselines.py` — B0 grid only, B1 fixed price first-come, B2 SDR + proportional, B3 full system
- `backend/app/sim/scenarios.py` — 19 scenarios: spec attacks, report S1–S4 / S10, edge-case stress tests
- `backend/app/sim/runner.py` — interval loop, settlement, reputation, detection every 12 intervals, metrics, CSVs
- `backend/app/sim/cli.py` — `simulate`, `compare`, `scenarios`

Tests: `backend/tests/sim/test_{models,runner}.py`

List scenarios with `python -m app.sim.cli scenarios`. Design decisions and findings: `docs/DECISIONS.md` (Phase 4).

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
