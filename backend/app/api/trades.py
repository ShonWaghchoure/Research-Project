"""Trade listing endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.models import Trade
from app.schemas.market import TradeOut

router = APIRouter(tags=["trades"])


def _to_out(t: Trade) -> TradeOut:
    return TradeOut(
        id=t.id,
        interval_id=t.interval_id,
        buyer_id=t.buyer_id,
        seller_id=t.seller_id,
        qty_wh=t.qty_wh,
        price_paise=t.price_paise,
        created_at=t.created_at,
    )


@router.get("/trades", response_model=list[TradeOut])
def list_trades(
    interval_id: int | None = Query(None),
    db: Session = Depends(get_db),
) -> list[TradeOut]:
    q = db.query(Trade)
    if interval_id is not None:
        q = q.filter(Trade.interval_id == interval_id)
    rows = q.order_by(Trade.id.desc()).limit(500).all()
    return [_to_out(t) for t in rows]


@router.get("/trades/{trade_id}", response_model=TradeOut)
def get_trade(trade_id: int, db: Session = Depends(get_db)) -> TradeOut:
    t = db.get(Trade, trade_id)
    if t is None:
        raise HTTPException(status_code=404, detail="trade not found")
    return _to_out(t)
