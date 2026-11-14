"""Position commit/reveal and anonymized orderbook."""

from __future__ import annotations

import secrets
from datetime import timezone

from eth_utils import to_checksum_address
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_participant
from app.chain.client import get_chain_client
from app.chain.commit import compute_commit_hash, side_to_uint8
from app.core.config import settings
from app.core.config_store import load_market_params
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


#: Generous household import ceiling per interval before storage is added (25 kWh).
BUY_BASE_WH = 25_000
#: How far past the interval end an EV deadline may be set.
MAX_DEADLINE_AFTER_END_S = 7 * 24 * 3600


def max_sell_wh(part: Participant, dt_hours: float) -> int:
    """Most a participant could physically deliver in one interval: PV over the interval,
    plus a full home battery, plus the EV battery when V2G is enabled."""
    ev = (part.ev_battery_wh or 0) if part.ev_v2g else 0
    return int(part.pv_capacity_w * dt_hours) + part.battery_wh + ev


def max_buy_wh(part: Participant) -> int:
    return BUY_BASE_WH + part.battery_wh + (part.ev_battery_wh or 0)


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

    params = load_market_params(db)
    if not params.p_fit <= body.limit_price_paise <= params.p_ret:
        raise HTTPException(
            status_code=422,
            detail=f"limit_price_paise must be between {params.p_fit} (feed-in) "
            f"and {params.p_ret} (retail)",
        )
    cap = max_sell_wh(part, params.dt_hours) if body.side == "sell" else max_buy_wh(part)
    if body.qty_wh > cap:
        raise HTTPException(
            status_code=422,
            detail=f"qty_wh {body.qty_wh} exceeds what this participant can "
            f"{'deliver' if body.side == 'sell' else 'take'} in one interval ({cap} Wh)",
        )

    starts = interval.starts_at
    ends = interval.ends_at
    if starts.tzinfo is None:
        starts = starts.replace(tzinfo=timezone.utc)
    if ends.tzinfo is None:
        ends = ends.replace(tzinfo=timezone.utc)
    deadline = int(body.deadline) if body.deadline is not None else int(ends.timestamp())
    # 0 means "no deadline" (the browser hashes it as 0, so it must be kept as 0).
    if deadline != 0 and not (
        starts.timestamp() <= deadline <= ends.timestamp() + MAX_DEADLINE_AFTER_END_S
    ):
        raise HTTPException(
            status_code=422,
            detail="deadline must fall between the interval start and 7 days after it ends",
        )
    salt = bytes.fromhex(body.salt[2:]) if body.salt else secrets.token_bytes(32)
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
    try:
        db.commit()
    except IntegrityError as exc:  # two concurrent submissions for the same interval
        db.rollback()
        raise HTTPException(status_code=409, detail="one net position per interval") from exc
    db.refresh(pos)
    return CommitData(
        id=pos.id,
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
    # Lock the interval row: the clock's REVEAL -> CLEARING update waits for this reveal
    # (or this reveal sees CLEARING), so a reveal can never land after clearing has read
    # the revealed positions and be both unmatched and counted as a reveal miss.
    interval = (
        db.query(Interval).filter(Interval.id == pos.interval_id).with_for_update().one_or_none()
    )
    if interval is None:
        raise HTTPException(status_code=404, detail="interval not found")
    if interval.state != IntervalState.REVEAL:
        # Revealing earlier would publish the bid while others can still commit.
        raise HTTPException(status_code=409, detail="reveal window is not open")

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

    # The sealed bid only means something if it was committed on chain. Fail closed: a
    # missing commit, a different commit, or an unreachable chain all refuse the reveal.
    try:
        client = get_chain_client()
        reachable = client.is_reachable()
        onchain = client.on_chain_commit(pos.interval_id, user.address) if reachable else None
    except Exception:
        reachable, onchain = False, None
    if not reachable:
        if not settings.testing:
            raise HTTPException(status_code=503, detail="chain unavailable, try again shortly")
    elif not onchain:
        raise HTTPException(status_code=400, detail="no on-chain commit for this position")
    elif onchain.lower() != pos.commit_hash.lower():
        raise HTTPException(status_code=400, detail="on-chain commit mismatch")

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
