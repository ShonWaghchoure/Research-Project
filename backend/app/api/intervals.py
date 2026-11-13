"""Interval and price-history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.models import Interval
from app.schemas.market import IntervalOut

router = APIRouter(tags=["intervals"])


def _to_out(iv: Interval) -> IntervalOut:
    return IntervalOut(
        id=iv.id,
        state=iv.state.value,
        starts_at=iv.starts_at,
        ends_at=iv.ends_at,
        p_ref_paise=iv.p_ref_paise,
        sdr=iv.sdr,
        input_root=iv.input_root,
        result_hash=iv.result_hash,
        delivery_root=iv.delivery_root,
        engine_version=iv.engine_version,
    )


@router.get("/intervals/current", response_model=IntervalOut)
def get_current_interval(db: Session = Depends(get_db)) -> IntervalOut:
    iv = db.query(Interval).order_by(desc(Interval.id)).first()
    if iv is None:
        raise HTTPException(status_code=404, detail="no interval")
    return _to_out(iv)


@router.get("/intervals/{interval_id}", response_model=IntervalOut)
def get_interval(interval_id: int, db: Session = Depends(get_db)) -> IntervalOut:
    iv = db.get(Interval, interval_id)
    if iv is None:
        raise HTTPException(status_code=404, detail="interval not found")
    return _to_out(iv)


@router.get("/price-history", response_model=list[IntervalOut])
def price_history(
    limit: int = Query(48, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[IntervalOut]:
    rows = (
        db.query(Interval)
        .filter(Interval.p_ref_paise.isnot(None))
        .order_by(desc(Interval.id))
        .limit(limit)
        .all()
    )
    return [_to_out(r) for r in reversed(rows)]
