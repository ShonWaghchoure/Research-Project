"""SDR-based reference price computation (pure functions).

Money/energy boundary note: callers may pass prices in any consistent unit
(paise/kWh in production, INR/kWh in unit tests). Results are floats and are
clipped to [p_fit, p_ret] before leaving this module.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, replace
from typing import Literal, Sequence

from app.core.params import MarketParams

EPS = 1e-12


@dataclass(frozen=True)
class Position:
    participant_id: str
    side: Literal["buy", "sell"]
    qty_kwh: float
    limit_price: float
    reputation: float


@dataclass(frozen=True)
class PriceResult:
    sdr: float
    p_raw: float
    p_ref: float
    supply: float
    demand: float


def _reputation_weight(reputation: float, r_ref: float) -> float:
    if r_ref <= 0:
        return 1.0
    return min(1.0, reputation / r_ref)


def _median_cap(quantities: Sequence[float], c: float) -> float:
    if not quantities:
        return 0.0
    return float(c) * float(statistics.median(quantities))


def _weighted_side_total(
    positions: Sequence[Position],
    side: Literal["buy", "sell"],
    params: MarketParams,
    *,
    apply_median_cap: bool = True,
) -> float:
    side_positions = [p for p in positions if p.side == side and p.qty_kwh > 0]
    if not side_positions:
        return 0.0

    # Median is taken only over positions with reputation >= rho_min so a swarm of
    # low-rep Sybil offers cannot poison the quantity cap (see docs/DECISIONS.md).
    if apply_median_cap:
        median_pool = [p.qty_kwh for p in side_positions if p.reputation >= params.rho_min]
        if not median_pool:
            median_pool = [p.qty_kwh for p in side_positions]
        cap_q: float | None = _median_cap(median_pool, params.c)
    else:
        cap_q = None

    total = 0.0
    for p in side_positions:
        effective_q = p.qty_kwh if cap_q is None else min(p.qty_kwh, cap_q)
        total += _reputation_weight(p.reputation, params.r_ref) * effective_q
    return total


def _p_raw_from_sdr(sdr: float, params: MarketParams) -> float:
    return float(params.p_fit) + float(params.p_ret - params.p_fit) / (1.0 + sdr ** params.k)


def _clip_price(price: float, params: MarketParams) -> float:
    return min(float(params.p_ret), max(float(params.p_fit), price))


def _smooth_p_ref(p_raw: float, prev_p_ref: float | None, params: MarketParams) -> float:
    if prev_p_ref is None:
        return _clip_price(p_raw, params)
    blended = params.alpha * p_raw + (1.0 - params.alpha) * prev_p_ref
    return _clip_price(blended, params)


def compute_reference_price(
    positions: Sequence[Position],
    prev_p_ref: float | None,
    params: MarketParams,
    *,
    apply_median_cap: bool = True,
) -> PriceResult:
    """Compute SDR-based reference price for one market interval.

    Pure: no I/O, no clock, no randomness.
    """
    supply = _weighted_side_total(positions, "sell", params, apply_median_cap=apply_median_cap)
    demand = _weighted_side_total(positions, "buy", params, apply_median_cap=apply_median_cap)

    midpoint = (float(params.p_fit) + float(params.p_ret)) / 2.0

    if supply <= 0.0 and demand <= 0.0:
        return PriceResult(sdr=1.0, p_raw=midpoint, p_ref=midpoint, supply=0.0, demand=0.0)

    if demand <= 0.0:
        # Zero demand with positive supply → floor price.
        return PriceResult(
            sdr=float("inf"),
            p_raw=float(params.p_fit),
            p_ref=float(params.p_fit),
            supply=supply,
            demand=0.0,
        )

    if supply <= 0.0:
        # Zero supply with positive demand → ceiling price.
        return PriceResult(
            sdr=0.0,
            p_raw=float(params.p_ret),
            p_ref=float(params.p_ret),
            supply=0.0,
            demand=demand,
        )

    sdr = supply / max(demand, EPS)
    p_raw = _p_raw_from_sdr(sdr, params)
    p_ref = _smooth_p_ref(p_raw, prev_p_ref, params)
    return PriceResult(sdr=sdr, p_raw=p_raw, p_ref=p_ref, supply=supply, demand=demand)


def price_impact(
    positions: Sequence[Position],
    participant_id: str,
    delta_kwh: float,
    params: MarketParams,
) -> float:
    """Return the change in p_raw if ``participant_id`` adds ``delta_kwh`` to their qty.

    Positive return means the raw price rose; negative means it fell.
    """
    baseline = compute_reference_price(positions, prev_p_ref=None, params=params)

    found = False
    perturbed: list[Position] = []
    for p in positions:
        if p.participant_id == participant_id:
            found = True
            perturbed.append(replace(p, qty_kwh=p.qty_kwh + delta_kwh))
        else:
            perturbed.append(p)

    if not found:
        raise ValueError(f"participant_id not found in positions: {participant_id!r}")

    after = compute_reference_price(perturbed, prev_p_ref=None, params=params)
    return after.p_raw - baseline.p_raw
