#!/usr/bin/env bash
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== Launching Backend (FastAPI on :8000) & Frontend (Next.js on :3000) ==="

# Cleanup handler on exit
cleanup() {
    echo ""
    echo "Stopping dev servers..."
    if [ -n "$BACKEND_PID" ]; then kill "$BACKEND_PID" 2>/dev/null || true; fi
    if [ -n "$FRONTEND_PID" ]; then kill "$FRONTEND_PID" 2>/dev/null || true; fi
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# Demo defaults (overridable by caller / .env)
export DEMO_MODE="${DEMO_MODE:-1}"
export INTERVAL_SECONDS="${INTERVAL_SECONDS:-45}"
export DEMO_BOT_COUNT="${DEMO_BOT_COUNT:-10}"

# Start backend
(cd "$ROOT_DIR/backend" && exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000) &
BACKEND_PID=$!
echo "Backend running on PID $BACKEND_PID (http://localhost:8000) DEMO_MODE=$DEMO_MODE INTERVAL_SECONDS=$INTERVAL_SECONDS"

# Start frontend
(cd "$ROOT_DIR/frontend" && exec npm run dev) &
FRONTEND_PID=$!
echo "Frontend running on PID $FRONTEND_PID (http://localhost:3000)"

wait
