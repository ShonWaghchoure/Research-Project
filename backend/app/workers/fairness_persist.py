"""Compute and persist baseline fairness metrics after an interval clears."""

from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.core.params import MarketParams
from app.db.models import FairnessMetric
from app.engine.clearing import ClearingResult
from app.engine.grid import Feeder
from app.engine.pricing import Position
from app.reputation.fairness import (
    gini,
    hhi,
    jain_index,
    matched_shares,
    max_price_impact,
    small_actor_parity,
    trade_welfare,
    welfare_efficiency,
    welfare_gains,
)
from app.sim.baselines import clear_b2


def _optimal_welfare(positions: Sequence[Position]) -> float:
    buyers = sorted(
        (position for position in positions if position.side == "buy"),
        key=lambda position: (-position.limit_price, position.participant_id),
    )
    sellers = sorted(
        (position for position in positions if position.side == "sell"),
        key=lambda position: (position.limit_price, position.participant_id),
    )
    buyer_remaining = [position.qty_kwh for position in buyers]
    seller_remaining = [position.qty_kwh for position in sellers]
    i = j = 0
    welfare = 0.0
    while i < len(buyers) and j < len(sellers):
        spread = buyers[i].limit_price - sellers[j].limit_price
        if spread <= 0:
            break
        quantity = min(buyer_remaining[i], seller_remaining[j])
        welfare += spread * quantity
        buyer_remaining[i] -= quantity
        seller_remaining[j] -= quantity
        if buyer_remaining[i] <= 0:
            i += 1
        if seller_remaining[j] <= 0:
            j += 1
    return welfare


def _metrics(
    positions: Sequence[Position],
    result: ClearingResult,
    params: MarketParams,
    optimal_welfare: float,
) -> dict[str, float]:
    offered = {
        position.participant_id: max(0, int(position.qty_kwh * 1000.0))
        for position in positions
    }
    matched: dict[str, int] = {}
    seller_volume: dict[str, int] = {}
    for trade in result.trades:
        matched[trade.buyer_id] = matched.get(trade.buyer_id, 0) + trade.qty_wh
        matched[trade.seller_id] = matched.get(trade.seller_id, 0) + trade.qty_wh
        seller_volume[trade.seller_id] = seller_volume.get(trade.seller_id, 0) + trade.qty_wh
    gains = welfare_gains(
        result.trades,
        result.p_ref,
        params,
        participants=offered.keys(),
    )
    return {
        "jain": jain_index(list(matched_shares(offered, matched).values())),
        "gini": gini(list(gains.values())),
        "hhi": hhi(seller_volume),
        "small_actor_parity": small_actor_parity(offered, matched),
        "price_impact": max_price_impact(positions, params),
        "welfare_efficiency": welfare_efficiency(
            trade_welfare(result.trades, positions),
            optimal_welfare,
        ),
    }


def persist_fairness(
    db: Session,
    *,
    interval_id: int,
    positions_b3: Sequence[Position],
    positions_b2: Sequence[Position],
    result_b3: ClearingResult,
    feeder: Feeder,
    params: MarketParams,
    prev_p_ref: float | None,
) -> None:
    if db.query(FairnessMetric.id).filter(FairnessMetric.interval_id == interval_id).first():
        return

    result_b2 = clear_b2(positions_b2, feeder, params, prev_p_ref)
    optimal_welfare = _optimal_welfare(positions_b2)
    db.add(
        FairnessMetric(
            interval_id=interval_id,
            metrics={
                "B2": _metrics(positions_b2, result_b2, params, optimal_welfare),
                "B3": _metrics(positions_b3, result_b3, params, optimal_welfare),
            },
        )
    )
