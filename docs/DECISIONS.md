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
