"""Position commit/reveal and anonymized orderbook."""

from __future__ import annotations

import secrets
from datetime import timezone

from eth_utils import to_checksum_address
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_participant
from app.chain.client import get_chain_client
from app.chain.commit import compute_commit_hash, side_to_uint8
from app.db.deps import get_db
from app.db.models import (
    Interval,
    IntervalState,
    Participant,
    Position,
    PositionSide,
    User,
)
from app.schemas.market import (
    CommitData,
    OrderbookLevel,
    OrderbookOut,
    PositionCreate,
    PositionOut,
    RevealIn,
)

router = APIRouter(tags=["positions"])


def _participant_for(user: User, db: Session) -> Participant:
    part = db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
    if part is None:
        raise HTTPException(status_code=400, detail="participant profile required")
    return part


def _pos_out(p: Position) -> PositionOut:
    return PositionOut(
        id=p.id,
        interval_id=p.interval_id,
        side=p.side.value,
        qty_wh=p.qty_wh,
        limit_price_paise=p.limit_price_paise,
        commit_hash=p.commit_hash,
        revealed=p.revealed,
        created_at=p.created_at,
    )


@router.post("/positions", response_model=CommitData, status_code=status.HTTP_201_CREATED)
def create_position(
    body: PositionCreate,
    user: User = Depends(require_participant),
    db: Session = Depends(get_db),
) -> CommitData:
    part = _participant_for(user, db)
    interval = db.query(Interval).order_by(desc(Interval.id)).first()
    if interval is None:
        raise HTTPException(status_code=404, detail="no active interval")
    if interval.state not in (IntervalState.OPEN, IntervalState.COMMIT):
        raise HTTPException(status_code=409, detail="commits closed for current interval")

    existing = (
        db.query(Position)
        .filter(Position.participant_id == part.id, Position.interval_id == interval.id)
        .one_or_none()
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="one net position per interval")

    ends = interval.ends_at
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    deadline = int(body.deadline) if body.deadline is not None else int(ends.timestamp())
    salt = secrets.token_bytes(32)
    salt_hex = "0x" + salt.hex()
    side = PositionSide.buy if body.side == "buy" else PositionSide.sell
    commit = compute_commit_hash(
        interval.id,
        user.address,
        side_to_uint8(body.side),
        body.qty_wh,
        body.limit_price_paise,
        deadline,
        salt,
    )
    pos = Position(
        participant_id=part.id,
        interval_id=interval.id,
        side=side,
        qty_wh=body.qty_wh,
        limit_price_paise=body.limit_price_paise,
        commit_hash=commit,
        salt=salt_hex,
        deadline=deadline,
        revealed=False,
    )
    db.add(pos)
    db.commit()
    db.refresh(pos)
    return CommitData(
        position_id=pos.id,
        interval_id=interval.id,
        commit_hash=commit,
        salt=salt_hex,
        side=body.side,
        qty_wh=body.qty_wh,
        limit_price_paise=body.limit_price_paise,
        deadline=deadline,
        participant=to_checksum_address(user.address),
    )


@router.post("/positions/{position_id}/reveal", response_model=PositionOut)
def reveal_position(
    position_id: int,
    body: RevealIn | None = None,
    user: User = Depends(require_participant),
    db: Session = Depends(get_db),
) -> PositionOut:
    part = _participant_for(user, db)
    pos = db.get(Position, position_id)
    if pos is None or pos.participant_id != part.id:
        raise HTTPException(status_code=404, detail="position not found")
    interval = db.get(Interval, pos.interval_id)
    if interval is None:
        raise HTTPException(status_code=404, detail="interval not found")
    if interval.state not in (IntervalState.OPEN, IntervalState.COMMIT, IntervalState.REVEAL):
        raise HTTPException(status_code=409, detail="reveal window closed")

    if body and body.salt and pos.salt and body.salt.lower() != pos.salt.lower():
        raise HTTPException(status_code=400, detail="salt mismatch")

    if not pos.salt or not pos.commit_hash:
        raise HTTPException(status_code=400, detail="missing commit data")

    ends = interval.ends_at
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    deadline = int(pos.deadline) if pos.deadline is not None else int(ends.timestamp())
    salt_hex = pos.salt.removeprefix("0x")
    recomputed = compute_commit_hash(
        pos.interval_id,
        user.address,
        side_to_uint8(pos.side.value),
        pos.qty_wh,
        pos.limit_price_paise,
        deadline,
        bytes.fromhex(salt_hex),
    )
    if recomputed.lower() != pos.commit_hash.lower():
        raise HTTPException(status_code=400, detail="commit hash mismatch")

    try:
        client = get_chain_client()
        if client.is_reachable():
            onchain = client.on_chain_commit(pos.interval_id, user.address)
            if onchain and onchain.lower() != pos.commit_hash.lower():
                raise HTTPException(status_code=400, detail="on-chain commit mismatch")
    except HTTPException:
        raise
    except Exception:
        pass

    pos.revealed = True
    db.commit()
    db.refresh(pos)
    return _pos_out(pos)


@router.get("/positions/mine", response_model=list[PositionOut])
def my_positions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PositionOut]:
    part = db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
    if part is None:
        return []
    rows = (
        db.query(Position)
        .filter(Position.participant_id == part.id)
        .order_by(desc(Position.id))
        .limit(100)
        .all()
    )
    return [_pos_out(p) for p in rows]


@router.get("/orderbook", response_model=OrderbookOut)
def orderbook(db: Session = Depends(get_db)) -> OrderbookOut:
    interval = db.query(Interval).order_by(desc(Interval.id)).first()
    if interval is None:
        raise HTTPException(status_code=404, detail="no interval")
    rows = (
        db.query(Position.side, func.sum(Position.qty_wh), func.count(Position.id))
        .filter(
            Position.interval_id == interval.id,
            Position.revealed.is_(True),
        )
        .group_by(Position.side)
        .all()
    )
    levels = [
        OrderbookLevel(side=side.value if hasattr(side, "value") else str(side), total_qty_wh=int(total or 0), count=int(cnt))
        for side, total, cnt in rows
    ]
    return OrderbookOut(interval_id=interval.id, levels=levels)
