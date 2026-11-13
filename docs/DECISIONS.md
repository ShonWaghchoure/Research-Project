# Architecture & Implementation Decisions

## Phase 0: Walking Skeleton

1. **Python Environment**:
   - Python 3.12 is used via `uv` toolchain to guarantee binary wheel compatibility across data science and web3 packages (numpy, pydantic, web3.py).
   - Database driver: `psycopg` (v3) binary with SQLAlchemy 2.0 compatible URL `postgresql+psycopg://...`. Fallback handling automatically normalizes `postgresql://` to `postgresql+psycopg://` if needed.

2. **Smart Contracts**:
   - Hardhat TypeScript environment with `@nomicfoundation/hardhat-toolbox` and `@openzeppelin/contracts`.
   - `Ping.sol` includes a `ping()` external function emitting a `Pong` event and returning `"pong"`.
   - Deployment script `scripts/deploy.ts` saves contract deployments to `contracts/deployments/<network>.json` with contract address, transaction hash, and ABI.

3. **Backend Health Check**:
   - `GET /health` runs pings against PostgreSQL (via SQLAlchemy `SELECT 1`), Redis (via `redis.ping()`), and queries the latest block number from `CHAIN_RPC_URL` using `web3.py`.
   - Uses `pydantic-settings` to load `.env` configuration.
   - Initial Alembic migration (`0001_initial.py`) is created as an empty baseline migration.

4. **Frontend Architecture**:
   - Next.js 14/15 App Router with TypeScript and Tailwind CSS.
   - Configured with Wagmi and Viem connecting to Hardhat local node (chainId 31337).
   - Dashboard page polls/fetches backend `/health`, displays health metrics (status, postgres ping, redis ping, block number), and connects wallet via Wagmi showing address and balance.

5. **Tooling & Orchestration**:
   - `Makefile` coordinates `dev`, `test`, `lint`, and `reset-db`.
   - `docker-compose.yml` provides containerized PostgreSQL 16 and Redis 7.

## Phase 1: Pricing Engine (SDR)

1. **Units in tests vs production**:
   - Production params use paise/kWh (`p_fit=300`, `p_ret=800`).
   - Phase 1 worked-example tests use the spec's simplified INR/kWh units (`p_fit=3`, `p_ret=8`) with `alpha=1` (no smoothing). The formula is unit-agnostic as long as a call is internally consistent.

2. **Median-cap Sybil resistance**:
   - Spec: `cap_q = c * median(q on that side)`. A naive median over every offer is poisonable by many tiny low-rep identities (they pull the median down and cap honest volume).
   - Decision: compute the median only over positions with `reputation >= rho_min`. Low-rep Sybil offers still enter the weighted supply/demand sum (with `w_i = min(1, R_i/R_ref)`), but cannot rewrite the quantity cap. If no position on a side meets `rho_min`, fall back to the full-side median.

3. **Monotonicity property**:
   - "p_raw non-increasing as supply grows" is checked with `apply_median_cap=False`, so the test isolates the SDR formula. Changing book composition under an active median cap can move the median and is not globally monotonic; that behaviour is covered by the dedicated median-cap tests.

4. **Empty / one-sided markets**:
   - Empty → `p_ref = (p_fit + p_ret) / 2`, `sdr = 1`, `p_raw = midpoint`.
   - Zero demand (supply > 0) → `p_ref = p_fit`.
   - Zero supply (demand > 0) → `p_ref = p_ret`.

5. **`price_impact`**:
   - Returns `p_raw(after) - p_raw(before)` when `delta_kwh` is added to one participant's quantity. Raises `ValueError` if `participant_id` is missing. Uses `prev_p_ref=None` so the metric reflects raw price only.

## Phase 2: Matching and Clearing Engine

1. **QP formulation (vectorized cvxpy)**:
   - Decision variables are a flat non-negative vector over pre-filtered eligible pairs only (not a dense buyer×seller matrix).
   - Eligibility: `a_j <= p_ref <= b_i`, both reputations `>= rho_min`, and `R_j >= r_min_i`.
   - Objective: surplus `(b_i - a_j) + beta * min(R_j, R_cap)` minus `match_lambda * ||y - s||^2` on the long side (sellers if `SDR > 1`, else buyers).
   - Solvers tried in order: Clarabel → OSQP → SCS.

2. **Grid flow model**:
   - Peer trade `x_ij` contributes `pi[line][(buyer, seller)] * x_ij` along the unique radial path seller → buyer.
   - Unmatched buy volume imports from the root (`root → buyer`); unmatched sell volume exports to the root (`seller → root`).
   - Line constraint: `|peer_flow + grid_residual| / dt <= capacity_kw` with `dt = 0.25 h`.
   - Consequence: zero capacity on the path from a node to the root makes any positive offer at that node infeasible (even grid-only residuals); the matcher then returns no peer trades.

3. **Default feeder**:
   - 13-node radial tree (`n0` root/transformer + 12 downstream buses, 12 lines). Fixture helper `default_13_node_feeder`.

4. **Integerization**:
   - Continuous kWh trades are floored to Wh, then a largest-remainder pass awards at most +1 Wh per trade while respecting per-participant quantity caps.
   - After awarding remainders, line loadings are rechecked; if any line exceeds capacity, remainders are stripped in reverse award order until feasible.

5. **Hashing**:
   - `canonical_json`: sorted keys, no spaces.
   - `input_root`: Merkle root (keccak256 pairwise, odd-duplicate) over sorted revealed position records.
   - `result_hash`: keccak256 of canonical JSON `{p_ref, trades[]}` with trades sorted by `(buyer_id, seller_id, qty_wh, price)`.

6. **EV helpers** (`ev.py`):
   - Buy limit `b_i = p_fit + (p_ret - p_fit) * u_i` with `u_i = clip(E_need / (P_max * T_left), 0, 1)`.
   - V2G sell qty `max(0, SOC - E_target)` only when `v2g=True`.
