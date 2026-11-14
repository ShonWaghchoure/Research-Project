"""Live feeder and grid status for the grid map."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config_store import load_market_params
from app.db.deps import get_db
from app.db.models import (
    FeederLine,
    FeederNode,
    Interval,
    Participant,
    Position,
    Trade,
    User,
)
from app.engine.clearing import ClearedTrade, _recompute_line_loadings
from app.engine.grid import Feeder
from app.engine.grid import FeederLine as EngineLine
from app.engine.pricing import Position as EnginePosition
from app.schemas.market import (
    GridLineOut,
    GridNodeOut,
    GridParticipantOut,
    GridStatusOut,
)

router = APIRouter(tags=["grid"])


@router.get("/grid/status", response_model=GridStatusOut)
def get_grid_status(db: Session = Depends(get_db)) -> GridStatusOut:
    interval = db.query(Interval).order_by(desc(Interval.id)).first()
    if interval is None:
        raise HTTPException(status_code=404, detail="no interval")

    nodes = db.query(FeederNode).order_by(FeederNode.id).all()
    db_lines = db.query(FeederLine).order_by(FeederLine.id).all()
    feeder = Feeder(
        root=next((node.id for node in nodes if node.is_root), "n0"),
        lines=tuple(
            EngineLine(
                id=line.id,
                from_node=line.from_node_id,
                to_node=line.to_node_id,
                capacity_kw=line.capacity_w / 1000.0,
            )
            for line in db_lines
        ),
    )

    position_rows = (
        db.query(Position, Participant)
        .join(Participant, Participant.id == Position.participant_id)
        .filter(
            Position.interval_id == interval.id,
            Position.revealed.is_(True),
            Participant.active.is_(True),
        )
        .all()
    )
    engine_positions = [
        EnginePosition(
            participant_id=str(position.participant_id),
            side=position.side.value,
            qty_kwh=position.qty_wh / 1000.0,
            limit_price=float(position.limit_price_paise),
            reputation=1.0,
            node_id=participant.feeder_node_id,
        )
        for position, participant in position_rows
    ]

    trades = db.query(Trade).filter(Trade.interval_id == interval.id).all()
    engine_trades = [
        ClearedTrade(
            buyer_id=str(trade.buyer_id),
            seller_id=str(trade.seller_id),
            qty_wh=trade.qty_wh,
            price=float(trade.price_paise),
        )
        for trade in trades
    ]
    loadings = _recompute_line_loadings(
        engine_trades,
        engine_positions,
        feeder,
        load_market_params(db),
    )

    line_outputs: list[GridLineOut] = []
    congested: list[str] = []
    max_loading_pct = 0.0
    for line in db_lines:
        capacity_kw = line.capacity_w / 1000.0
        flow_kw = abs(loadings.get(line.id, 0.0))
        loading_pct = flow_kw / capacity_kw * 100.0 if capacity_kw > 0 else (100.0 if flow_kw else 0.0)
        max_loading_pct = max(max_loading_pct, loading_pct)
        if loading_pct >= 70.0:
            congested.append(line.id)
        line_outputs.append(
            GridLineOut(
                id=line.id,
                from_node=line.from_node_id,
                to_node=line.to_node_id,
                capacity_kw=capacity_kw,
                loading_pct=loading_pct,
            )
        )

    matched_by_participant: dict[int, int] = {}
    matched_wh = 0
    for trade in trades:
        matched_wh += trade.qty_wh
        matched_by_participant[trade.buyer_id] = (
            matched_by_participant.get(trade.buyer_id, 0) + trade.qty_wh
        )
        matched_by_participant[trade.seller_id] = (
            matched_by_participant.get(trade.seller_id, 0) + trade.qty_wh
        )
    unmatched_wh = sum(
        max(0, position.qty_wh - matched_by_participant.get(position.participant_id, 0))
        for position, _ in position_rows
    )
    p2p_share_pct = 100.0 * matched_wh / (matched_wh + unmatched_wh) if matched_wh + unmatched_wh else 0.0

    participant_rows = (
        db.query(Participant, User.address)
        .join(User, User.id == Participant.user_id)
        .filter(Participant.active.is_(True))
        .all()
    )
    by_node: dict[str, list[GridParticipantOut]] = {}
    for participant, address in participant_rows:
        by_node.setdefault(participant.feeder_node_id, []).append(
            GridParticipantOut(address=address, kind=participant.type.value)
        )

    return GridStatusOut(
        interval_id=interval.id,
        lines=line_outputs,
        congested_line_ids=congested,
        max_loading_pct=max_loading_pct,
        p2p_share_pct=p2p_share_pct,
        nodes=[
            GridNodeOut(
                id=node.id,
                label=node.name,
                kind="root" if node.is_root else "feeder",
                participants=by_node.get(node.id, []),
            )
            for node in nodes
        ],
    )
