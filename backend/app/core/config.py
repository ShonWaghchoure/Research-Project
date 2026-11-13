from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = (
        "postgresql+psycopg://postgres:postgrespassword@localhost:5432/energy_trading"
    )
    REDIS_URL: str = "redis://localhost:6379/0"
    CHAIN_RPC_URL: str = "http://127.0.0.1:8545"
    CHAIN_ID: int = 31337
    OPERATOR_PRIVATE_KEY: str = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    JWT_SECRET: str = "fair_and_trustworthy_jwt_secret_key_change_in_production"
    INTERVAL_SECONDS: int = 900

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

    @property
    def sqlalchemy_database_url(self) -> str:
        url = self.DATABASE_URL
        if url.startswith("postgresql://") and not url.startswith("postgresql+"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        return url


settings = Settings()
