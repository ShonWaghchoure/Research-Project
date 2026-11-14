.PHONY: dev demo test lint reset-db gen-api experiments-smoke experiments-plot security sync-contracts

BACKEND_DIR  := backend
FRONTEND_DIR := frontend
CONTRACTS_DIR := contracts

# ─── demo (one-click) ───────────────────────────────────────────────────────
demo:
	bash scripts/demo.sh

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
	@$(MAKE) sync-contracts
	@echo "🗄  Migrating + seeding DB…"
	cd $(BACKEND_DIR) && .venv/bin/alembic upgrade head
	cd $(BACKEND_DIR) && .venv/bin/python -m app.db.seed
	@echo "🚀  Starting backend + frontend (demo mode)…"
	DEMO_MODE=1 INTERVAL_SECONDS=45 DEMO_BOT_COUNT=20 bash scripts/run-dev.sh

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

# ─── Phase 11 experiments ───────────────────────────────────────────────────
experiments-smoke:
	cd experiments && ../backend/.venv/bin/python run_all.py

experiments-plot:
	cd experiments && ../backend/.venv/bin/python figures/plot_all.py

# ─── Phase 12 ───────────────────────────────────────────────────────────────
security:
	bash scripts/security-pass.sh

sync-contracts:
	cp $(CONTRACTS_DIR)/deployments/localhost.json $(FRONTEND_DIR)/src/contracts/localhost.json
	@echo "synced frontend/src/contracts/localhost.json"
