"""Run engine clearing for an interval and persist results."""

from __future__ import annotations

import subprocess
from typing import Optional

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config_store import load_market_params
from app.db.models import (
    Interval,
    Participant,
    Position,
    PositionSide,
    ReputationEvent,
    ReputationScore,
    Trade,
)
from app.engine.clearing import clear_interval
from app.engine.pricing import Position as EngPosition
from app.reputation.score import BetaState, initial_state, reputation
from app.reputation.tiers import Tier, classify, matching_reputation, volume_cap_kwh
from app.workers.fairness_persist import persist_fairness
from app.workers.feeder_load import load_feeder
from app.workers.pubsub import publish_grid, publish_price, publish_trades

logger = structlog.get_logger(__name__)


def engine_version() -> str:
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=str(__file__).rsplit("/backend/", 1)[0] if "/backend/" in __file__ else None,
            text=True,
            timeout=2,
        )
        return out.strip() or "dev"
    except Exception:
        return "dev"


def _latest_rep(db: Session, participant_id: int) -> tuple[BetaState, Tier | None]:
    row = (
        db.query(ReputationScore)
        .filter(ReputationScore.participant_id == participant_id)
        .order_by(desc(ReputationScore.interval_id))
        .first()
    )
    if row is None:
        return initial_state(), None
    try:
        prev = Tier(row.tier)
    except ValueError:
        prev = None
    return BetaState(alpha=row.alpha, beta=row.beta, evidence_count=row.evidence_count), prev


def run(db: Session, interval: Interval) -> None:
    """Clear revealed positions; idempotent if trades already stored."""
    existing = db.query(Trade).filter(Trade.interval_id == interval.id).count()
    if existing > 0 and interval.result_hash:
        logger.info("clearing_skip_already_done", interval_id=interval.id)
        return

    params = load_market_params(db)
    feeder = load_feeder(db)
    positions = (
        db.query(Position)
        .filter(Position.interval_id == interval.id, Position.revealed.is_(True))
        .all()
    )

    eng_positions: list[EngPosition] = []
    baseline_positions: list[EngPosition] = []
    for pos in positions:
        part = db.get(Participant, pos.participant_id)
        if part is None or not part.active:
            continue
        baseline_positions.append(
            EngPosition(
                participant_id=str(pos.participant_id),
                side="buy" if pos.side == PositionSide.buy else "sell",
                qty_kwh=pos.qty_wh / 1000.0,
                limit_price=float(pos.limit_price_paise),
                reputation=1.0,
                node_id=part.feeder_node_id,
            )
        )
        state, prev_tier = _latest_rep(db, pos.participant_id)
        tier = classify(state, prev_tier=prev_tier)
        r_match = matching_reputation(state, tier)
        qty_kwh = pos.qty_wh / 1000.0
        # Apply volume cap for probation etc.
        r_true = reputation(state)
        cap = volume_cap_kwh(params.q_base_kwh, r_true)
        qty_kwh = min(qty_kwh, cap)
        eng_positions.append(
            EngPosition(
                participant_id=str(pos.participant_id),
                side="buy" if pos.side == PositionSide.buy else "sell",
                qty_kwh=qty_kwh,
                limit_price=float(pos.limit_price_paise),
                reputation=r_match,
                node_id=part.feeder_node_id,
            )
        )

    prev_p: Optional[float] = None
    prev_iv = (
        db.query(Interval)
        .filter(Interval.id < interval.id, Interval.p_ref_paise.isnot(None))
        .order_by(desc(Interval.id))
        .first()
    )
    if prev_iv is not None and prev_iv.p_ref_paise is not None:
        prev_p = float(prev_iv.p_ref_paise)

    result = clear_interval(eng_positions, feeder, params, prev_p)

    # Replace any partial trades
    db.query(Trade).filter(Trade.interval_id == interval.id).delete()
    for t in result.trades:
        db.add(
            Trade(
                interval_id=interval.id,
                buyer_id=int(t.buyer_id),
                seller_id=int(t.seller_id),
                qty_wh=int(t.qty_wh),
                price_paise=int(round(t.price)),
            )
        )

    interval.p_ref_paise = int(round(result.p_ref))
    interval.sdr = float(result.sdr)
    interval.input_root = result.input_root
    interval.result_hash = result.result_hash
    interval.engine_version = engine_version()

    persist_fairness(
        db,
        interval_id=interval.id,
        positions_b3=eng_positions,
        positions_b2=baseline_positions,
        result_b3=result,
        feeder=feeder,
        params=params,
        prev_p_ref=prev_p,
    )

    # Reveal-miss events for unrevealed commits
    unrevealed = (
        db.query(Position)
        .filter(
            Position.interval_id == interval.id,
            Position.revealed.is_(False),
            Position.commit_hash.isnot(None),
        )
        .all()
    )
    for pos in unrevealed:
        exists = (
            db.query(ReputationEvent)
            .filter(
                ReputationEvent.interval_id == interval.id,
                ReputationEvent.participant_id == pos.participant_id,
                ReputationEvent.event_type == "reveal_miss",
            )
            .one_or_none()
        )
        if exists is None:
            db.add(
                ReputationEvent(
                    interval_id=interval.id,
                    participant_id=pos.participant_id,
                    event_type="reveal_miss",
                    payload={"position_id": pos.id},
                )
            )

    db.commit()
    publish_price(
        {
            "interval_id": interval.id,
            "p_ref_paise": interval.p_ref_paise,
            "sdr": interval.sdr,
            "input_root": interval.input_root,
            "result_hash": interval.result_hash,
        }
    )
    publish_trades(
        {
            "interval_id": interval.id,
            "count": len(result.trades),
            "trades": [
                {
                    "buyer_id": int(t.buyer_id),
                    "seller_id": int(t.seller_id),
                    "qty_wh": t.qty_wh,
                    "price_paise": int(round(t.price)),
                }
                for t in result.trades
            ],
        }
    )
    publish_grid({"interval_id": interval.id})
    logger.info(
        "clearing_done",
        interval_id=interval.id,
        trades=len(result.trades),
        p_ref=interval.p_ref_paise,
    )
