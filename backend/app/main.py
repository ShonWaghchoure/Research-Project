from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict

import redis
import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from web3 import Web3

from app.api import (
    admin,
    audit,
    auth,
    fairness,
    grid,
    intervals,
    participants,
    positions,
    reputation_api,
    trades,
    ws,
)
from app.core.config import settings
from app.core.limiter import limiter
from app.core.logging import setup_logging
from app.db.session import engine
from app.workers import sim_control
from app.workers.scheduler import start_scheduler, stop_scheduler

setup_logging()
logger = structlog.get_logger("ft_backend")

MAX_REQUEST_BYTES = 1_048_576  # 1 MiB


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > MAX_REQUEST_BYTES:
            return Response("request body too large", status_code=413)
        return await call_next(request)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


def _cors_origins() -> list[str]:
    raw = (settings.CORS_ORIGINS or "*").strip()
    if raw in ("*", ""):
        return ["*"]
    return [o.strip() for o in raw.split(",") if o.strip()]


app = FastAPI(
    title="Fair and Trustworthy P2P Energy Trading API",
    version="0.12.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

_cors = _cors_origins()
# Browsers reject allow_origins=["*"] with credentials=True; only enable credentials
# when origins are an explicit allow-list (production).
_cors_credentials = _cors != ["*"]

app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors,
    allow_credentials=_cors_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(participants.router)
app.include_router(admin.router)
app.include_router(audit.router)
app.include_router(intervals.router)
app.include_router(positions.router)
app.include_router(trades.router)
app.include_router(reputation_api.router)
app.include_router(grid.router)
app.include_router(fairness.router)
app.include_router(ws.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[no-untyped-def]
    response = await call_next(request)
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        client=request.client.host if request.client else None,
    )
    return response


@app.get("/health")
@limiter.limit("60/minute")
def health_check(request: Request) -> Dict[str, Any]:
    postgres_status = "error"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            postgres_status = "ok"
    except Exception as exc:
        logger.warning("postgres_ping_failed", error=str(exc))
        postgres_status = f"unreachable: {exc}"

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
        logger.warning("redis_ping_failed", error=str(exc))
        redis_status = f"unreachable: {exc}"

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
        logger.warning("rpc_ping_failed", error=str(exc))
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
        "demo_mode": settings.DEMO_MODE,
        "interval_seconds": sim_control.interval_seconds(),
        "simulation_running": sim_control.is_running(),
    }
