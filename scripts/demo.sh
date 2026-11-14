#!/usr/bin/env bash
# One-click local demo: reset DB, seed 20 Hardhat participants, deploy contracts,
# start bots on a 30–60s interval, open the app.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

INTERVAL_SECONDS="${INTERVAL_SECONDS:-45}"
DEMO_BOT_COUNT="${DEMO_BOT_COUNT:-20}"
DEMO_MODE="${DEMO_MODE:-1}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"

echo "=== Fair & Trustworthy — demo ==="
echo "INTERVAL_SECONDS=$INTERVAL_SECONDS DEMO_BOT_COUNT=$DEMO_BOT_COUNT"

if [ ! -f .env ]; then
  echo "Creating .env from .env.example…"
  cp .env.example .env
fi

# Ensure frontend env points at the live API (not the mock).
if [ ! -f frontend/.env.local ]; then
  cat > frontend/.env.local <<'EOF'
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_CHAIN_ID=31337
NEXT_PUBLIC_RPC_URL=http://127.0.0.1:8545
EOF
  echo "Wrote frontend/.env.local"
fi

echo "→ docker compose up (postgres + redis)"
docker compose up -d postgres redis

echo "→ waiting for postgres + redis…"
for i in $(seq 1 40); do
  if docker compose exec -T postgres pg_isready -U postgres -d energy_trading >/dev/null 2>&1 \
     && docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; then
    break
  fi
  sleep 1
done

# Stop any previous Hardhat / API / Next on demo ports.
pkill -f "hardhat node" 2>/dev/null || true
pkill -f "uvicorn app.main:app" 2>/dev/null || true
# Leave other next processes alone if possible; free :3000/:8000/:8545.
for port in 3000 8000 8545; do
  pids=$(lsof -ti tcp:$port 2>/dev/null || true)
  if [ -n "${pids:-}" ]; then
    echo "→ freeing :$port ($pids)"
    kill $pids 2>/dev/null || true
  fi
done
sleep 1

echo "→ Hardhat node"
mkdir -p "$ROOT_DIR/.demo"
(cd "$ROOT_DIR/contracts" && npx hardhat node > "$ROOT_DIR/.demo/hardhat.log" 2>&1) &
HARDHAT_PID=$!
echo "$HARDHAT_PID" > "$ROOT_DIR/.demo/hardhat.pid"

echo "→ waiting for chain RPC…"
for i in $(seq 1 60); do
  if curl -sf -X POST -H 'Content-Type: application/json' \
      --data '{"jsonrpc":"2.0","method":"eth_chainId","params":[],"id":1}' \
      http://127.0.0.1:8545 >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

echo "→ deploy contracts"
(cd "$ROOT_DIR/contracts" && npx hardhat run scripts/deploy.ts --network localhost)

# Keep frontend ABIs/addresses in sync with the fresh deploy.
if [ -f contracts/deployments/localhost.json ]; then
  cp contracts/deployments/localhost.json frontend/src/contracts/localhost.json
  echo "→ synced frontend/src/contracts/localhost.json"
fi

echo "→ migrate + reset market state (fresh Hardhat ≠ old idempotency rows)"
(cd "$ROOT_DIR/backend" && .venv/bin/alembic upgrade head)
(cd "$ROOT_DIR/backend" && .venv/bin/python -m app.db.reset_market)
echo "→ seed (20 pre-funded Hardhat wallets)"
(cd "$ROOT_DIR/backend" && .venv/bin/python -m app.db.seed)

echo "→ starting API + Next.js (demo bots)"
export DEMO_MODE INTERVAL_SECONDS DEMO_BOT_COUNT
bash "$ROOT_DIR/scripts/run-dev.sh" &
DEV_PID=$!
echo "$DEV_PID" > "$ROOT_DIR/.demo/dev.pid"

echo "→ waiting for /health…"
ok=0
for i in $(seq 1 90); do
  body=$(curl -sf http://127.0.0.1:8000/health 2>/dev/null || true)
  if echo "$body" | grep -q '"postgres":"ok"' && echo "$body" | grep -q '"redis":"ok"'; then
    ok=1
    echo "$body"
    break
  fi
  sleep 1
done
if [ "$ok" != "1" ]; then
  echo "Backend health check failed; see terminal / .demo/hardhat.log" >&2
  exit 1
fi

for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000 2>/dev/null || echo 000)
  if [ "$code" = "200" ] || [ "$code" = "304" ]; then
    break
  fi
  sleep 1
done

echo ""
echo "Demo ready:"
echo "  App:     http://localhost:3000"
echo "  API:     http://localhost:8000/docs"
echo "  Health:  http://localhost:8000/health"
echo "  Wallet:  use Demo wallet #1–#3 (Hardhat unlocked) or MetaMask on localhost:8545"
echo "  Admin:   Hardhat account #0 (0xf39F…2266)"
echo "  Script:  docs/DEMO.md"
echo ""

if [ "$OPEN_BROWSER" = "1" ]; then
  if command -v open >/dev/null 2>&1; then
    open "http://localhost:3000" || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://localhost:3000" || true
  fi
fi

wait "$DEV_PID"
