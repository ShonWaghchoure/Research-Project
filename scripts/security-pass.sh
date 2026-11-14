#!/usr/bin/env bash
# Phase 12 security pass: dependency audits + optional Slither.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
FAIL=0

echo "══ npm audit (contracts) ══"
(cd contracts && npm audit --audit-level=high) || FAIL=1

echo "══ npm audit (frontend) ══"
(cd frontend && npm audit --audit-level=high) || FAIL=1

echo "══ pip-audit (backend) ══"
if [ -x backend/.venv/bin/pip-audit ]; then
  (cd backend && .venv/bin/pip-audit -r requirements.txt) || FAIL=1
elif command -v pip-audit >/dev/null 2>&1; then
  pip-audit -r backend/requirements.txt || FAIL=1
else
  echo "pip-audit not installed — run: backend/.venv/bin/pip install pip-audit"
  FAIL=1
fi

echo "══ Slither (contracts) ══"
if command -v slither >/dev/null 2>&1; then
  (cd contracts && slither . --filter-paths "node_modules|test|mocks" --exclude-dependencies) || FAIL=1
else
  echo "Slither not installed (optional locally). CI installs it when available."
  echo "  pip install slither-analyzer  OR  docker run trailofbits/eth-security-toolbox"
fi

echo "══ Frontend private-key scan ══"
if rg -n "PRIVATE_KEY|mnemonic|0x[a-fA-F0-9]{64}" frontend/src --glob '!**/localhost.json' 2>/dev/null; then
  echo "Possible key material under frontend/src — investigate."
  FAIL=1
else
  echo "No private keys under frontend/src (OK)."
fi

if [ "$FAIL" != "0" ]; then
  echo "Security pass reported findings (see above)."
  exit 1
fi
echo "Security pass clean."
