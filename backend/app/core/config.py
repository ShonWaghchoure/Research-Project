from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# chain_id -> deployments filename (without path)
_CHAIN_DEPLOYMENT_FILES: dict[int, str] = {
    31337: "localhost.json",
    11155111: "sepolia.json",
}


def _repo_root() -> Path:
    # backend/app/core/config.py -> repo root
    return Path(__file__).resolve().parents[3]


def _deployments_path(chain_id: int) -> Path:
    name = _CHAIN_DEPLOYMENT_FILES.get(chain_id, "localhost.json")
    return _repo_root() / "contracts" / "deployments" / name


def _load_deployment_addresses(chain_id: int) -> dict[str, str]:
    path = _deployments_path(chain_id)
    if not path.is_file():
        return {}
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for key in ("Ping", "MockINR", "Registry", "ReputationAnchor", "Settlement"):
        val = raw.get(key)
        if isinstance(val, str) and val:
            out[key] = val
        elif isinstance(val, dict) and val.get("address"):
            out[key] = str(val["address"])
    contracts = raw.get("contracts")
    if isinstance(contracts, dict):
        for key, meta in contracts.items():
            if key not in out and isinstance(meta, dict) and meta.get("address"):
                out[key] = str(meta["address"])
    return out


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgrespassword@localhost:5433/energy_trading"
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    CHAIN_RPC_URL: str = "http://127.0.0.1:8545"
    CHAIN_ID: int = 31337
    OPERATOR_PRIVATE_KEY: str = (
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )
    JWT_SECRET: str = "fair_and_trustworthy_jwt_secret_key_change_in_production"
    INTERVAL_SECONDS: int = 900

    DEMO_MODE: bool = False
    DEMO_BOT_COUNT: int = 20
    # Optional override; when unset, derived from CHAIN_ID (1 local, 2 sepolia).
    CHAIN_CONFIRMATIONS: Optional[int] = None
    # Comma-separated browser origins. Empty / "*" = allow all (local demo only).
    CORS_ORIGINS: str = "*"

    PING_CONTRACT_ADDRESS: Optional[str] = None
    MOCK_INR_ADDRESS: Optional[str] = None
    REGISTRY_ADDRESS: Optional[str] = None
    REPUTATION_ANCHOR_ADDRESS: Optional[str] = None
    SETTLEMENT_ADDRESS: Optional[str] = None

    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @model_validator(mode="after")
    def _fill_addresses_from_deployments(self) -> Settings:
        deployed = _load_deployment_addresses(self.CHAIN_ID)
        mapping = {
            "Ping": "PING_CONTRACT_ADDRESS",
            "MockINR": "MOCK_INR_ADDRESS",
            "Registry": "REGISTRY_ADDRESS",
            "ReputationAnchor": "REPUTATION_ANCHOR_ADDRESS",
            "Settlement": "SETTLEMENT_ADDRESS",
        }
        for dep_key, attr in mapping.items():
            current = getattr(self, attr)
            if not current and dep_key in deployed:
                object.__setattr__(self, attr, deployed[dep_key])
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url

    @property
    def confirmations(self) -> int:
        if self.CHAIN_CONFIRMATIONS is not None:
            return max(1, int(self.CHAIN_CONFIRMATIONS))
        return 1 if self.CHAIN_ID == 31337 else 2

    @property
    def testing(self) -> bool:
        return os.environ.get("TESTING", "").strip() in ("1", "true", "True", "yes")


settings = Settings()
