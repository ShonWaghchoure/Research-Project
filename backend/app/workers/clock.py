"""Interval state machine clock — advances phases and triggers workers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.chain.client import ChainClient, get_chain_client
from app.db.models import Interval, IntervalState, Participant, Transaction, TxStatus
from app.db.session import SessionLocal
from app.workers import clearing, detection, meter, poster, reputation, sim_control
from app.workers.phase_timing import (
    STATE_ORDER,
    commit_deadline_ts,
    expected_state,
    next_state,
    reveal_deadline_ts,
)
from app.workers.pubsub import publish_interval

logger = structlog.get_logger(__name__)

# Minimum seconds that commitDeadline must sit above chain time when opening.
# Hardhat advances ~1s/block; bots + settlement burn many blocks quickly.
_OPEN_COMMIT_HEADROOM = 25


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _guarded_transition(db: Session, interval_id: int, from_state: IntervalState, to_state: IntervalState) -> bool:
    res = db.execute(
        update(Interval)
        .where(Interval.id == interval_id, Interval.state == from_state)
        .values(state=to_state)
    )
    db.commit()
    return bool(res.rowcount and res.rowcount > 0)


def _schedule_window(
    client: ChainClient,
    starts: datetime | None = None,
) -> tuple[datetime, datetime, int, int]:
    """Build starts/ends and on-chain deadlines anchored to chain time."""
    duration = int(sim_control.interval_seconds())
    chain_now = int(client.w3.eth.get_block("latest")["timestamp"])
    wall = _now()
    start = starts or wall
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)

    # Never start behind chain time — commitDeadline is derived from starts_at.
    if int(start.timestamp()) < chain_now:
        start = datetime.fromtimestamp(chain_now, tz=timezone.utc)

    end = start + timedelta(seconds=duration)
    commit_dl = commit_deadline_ts(start, end)
    headroom = max(_OPEN_COMMIT_HEADROOM, duration // 2)
    if commit_dl <= chain_now + headroom:
        shift = (chain_now + headroom + 1) - commit_dl
        start = start + timedelta(seconds=shift)
        end = end + timedelta(seconds=shift)
        commit_dl = commit_deadline_ts(start, end)
    reveal_dl = reveal_deadline_ts(start, end)
    return start, end, commit_dl, reveal_dl


def _publish(interval: Interval) -> None:
    publish_interval(
        {
            "interval_id": interval.id,
            "state": interval.state.value,
            "starts_at": interval.starts_at.isoformat(),
            "ends_at": interval.ends_at.isoformat(),
        }
    )


def _open_new_interval(db: Session, client: ChainClient, starts: datetime | None = None) -> Interval:
    start, end, commit_dl, reveal_dl = _schedule_window(client, starts=starts)
    interval = Interval(state=IntervalState.OPEN, starts_at=start, ends_at=end)
    db.add(interval)
    db.flush()  # allocate id; do not commit until chain open succeeds

    try:
        # Own session for the tx row so a mid-flight commit cannot persist Interval.
        client.open_interval(interval.id, commit_dl, reveal_dl, db=None)
    except Exception:
        db.rollback()
        raise

    db.commit()
    db.refresh(interval)
    _publish(interval)
    logger.info("interval_opened", interval_id=interval.id, commit_dl=commit_dl, reveal_dl=reveal_dl)
    return interval


def _ensure_on_chain_open(db: Session, client: ChainClient, interval: Interval) -> bool:
    """Retry openInterval for a DB interval that never made it on chain."""
    if client.on_chain_interval_opened(interval.id):
        return True

    start, end, commit_dl, reveal_dl = _schedule_window(client, starts=_now())
    interval.starts_at = start
    interval.ends_at = end
    interval.state = IntervalState.OPEN
    db.flush()
    try:
        client.open_interval(interval.id, commit_dl, reveal_dl, db=None)
    except Exception:
        logger.exception("interval_open_retry_failed", interval_id=interval.id)
        db.rollback()
        return False
    db.commit()
    db.refresh(interval)
    _publish(interval)
    logger.info("interval_open_retried", interval_id=interval.id)
    return True


def _current_interval(db: Session) -> Interval | None:
    return db.query(Interval).order_by(Interval.id.desc()).first()


def _safe_hook(name: str, interval: Interval, fn):  # type: ignore[no-untyped-def]
    """Run a worker step; return its result, or None if it raised (logged)."""
    try:
        return fn()
    except Exception:
        logger.exception("transition_hook_failed", hook=name, state=interval.state.value, id=interval.id)
        return None


def _interval_complete(db: Session, interval: Interval) -> bool:
    """Everything for this interval is confirmed on chain: delivery root stored (only set
    after postDelivery confirms) and the reputation root anchored. The clock only opens
    the next interval when this holds; it never revisits older intervals, so moving on
    early would abandon unsettled trades for good."""
    if not interval.delivery_root:
        return False
    tx = (
        db.query(Transaction)
        .filter(Transaction.idempotency_key == f"rep:{interval.id}:postRoot")
        .one_or_none()
    )
    if tx is not None:
        return tx.status == TxStatus.confirmed
    # No root transaction: complete only if there was nothing to anchor.
    return db.query(Participant).count() == 0


def _run_hooks(db: Session, interval: Interval, client: ChainClient) -> None:
    """Idempotent worker hooks for the current (and prior) FSM states.

    Each step is isolated so a poster failure cannot starve meter/reputation.
    """
    if interval.state in (
        IntervalState.CLEARING,
        IntervalState.SETTLED,
        IntervalState.METERED,
    ) and not interval.result_hash:
        _safe_hook("clearing", interval, lambda: clearing.run(db, interval))
        db.refresh(interval)

    settled = False
    if interval.state in (IntervalState.SETTLED, IntervalState.METERED) and interval.result_hash:
        if client.on_chain_interval_opened(interval.id):
            settled = bool(_safe_hook("poster", interval, lambda: poster.run(db, interval, client=client)))
            db.refresh(interval)
        else:
            logger.warning("poster_skip_not_open", interval_id=interval.id)

    if interval.state == IntervalState.METERED:
        # Metering needs clearing posted and every trade settled on chain; otherwise
        # postDelivery reverts ("no clearing") or deliveries are recorded for trades
        # that never moved money.
        if not interval.delivery_root and settled:
            _safe_hook("meter", interval, lambda: meter.run(db, interval, client=client))
            db.refresh(interval)
        elif not interval.delivery_root:
            logger.warning("meter_waiting_for_settlement", interval_id=interval.id)
        if interval.delivery_root:
            _safe_hook("reputation", interval, lambda: reputation.run(db, interval, client=client))
            db.refresh(interval)
            _safe_hook("detection", interval, lambda: detection.maybe_run_after_metered(db, interval))
            db.refresh(interval)


def _advance_to(db: Session, interval: Interval, target: IntervalState, client: ChainClient) -> Interval:
    """Advance one step at a time toward ``target``, running transition hooks."""
    db.refresh(interval)
    while interval.state != target:
        nxt = next_state(interval.state)
        if nxt is None:
            break
        # Don't jump past target
        cur_idx = STATE_ORDER.index(interval.state)
        tgt_idx = STATE_ORDER.index(target)
        if cur_idx >= tgt_idx:
            break
        if not _guarded_transition(db, interval.id, interval.state, nxt):
            db.refresh(interval)
            continue
        db.refresh(interval)
        _publish(interval)
        _run_hooks(db, interval, client)
        db.refresh(interval)
    return interval


def tick(client: ChainClient | None = None) -> None:
    """Single scheduler tick. Never raises to the caller."""
    if not sim_control.is_running():
        return
    client = client or get_chain_client()
    db = SessionLocal()
    try:
        if not client.is_reachable():
            logger.warning("clock_chain_unreachable")
            return

        interval = _current_interval(db)
        now = _now()

        if interval is None:
            _open_new_interval(db, client, starts=now)
            return

        # Orphan recovery: DB row exists but openInterval never confirmed.
        if not client.on_chain_interval_opened(interval.id):
            if not _ensure_on_chain_open(db, client, interval):
                return
            db.refresh(interval)

        # Past end and fully metered → open next
        ends = interval.ends_at
        if ends.tzinfo is None:
            ends = ends.replace(tzinfo=timezone.utc)
        if now >= ends and interval.state == IntervalState.METERED and _interval_complete(db, interval):
            _open_new_interval(db, client, starts=max(now, ends))
            return

        # If past end but not yet METERED, force advance through remaining phases
        want = expected_state(interval.starts_at, interval.ends_at, now)
        if now >= ends:
            want = IntervalState.METERED

        if interval.state != want:
            _advance_to(db, interval, want, client)
        else:
            # Restart-safe: finish incomplete work without re-entering the state.
            _run_hooks(db, interval, client)

        db.refresh(interval)
    except Exception:
        logger.exception("clock_tick_failed")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
