# Deployment

**Default for demos and development:** local Hardhat + Docker Postgres/Redis +
`make demo`. Sepolia and hosted frontends are optional.

## Environment variables

Copy `.env.example` → `.env` and `frontend/.env.example` → `frontend/.env.local`.

| Variable | Where | Notes |
|----------|-------|-------|
| `DATABASE_URL` | backend | Postgres (`localhost:5433` in compose) |
| `REDIS_URL` | backend | Redis |
| `CHAIN_RPC_URL` / `CHAIN_ID` | backend | `http://127.0.0.1:8545` / `31337` local |
| `OPERATOR_PRIVATE_KEY` | backend / Hardhat | **Never** commit real keys; Hardhat #0 only for local |
| `JWT_SECRET` | backend | Random, 32+ chars. The backend **refuses to start** off the local chain with the public default |
| `SIWE_DOMAIN` / `SIWE_URI` | backend | The frontend's host (e.g. `app.example.com` / `https://app.example.com`). Sign-in messages for any other site are rejected. Must not be `localhost` off the local chain |
| `ADMIN_ADDRESSES` / `OPERATOR_ADDRESSES` | backend seed | Your own wallets. Off the local chain the seed creates **only** these privileged users; Hardhat demo accounts (public keys) are never seeded |
| `CORS_ORIGINS` | backend | Comma list in production (e.g. `https://app.example.com`); `*` for local |
| `INTERVAL_SECONDS` | backend | `45` demo, `900` production-like |
| `DEMO_MODE` / `DEMO_BOT_COUNT` | backend | `1` / `20` for demo |
| `NEXT_PUBLIC_API_URL` | frontend | Backend origin |
| `NEXT_PUBLIC_RPC_URL` / `NEXT_PUBLIC_CHAIN_ID` | frontend | Wallet RPC |
| `SEPOLIA_RPC_URL` | contracts | Only for Sepolia deploy |

Contract addresses auto-load from `contracts/deployments/<network>.json` when env slots are empty.

## Local (recommended)

```bash
cp .env.example .env
make demo          # compose + Hardhat + deploy + seed + API + UI + browser
# or: make dev
```

Open http://localhost:3000. Stop with Ctrl+C; `docker compose down` if desired.

## Docker images

```bash
# Backend
docker build -t ft-backend ./backend
docker run --rm -p 8000:8000 --env-file .env ft-backend

# Frontend (bake public API URL at build time)
docker build -t ft-frontend ./frontend \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  --build-arg NEXT_PUBLIC_CHAIN_ID=11155111 \
  --build-arg NEXT_PUBLIC_RPC_URL=https://rpc.example.com \
  --build-arg NEXT_PUBLIC_MOCK_INR_ADDRESS=0x... \
  --build-arg NEXT_PUBLIC_REGISTRY_ADDRESS=0x... \
  --build-arg NEXT_PUBLIC_SETTLEMENT_ADDRESS=0x... \
  --build-arg NEXT_PUBLIC_REPUTATION_ANCHOR_ADDRESS=0x...
# Off the local chain the four addresses are required (the build fails without them).
# Demo wallets stay off in production builds unless NEXT_PUBLIC_ENABLE_DEMO_WALLET=true,
# which is only for a private local demo.
docker run --rm -p 3000:3000 ft-frontend
```

Compose today runs **postgres + redis** (+ optional Hardhat profile `test`). App
containers are built as above for VM/Railway-style hosts.

## Frontend on Vercel

1. Import the repo; set **Root Directory** to `frontend`.
2. Env: `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_CHAIN_ID`, `NEXT_PUBLIC_RPC_URL`,
   optional contract address overrides.
3. Build: `npm run build` (uses `output: "standalone"` locally for Docker; Vercel uses default Next build).
4. Point CORS on the API to the Vercel origin via `CORS_ORIGINS`.

## Backend + Postgres + Redis (VM / Render / Railway)

1. Provision Postgres 16 and Redis 7; set `DATABASE_URL` / `REDIS_URL`.
2. Run a chain RPC (hosted Hardhat is uncommon — use Sepolia RPC or your own node).
3. Deploy contracts; set addresses or ship `deployments/*.json`.
4. Set `OPERATOR_PRIVATE_KEY` (secret store), `JWT_SECRET`, `CORS_ORIGINS`, `DEMO_MODE=0` for production.
5. Start: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000`.
6. Optionally disable docs in production and tighten rate limits.

## Sepolia

```bash
cd contracts
export SEPOLIA_RPC_URL=https://...
export OPERATOR_PRIVATE_KEY=0x...   # funded test key only
npm run deploy:sepolia
# Write addresses into deployments/sepolia.json (script does this)
# Verify on https://sepolia.etherscan.io
```

Update backend `CHAIN_ID=11155111` and set the frontend's `NEXT_PUBLIC_CHAIN_ID=11155111` plus
`NEXT_PUBLIC_MOCK_INR_ADDRESS`, `NEXT_PUBLIC_REGISTRY_ADDRESS`, `NEXT_PUBLIC_SETTLEMENT_ADDRESS` and
`NEXT_PUBLIC_REPUTATION_ANCHOR_ADDRESS` from `deployments/sepolia.json`. Then seed with your own wallets:
`ADMIN_ADDRESSES=0x... OPERATOR_ADDRESSES=0x... python -m app.db.seed`.
**Localhost remains the supported one-click demo path.**

## Security checklist before public deploy

- [ ] Rotate `JWT_SECRET` and operator key; never use Hardhat keys on public nets (the backend refuses to start otherwise)  
- [ ] Set `SIWE_DOMAIN` / `SIWE_URI` to the frontend's site  
- [ ] Seed admin/operator from `ADMIN_ADDRESSES` / `OPERATOR_ADDRESSES` (never Hardhat accounts)  
- [ ] Set all four `NEXT_PUBLIC_*_ADDRESS` variables; leave demo wallets disabled  
- [ ] Do not expose Postgres, Redis or the Hardhat node publicly (compose binds them to 127.0.0.1)  
- [ ] Never run `frontend/mock/server.mjs` publicly (local test tool; `/auth/dev-login` only with `MOCK_DEV_LOGIN=1`)  
- [ ] Set explicit `CORS_ORIGINS`  
- [ ] `DEMO_MODE=0`  
- [ ] Run `bash scripts/security-pass.sh` and review CI secret scan  
- [ ] Confirm frontend `src/` has no private keys  
