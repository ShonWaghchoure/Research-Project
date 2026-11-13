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
