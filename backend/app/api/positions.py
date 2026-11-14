"""Position commit/reveal and anonymized orderbook."""

from __future__ import annotations

from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import desc, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_participant
from app.chain.client import get_chain_client
from app.chain.commit import compute_commit_hash, side_to_uint8
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
    CommitConfirmationIn,
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
        deadline=int(p.deadline or 0),
        salt=p.salt or "",
        commit_hash=p.commit_hash,
        committed_tx=p.committed_tx,
        revealed=p.revealed,
        created_at=p.created_at,
    )


@router.post("/positions", response_model=PositionOut, status_code=status.HTTP_201_CREATED)
def create_position(
    body: PositionCreate,
    user: User = Depends(require_participant),
    db: Session = Depends(get_db),
) -> PositionOut:
    part = _participant_for(user, db)
    interval = db.query(Interval).order_by(desc(Interval.id)).first()
    if interval is None:
        raise HTTPException(status_code=404, detail="no active interval")
    if body.interval_id != interval.id:
        raise HTTPException(status_code=409, detail="interval is not current")
    if interval.state != IntervalState.COMMIT:
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
    # 0 (or omitted) means "no deadline"; the browser hashes it as 0.
    deadline = int(body.deadline or 0)
    if deadline != 0 and not (
        starts.timestamp() <= deadline <= ends.timestamp() + MAX_DEADLINE_AFTER_END_S
    ):
        raise HTTPException(
            status_code=422,
            detail="deadline must fall between the interval start and 7 days after it ends",
        )
    side = PositionSide.buy if body.side == "buy" else PositionSide.sell
    commit = compute_commit_hash(
        interval.id,
        user.address,
        side_to_uint8(body.side),
        body.qty_wh,
        body.limit_price_paise,
        deadline,
        body.salt,
    )
    pos = Position(
        participant_id=part.id,
        interval_id=interval.id,
        side=side,
        qty_wh=body.qty_wh,
        limit_price_paise=body.limit_price_paise,
        commit_hash=commit,
        salt=body.salt,
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
    return _pos_out(pos)


@router.post("/positions/{position_id}/commit", response_model=PositionOut)
def confirm_commit(
    position_id: int,
    body: CommitConfirmationIn,
    user: User = Depends(require_participant),
    db: Session = Depends(get_db),
) -> PositionOut:
    part = _participant_for(user, db)
    pos = db.get(Position, position_id)
    if pos is None or pos.participant_id != part.id:
        raise HTTPException(status_code=404, detail="position not found")
    if not pos.commit_hash:
        raise HTTPException(status_code=409, detail="position has no commit hash")

    client = get_chain_client()
    if not client.is_reachable():
        raise HTTPException(status_code=503, detail="chain RPC is unavailable")
    try:
        onchain = client.on_chain_commit(pos.interval_id, user.address)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="could not verify on-chain commit") from exc
    if not onchain:
        raise HTTPException(status_code=409, detail="on-chain commit not found")
    if onchain.lower() != pos.commit_hash.lower():
        raise HTTPException(status_code=409, detail="on-chain commit does not match position")

    pos.committed_tx = body.tx_hash
    db.commit()
    db.refresh(pos)
    return _pos_out(pos)


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

    if not pos.salt or not pos.commit_hash:
        raise HTTPException(status_code=400, detail="missing commit data")
    if not body or not pos.committed_tx:
        raise HTTPException(status_code=409, detail="on-chain commit confirmation is required")
    if body.tx_hash.lower() != pos.committed_tx.lower():
        raise HTTPException(status_code=409, detail="commit transaction hash mismatch")

    deadline = int(pos.deadline or 0)
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

    # The sealed bid only means something if it was committed on chain: fail closed.
    client = get_chain_client()
    if not client.is_reachable():
        raise HTTPException(status_code=503, detail="chain RPC is unavailable")
    try:
        onchain = client.on_chain_commit(pos.interval_id, user.address)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="could not verify on-chain commit") from exc
    if not onchain or onchain.lower() != pos.commit_hash.lower():
        raise HTTPException(status_code=409, detail="on-chain commit does not match position")

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
        db.query(
            Position.side,
            Position.limit_price_paise,
            func.sum(Position.qty_wh),
        )
        .filter(
            Position.interval_id == interval.id,
            Position.revealed.is_(True),
        )
        .group_by(Position.side, Position.limit_price_paise)
        .all()
    )
    bids = [
        OrderbookLevel(price_paise=int(price), qty_wh=int(total or 0))
        for side, price, total in rows
        if side == PositionSide.buy
    ]
    asks = [
        OrderbookLevel(price_paise=int(price), qty_wh=int(total or 0))
        for side, price, total in rows
        if side == PositionSide.sell
    ]
    bids.sort(key=lambda level: level.price_paise, reverse=True)
    asks.sort(key=lambda level: level.price_paise)
    return OrderbookOut(
        interval_id=interval.id,
        supply_wh=sum(level.qty_wh for level in asks),
        demand_wh=sum(level.qty_wh for level in bids),
        bids=bids,
        asks=asks,
    )
