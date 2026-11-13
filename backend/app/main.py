import logging
from typing import Any, Dict

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from web3 import Web3

from app.core.config import settings
from app.db.session import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ft_backend")

app = FastAPI(
    title="Fair and Trustworthy P2P Energy Trading API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> Dict[str, Any]:
    # 1. PostgreSQL ping
    postgres_status = "error"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            postgres_status = "ok"
    except Exception as exc:
        logger.warning("Postgres ping failed: %s", exc)
        postgres_status = f"unreachable: {exc}"

    # 2. Redis ping
    redis_status = "error"
    try:
        r = redis.Redis.from_url(
            settings.REDIS_URL,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
        if r.ping():
            redis_status = "ok"
        r.close()
    except Exception as exc:
        logger.warning("Redis ping failed: %s", exc)
        redis_status = f"unreachable: {exc}"

    # 3. Block number from CHAIN_RPC_URL via web3.py
    block_number = None
    rpc_status = "error"
    try:
        w3 = Web3(Web3.HTTPProvider(settings.CHAIN_RPC_URL, request_kwargs={"timeout": 1.0}))
        if w3.is_connected():
            block_number = int(w3.eth.block_number)
            rpc_status = "ok"
        else:
            rpc_status = "disconnected"
    except Exception as exc:
        logger.warning("RPC block_number query failed: %s", exc)
        rpc_status = f"unreachable: {exc}"

    is_all_ok = (
        postgres_status == "ok"
        and redis_status == "ok"
        and rpc_status == "ok"
        and block_number is not None
    )

    return {
        "status": "ok" if is_all_ok else "degraded",
        "postgres": postgres_status,
        "redis": redis_status,
        "chain_rpc": rpc_status,
        "block_number": block_number,
        "chain_id": settings.CHAIN_ID,
    }
