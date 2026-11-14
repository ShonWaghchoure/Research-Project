"""WebSocket bridge over Redis pub/sub.

One Redis subscription per process fans out to every connected client through small
bounded queues. Previously each client opened its own Redis connection plus a polling
task, so a script opening thousands of sockets could exhaust Redis's client limit and
break the workers that publish market updates.
"""

from __future__ import annotations

import asyncio
import json
from collections import Counter
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.workers.pubsub import CHANNELS

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["ws"])

MAX_WS_CONNECTIONS = 500
MAX_WS_PER_IP = 20
#: Messages buffered per client; a slow client drops the oldest instead of growing memory.
CLIENT_QUEUE_SIZE = 100


class _Hub:
    def __init__(self) -> None:
        self.clients: dict[asyncio.Queue[dict[str, Any]], set[str]] = {}
        self.per_ip: Counter[str] = Counter()
        self._task: asyncio.Task[None] | None = None

    def ensure_started(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._pump())

    async def _pump(self) -> None:
        while True:
            r = None
            try:
                r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
                pubsub = r.pubsub()
                await pubsub.subscribe(*CHANNELS)
                async for msg in pubsub.listen():
                    if msg.get("type") != "message":
                        continue
                    # Publishers send JSON strings; clients expect objects. Parse once here
                    # for every client instead of once per connection.
                    try:
                        data: Any = json.loads(msg["data"])
                    except (TypeError, json.JSONDecodeError):
                        logger.warning("ws_invalid_pubsub_payload", channel=msg.get("channel"))
                        continue
                    payload = {"channel": msg["channel"], "type": "update", "data": data}
                    for q, subs in list(self.clients.items()):
                        if msg["channel"] not in subs:
                            continue
                        if q.full():
                            q.get_nowait()
                        q.put_nowait(payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("ws_hub_redis_error", error=str(exc))
                await asyncio.sleep(2.0)
            finally:
                if r is not None:
                    try:
                        await r.close()
                    except Exception:
                        pass


hub = _Hub()


def _origin_allowed(origin: str | None) -> bool:
    raw = (settings.CORS_ORIGINS or "*").strip()
    if raw in ("", "*"):
        return True
    allowed = {o.strip().rstrip("/") for o in raw.split(",") if o.strip()}
    return origin is not None and origin.rstrip("/") in allowed


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channels: str = Query("interval,price,trades,reputation,flags,grid"),
) -> None:
    ip = websocket.client.host if websocket.client else "unknown"
    if not _origin_allowed(websocket.headers.get("origin")):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    if len(hub.clients) >= MAX_WS_CONNECTIONS or hub.per_ip[ip] >= MAX_WS_PER_IP:
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

    await websocket.accept()
    requested = [c.strip() for c in channels.split(",") if c.strip()]
    subs = {c for c in requested if c in CHANNELS}
    if not subs:
        await websocket.send_json({"error": "no valid channels", "allowed": list(CHANNELS)})
        await websocket.close()
        return

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=CLIENT_QUEUE_SIZE)
    hub.clients[queue] = subs
    hub.per_ip[ip] += 1
    hub.ensure_started()
    await websocket.send_json({"subscribed": sorted(subs)})

    async def writer() -> None:
        while True:
            await websocket.send_json(await queue.get())

    task = asyncio.create_task(writer())
    try:
        while True:
            # Keep connection alive; ignore client pings/text
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except TimeoutError:
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.info("ws_closed", error=str(exc))
    finally:
        task.cancel()
        hub.clients.pop(queue, None)
        hub.per_ip[ip] -= 1
        if hub.per_ip[ip] <= 0:
            del hub.per_ip[ip]
