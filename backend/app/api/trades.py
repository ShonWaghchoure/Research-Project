"""Trade listing endpoints."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user
from app.db.deps import get_db
from app.db.models import Delivery, Interval, IntervalState, Participant, Trade, User
from app.schemas.market import TradeOut

router = APIRouter(tags=["trades"])


def _to_out(
    db: Session,
    trades: list[Trade],
    current_participant_id: int | None = None,
) -> list[TradeOut]:
    if not trades:
        return []

    participant_ids = {t.buyer_id for t in trades} | {t.seller_id for t in trades}
    addresses = dict(
        db.query(Participant.id, User.address)
        .join(User, User.id == Participant.user_id)
        .filter(Participant.id.in_(participant_ids))
        .all()
    )
    interval_ids = {t.interval_id for t in trades}
    states = dict(
        db.query(Interval.id, Interval.state)
        .filter(Interval.id.in_(interval_ids))
        .all()
    )
    trade_ids = [t.id for t in trades]
    deliveries = {
        d.trade_id: d
        for d in db.query(Delivery).filter(Delivery.trade_id.in_(trade_ids)).all()
    }

    result: list[TradeOut] = []
    for trade in trades:
        delivery = deliveries.get(trade.id)
        if delivery is not None:
            trade_status: Literal["cleared", "settled", "delivered", "shortfall"] = (
                "shortfall" if delivery.shortfall_wh > 0 else "delivered"
            )
        elif states.get(trade.interval_id) in (IntervalState.SETTLED, IntervalState.METERED):
            trade_status = "settled"
        else:
            trade_status = "cleared"
        side: Literal["buy", "sell"] | None = None
        if current_participant_id is not None:
            side = "buy" if trade.buyer_id == current_participant_id else "sell"

        buyer = addresses.get(trade.buyer_id)
        seller = addresses.get(trade.seller_id)
        if buyer is None or seller is None:
            raise HTTPException(status_code=500, detail="trade participant is missing")
        result.append(
            TradeOut(
                id=trade.id,
                interval_id=trade.interval_id,
                side=side,
                buyer=buyer,
                seller=seller,
                qty_wh=trade.qty_wh,
                price_paise=trade.price_paise,
                status=trade_status,
                created_at=trade.created_at,
            )
        )
    return result


@router.get("/trades", response_model=list[TradeOut])
def list_trades(
    interval_id: int | None = Query(None, ge=1),
    limit: int = Query(20, ge=1, le=500),
    mine: bool = Query(False),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> list[TradeOut]:
    current_participant_id: int | None = None
    query = db.query(Trade)
    if mine:
        if user is None:
            raise HTTPException(status_code=401, detail="not authenticated")
        participant = (
            db.query(Participant)
            .filter(Participant.user_id == user.id)
            .one_or_none()
        )
        if participant is None:
            return []
        current_participant_id = participant.id
        query = query.filter(
            (Trade.buyer_id == participant.id) | (Trade.seller_id == participant.id)
        )
    if interval_id is not None:
        query = query.filter(Trade.interval_id == interval_id)
    rows = query.order_by(Trade.id.desc()).limit(limit).all()
    return _to_out(db, rows, current_participant_id)


@router.get("/trades/{trade_id}", response_model=TradeOut)
def get_trade(trade_id: int, db: Session = Depends(get_db)) -> TradeOut:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise HTTPException(status_code=404, detail="trade not found")
    return _to_out(db, [trade])[0]
