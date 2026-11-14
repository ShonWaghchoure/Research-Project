"""Redis pub/sub helpers for live market channels."""

from __future__ import annotations

import json
from typing import Any

import redis
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

CHANNELS = ("interval", "price", "trades", "reputation", "flags", "grid")


def _client() -> redis.Redis:  # type: ignore[type-arg]
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


def publish(channel: str, payload: dict[str, Any]) -> None:
    if channel not in CHANNELS:
        logger.warning("unknown_channel", channel=channel)
    try:
        r = _client()
        r.publish(channel, json.dumps(payload, default=str))
        r.close()
    except Exception as exc:
        logger.warning("pubsub_publish_failed", channel=channel, error=str(exc))


def publish_interval(payload: dict[str, Any]) -> None:
    publish("interval", payload)


def publish_price(payload: dict[str, Any]) -> None:
    publish("price", payload)


def publish_trades(payload: dict[str, Any]) -> None:
    publish("trades", payload)


def publish_reputation(payload: dict[str, Any]) -> None:
    publish("reputation", payload)


def publish_flags(payload: dict[str, Any]) -> None:
    publish("flags", payload)


def publish_grid(payload: dict[str, Any]) -> None:
    publish("grid", payload)
