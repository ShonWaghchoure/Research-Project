.PHONY: dev test lint reset-db

BACKEND_DIR  := backend
FRONTEND_DIR := frontend
CONTRACTS_DIR := contracts
VENV         := $(BACKEND_DIR)/.venv/bin

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
	cd $(BACKEND_DIR) && $(VENV)/pytest -v
	@echo "── Frontend ──"
	cd $(FRONTEND_DIR) && npm run build

# ─── lint ───────────────────────────────────────────────────────────────────
lint:
	@echo "── Ruff ──"
	cd $(BACKEND_DIR) && $(VENV)/ruff check .
	@echo "── Mypy ──"
	cd $(BACKEND_DIR) && $(VENV)/mypy app
	@echo "── Next.js lint ──"
	cd $(FRONTEND_DIR) && npm run lint

# ─── reset-db ───────────────────────────────────────────────────────────────
reset-db:
	docker compose down -v
	docker compose up -d postgres redis
	@echo "⏳  Waiting for postgres…"
	@sleep 4
	cd $(BACKEND_DIR) && $(VENV)/alembic upgrade head
	@echo "✅  DB reset and migrated."
