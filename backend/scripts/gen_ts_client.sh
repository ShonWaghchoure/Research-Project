#!/usr/bin/env bash
# Generate TypeScript types from the running FastAPI OpenAPI schema.
# Requires: backend serving /openapi.json and npx openapi-typescript.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
OUT_DIR="$ROOT/frontend/src/api"
OUT_FILE="$OUT_DIR/schema.d.ts"

mkdir -p "$OUT_DIR"
echo "Fetching OpenAPI from $BASE_URL/openapi.json …"
curl -sf "$BASE_URL/openapi.json" -o "$OUT_DIR/openapi.json"
cd "$ROOT/frontend"
npx --yes openapi-typescript "$OUT_DIR/openapi.json" -o "$OUT_FILE"
echo "Wrote $OUT_FILE"
