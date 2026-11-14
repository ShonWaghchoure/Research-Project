"""WebSocket bridge over Redis pub/sub."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.workers.pubsub import CHANNELS

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["ws"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    channels: str = Query("interval,price,trades,reputation,flags,grid"),
) -> None:
    await websocket.accept()
    requested = [c.strip() for c in channels.split(",") if c.strip()]
    subs = [c for c in requested if c in CHANNELS]
    if not subs:
        await websocket.send_json({"error": "no valid channels", "allowed": list(CHANNELS)})
        await websocket.close()
        return

    r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe(*subs)
    await websocket.send_json({"subscribed": subs})

    async def reader() -> None:
        while True:
            msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if msg and msg.get("type") == "message":
                try:
                    data: Any = json.loads(msg["data"])
                except (TypeError, json.JSONDecodeError):
                    logger.warning("ws_invalid_pubsub_payload", channel=msg.get("channel"))
                    continue
                await websocket.send_json(
                    {"channel": msg["channel"], "type": "update", "data": data}
                )
            else:
                await asyncio.sleep(0.05)

    task = asyncio.create_task(reader())
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
        try:
            await pubsub.unsubscribe(*subs)
            await pubsub.close()
            await r.close()
        except Exception:
            pass
