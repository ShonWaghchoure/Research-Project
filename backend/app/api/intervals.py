"""Interval and price-history endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.models import Interval, Participant
from app.schemas.market import IntervalOut, PricePointOut
from app.workers.phase_timing import commit_deadline_ts, reveal_deadline_ts

router = APIRouter(tags=["intervals"])


def _to_out(iv: Interval, db: Session) -> IntervalOut:
    previous = (
        db.query(Interval.p_ref_paise)
        .filter(Interval.id < iv.id, Interval.p_ref_paise.isnot(None))
        .order_by(desc(Interval.id))
        .first()
    )
    active_participants = (
        db.query(func.count(Participant.id)).filter(Participant.active.is_(True)).scalar() or 0
    )
    return IntervalOut(
        id=iv.id,
        state=iv.state.value,
        starts_at=iv.starts_at,
        ends_at=iv.ends_at,
        commit_deadline=datetime.fromtimestamp(
            commit_deadline_ts(iv.starts_at, iv.ends_at), tz=timezone.utc
        ),
        reveal_deadline=datetime.fromtimestamp(
            reveal_deadline_ts(iv.starts_at, iv.ends_at), tz=timezone.utc
        ),
        p_ref_paise=iv.p_ref_paise,
        prev_p_ref_paise=previous[0] if previous else None,
        sdr=iv.sdr,
        active_participants=active_participants,
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
    return _to_out(iv, db)


@router.get("/intervals/{interval_id}", response_model=IntervalOut)
def get_interval(interval_id: int, db: Session = Depends(get_db)) -> IntervalOut:
    iv = db.get(Interval, interval_id)
    if iv is None:
        raise HTTPException(status_code=404, detail="interval not found")
    return _to_out(iv, db)


@router.get("/price-history", response_model=list[PricePointOut])
def price_history(
    limit: int = Query(96, ge=1, le=500),
    db: Session = Depends(get_db),
) -> list[PricePointOut]:
    rows = (
        db.query(Interval)
        .filter(Interval.p_ref_paise.isnot(None), Interval.sdr.isnot(None))
        .order_by(desc(Interval.id))
        .limit(limit)
        .all()
    )
    return [
        PricePointOut(
            interval_id=row.id,
            ends_at=row.ends_at,
            p_ref_paise=int(row.p_ref_paise),
            sdr=float(row.sdr),
        )
        for row in reversed(rows)
        if row.p_ref_paise is not None and row.sdr is not None
    ]
