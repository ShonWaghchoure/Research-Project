.PHONY: dev test lint reset-db gen-api

BACKEND_DIR  := backend
FRONTEND_DIR := frontend
CONTRACTS_DIR := contracts

# ─── dev ────────────────────────────────────────────────────────────────────
dev:
	docker compose up -d
	@echo "⏳  Waiting for postgres + redis to be healthy…"
	@sleep 4
	@echo "⛓  Starting Hardhat node (background)…"
	cd $(CONTRACTS_DIR) && npx hardhat node &
	@sleep 3
	@echo "📦  Deploying contracts to localhost…"
	cd $(CONTRACTS_DIR) && npx hardhat run scripts/deploy.ts --network localhost
	@echo "🚀  Starting backend + frontend…"
	bash scripts/run-dev.sh

# ─── test ───────────────────────────────────────────────────────────────────
test:
	@echo "── Contracts ──"
	cd $(CONTRACTS_DIR) && npx hardhat test
	@echo "── Backend ──"
	cd $(BACKEND_DIR) && .venv/bin/pytest -v
	@echo "── Frontend ──"
	cd $(FRONTEND_DIR) && npm run build

# ─── lint ───────────────────────────────────────────────────────────────────
lint:
	@echo "── Ruff ──"
	cd $(BACKEND_DIR) && .venv/bin/ruff check .
	@echo "── Mypy ──"
	cd $(BACKEND_DIR) && .venv/bin/mypy app
	@echo "── Next.js lint ──"
	cd $(FRONTEND_DIR) && npm run lint

# ─── reset-db ───────────────────────────────────────────────────────────────
reset-db:
	docker compose down -v
	docker compose up -d postgres redis
	@echo "⏳  Waiting for postgres…"
	@sleep 4
	cd $(BACKEND_DIR) && .venv/bin/alembic upgrade head
	cd $(BACKEND_DIR) && .venv/bin/python -m app.db.seed
	@echo "✅  DB reset, migrated, and seeded."

# ─── OpenAPI → TypeScript client ────────────────────────────────────────────
gen-api:
	bash $(BACKEND_DIR)/scripts/gen_ts_client.sh
