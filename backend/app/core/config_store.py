"""Load / persist MarketParams via the config table."""

from __future__ import annotations

from dataclasses import asdict, fields
from typing import Any

from sqlalchemy.orm import Session

from app.core.params import DEFAULT_PARAMS, MarketParams
from app.db.models import ConfigEntry

# Keys the engine cares about (MarketParams fields).
PARAM_KEYS = {f.name for f in fields(MarketParams)}


def default_config_map() -> dict[str, Any]:
    return asdict(DEFAULT_PARAMS)


def seed_config(db: Session) -> None:
    for key, value in default_config_map().items():
        existing = db.get(ConfigEntry, key)
        if existing is None:
            db.add(ConfigEntry(key=key, value=value))
    db.flush()


def get_config_map(db: Session) -> dict[str, Any]:
    rows = db.query(ConfigEntry).all()
    return {row.key: row.value for row in rows}


def load_market_params(db: Session) -> MarketParams:
    """Engine entrypoint: build MarketParams from the config table (fallback defaults)."""
    raw = get_config_map(db)
    kwargs: dict[str, Any] = {}
    for key in PARAM_KEYS:
        if key in raw:
            kwargs[key] = raw[key]
    return MarketParams(**kwargs) if kwargs else DEFAULT_PARAMS


def update_config(
    db: Session,
    updates: dict[str, Any],
    *,
    updated_by: int | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply updates; return (before, after) snapshots of touched keys."""
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for key, value in updates.items():
        row = db.get(ConfigEntry, key)
        if row is None:
            before[key] = None
            row = ConfigEntry(key=key, value=value, updated_by=updated_by)
            db.add(row)
        else:
            before[key] = row.value
            row.value = value
            row.updated_by = updated_by
        after[key] = value
    db.flush()
    return before, after
