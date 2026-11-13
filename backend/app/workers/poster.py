"""Post clearing roots and settle trades on-chain (idempotent)."""

from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

from app.chain.client import ChainClient, get_chain_client
from app.db.models import Interval, Participant, Trade, User
from app.workers.phase_timing import reveal_deadline_ts

logger = structlog.get_logger(__name__)

BATCH_SIZE = 10


def _address_for_participant(db: Session, participant_id: int) -> str:
    part = db.get(Participant, participant_id)
    if part is None:
        raise ValueError(f"participant {participant_id} missing")
    user = db.get(User, part.user_id)
    if user is None:
        raise ValueError(f"user for participant {participant_id} missing")
    return user.address


def _settle_all_batches(
    db: Session,
    client: ChainClient,
    interval: Interval,
    trades: list[Trade],
) -> None:
    p_ref = int(interval.p_ref_paise or 0)
    batch: list[tuple[str, str, int, int]] = []
    batch_index = 0
    for t in trades:
        buyer = _address_for_participant(db, t.buyer_id)
        seller = _address_for_participant(db, t.seller_id)
        batch.append((buyer, seller, int(t.qty_wh), p_ref))
        if len(batch) >= BATCH_SIZE:
            client.settle_batch(interval.id, batch, batch_index, db=db)
            batch_index += 1
            batch = []
    if batch:
        client.settle_batch(interval.id, batch, batch_index, db=db)


def run(db: Session, interval: Interval, client: ChainClient | None = None) -> None:
    client = client or get_chain_client()
    if not interval.result_hash or interval.p_ref_paise is None or not interval.input_root:
        logger.warning("poster_skip_no_clearing", interval_id=interval.id)
        return

    trades = (
        db.query(Trade)
        .filter(Trade.interval_id == interval.id)
        .order_by(Trade.id)
        .all()
    )

    clearing_posted = client.on_chain_clearing_posted(interval.id)
    if not clearing_posted:
        # Ensure chain time is at/past reveal deadline before postClearing.
        # Only bump to reveal_ts — never to wall clock — so Hardhat does not race
        # ahead of wall time and invalidate the next interval's commitDeadline.
        reveal_ts = reveal_deadline_ts(interval.starts_at, interval.ends_at)
        client.sync_chain_time(reveal_ts)
        client.post_clearing(
            interval.id,
            interval.input_root,
            interval.result_hash,
            int(interval.p_ref_paise),
            db=db,
        )
        _settle_all_batches(db, client, interval, trades)
        logger.info("poster_done", interval_id=interval.id, trades=len(trades))
        return

    # Restart path: clearing already on chain — settle any remaining batches once.
    # Skip entirely once delivery is posted (settlement finished for this interval).
    if client.on_chain_delivery_posted(interval.id):
        logger.info("poster_skip_delivery_done", interval_id=interval.id)
        return
    _settle_all_batches(db, client, interval, trades)
    logger.info("poster_skip_already_posted", interval_id=interval.id, trades=len(trades))
