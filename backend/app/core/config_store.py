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


#: Retail tariff baked into the deployed Settlement contract (immutable pRetPaise).
#: postClearing reverts if p_ref exceeds it, so p_ret may never be configured above it.
CHAIN_P_RET_PAISE = 800

_INT_KEYS = {f.name for f in fields(MarketParams) if f.type in (int, "int")}

# (min, max, min_inclusive, max_inclusive)
_RANGES: dict[str, tuple[float, float, bool, bool]] = {
    "p_fit": (0, CHAIN_P_RET_PAISE, True, False),
    "p_ret": (1, CHAIN_P_RET_PAISE, True, True),
    "interval_seconds": (5, 86_400, True, True),
    "demo_interval_seconds": (5, 3_600, True, True),
    "k": (1, 10, True, True),
    "alpha": (0, 1, False, True),
    "c": (1, 100, True, True),
    "r_ref": (0, 1, False, True),
    "rho_min": (0, 1, True, False),
    "r_cap": (0, 1, False, True),
    "beta": (0, float("inf"), True, True),
    "match_lambda": (0, 1_000, True, True),
    "dt_hours": (0, 1, False, True),
    "w_del": (0, 1, True, True),
    "w_rev": (0, 1, True, True),
    "w_hon": (0, 1, True, True),
    "w_col": (0, 1, True, True),
    "alpha0": (0, 1_000, False, True),
    "beta0": (0, 1_000, False, True),
    "kappa": (1, 100, True, True),
    "z": (0, 10, True, True),
    "half_life_intervals": (1, 1_000_000, True, True),
    "shortfall_penalty_f": (0, 1, True, True),
    "collusion_window_intervals": (1, 100_000, True, True),
}


def validate_config(merged: dict[str, Any]) -> list[str]:
    """Return human-readable problems with a full config map (empty list = valid)."""
    errors: list[str] = []
    for key, value in merged.items():
        if key not in PARAM_KEYS:
            errors.append(f"{key}: unknown setting")
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors.append(f"{key}: must be a number")
            continue
        if key in _INT_KEYS and not float(value).is_integer():
            errors.append(f"{key}: must be a whole number")
            continue
        lo, hi, lo_inc, hi_inc = _RANGES[key]
        if (value < lo or (value == lo and not lo_inc)) or (value > hi or (value == hi and not hi_inc)):
            errors.append(
                f"{key}: must be {'≥' if lo_inc else '>'} {lo} and {'≤' if hi_inc else '<'} {hi}"
            )
    if errors:
        return errors
    if merged["p_fit"] >= merged["p_ret"]:
        errors.append("p_fit must be below p_ret")
    elif merged["beta"] > 0.05 * (merged["p_ret"] - merged["p_fit"]):
        errors.append("beta must be at most 5% of (p_ret − p_fit)")
    weights = sum(merged[k] for k in ("w_del", "w_rev", "w_hon", "w_col"))
    if abs(weights - 1.0) > 1e-6:
        errors.append(f"reputation weights w_del + w_rev + w_hon + w_col must sum to 1 (got {weights:g})")
    return errors


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
