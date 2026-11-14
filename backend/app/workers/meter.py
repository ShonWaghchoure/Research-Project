"""Simulate meter readings, store deliveries, post delivery root, settle shortfalls."""

from __future__ import annotations

from collections import defaultdict

import structlog
from sqlalchemy.orm import Session

from app.chain.client import ChainClient, get_chain_client
from app.chain.merkle import build_tree, get_proof, shortfall_leaf
from app.db.models import Delivery, Interval, MeterReading, Participant, Trade, User
from app.sim.meters import MeterKey, verify
from app.sim.meters import MeterReading as SimReading

logger = structlog.get_logger(__name__)

METER_SEED = 42
LAZY_SHORTFALL_FRAC = 0.5  # lazy bots deliver half


def _is_lazy(db: Session, part: Participant | None) -> bool:
    """Only the designated demo bot under-delivers (see bots.lazy_bot_address)."""
    from app.workers.bots import lazy_bot_address

    lazy = lazy_bot_address()
    if part is None or lazy is None:
        return False
    user = db.get(User, part.user_id)
    return user is not None and user.address.lower() == lazy.lower()


def _addr(db: Session, participant_id: int) -> str:
    part = db.get(Participant, participant_id)
    assert part is not None
    user = db.get(User, part.user_id)
    assert user is not None
    return user.address


def run(db: Session, interval: Interval, client: ChainClient | None = None) -> None:
    client = client or get_chain_client()
    trades = db.query(Trade).filter(Trade.interval_id == interval.id).all()

    existing_del = db.query(Delivery).filter(Delivery.interval_id == interval.id).count()
    if existing_del > 0 and interval.delivery_root:
        # Restart path: delivery already posted — still attempt shortfall settles
        # (chain idempotency keys prevent double-slash).
        logger.info("meter_retry_shortfalls_only", interval_id=interval.id)
        _settle_existing_shortfalls(db, interval, client)
        return

    db.query(Delivery).filter(Delivery.interval_id == interval.id).delete()

    seller_buyer_shortfall: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    export_wh: dict[int, int] = defaultdict(int)
    import_wh: dict[int, int] = defaultdict(int)

    for t in trades:
        seller = db.get(Participant, t.seller_id)
        if _is_lazy(db, seller):
            delivered = int(t.qty_wh * (1.0 - LAZY_SHORTFALL_FRAC))
        else:
            delivered = int(t.qty_wh)
        shortfall = max(0, int(t.qty_wh) - delivered)
        db.add(
            Delivery(
                interval_id=interval.id,
                trade_id=t.id,
                delivered_wh=delivered,
                shortfall_wh=shortfall,
            )
        )
        seller_buyer_shortfall[t.seller_id][t.buyer_id] += shortfall
        export_wh[t.seller_id] += delivered
        import_wh[t.buyer_id] += delivered

    participants_involved = set(export_wh) | set(import_wh)
    for pid in participants_involved:
        key = MeterKey(seed=METER_SEED, participant_id=str(pid))
        reading = SimReading(
            participant_id=str(pid),
            interval=int(interval.id),
            export_wh=int(export_wh.get(pid, 0)),
            import_wh=int(import_wh.get(pid, 0)),
            pv_wh=0,
        )
        signed = key.sign(reading)
        if not verify(signed, key.address):
            raise RuntimeError(f"meter signature verify failed for {pid}")
        existing = (
            db.query(MeterReading)
            .filter(
                MeterReading.interval_id == interval.id,
                MeterReading.participant_id == pid,
            )
            .one_or_none()
        )
        if existing is None:
            db.add(
                MeterReading(
                    interval_id=interval.id,
                    participant_id=pid,
                    import_wh=int(import_wh.get(pid, 0)),
                    export_wh=int(export_wh.get(pid, 0)),
                    signature=signed.signature,
                )
            )
        else:
            existing.import_wh = int(import_wh.get(pid, 0))
            existing.export_wh = int(export_wh.get(pid, 0))
            existing.signature = signed.signature

    db.flush()

    pairs = _shortfall_pairs(db, trades, seller_buyer_shortfall)
    leaves = _pair_leaves(interval.id, pairs)

    tree = build_tree(leaves)
    db.commit()  # readings and deliveries are deterministic; safe to persist first

    # Record the root only once it is confirmed on chain: the clock treats a stored
    # delivery_root as "interval finished" and opens the next one. A revert raises here.
    client.post_delivery(interval.id, tree.root, db=db)
    interval.delivery_root = tree.root
    db.commit()

    _settle_pairs(db, interval, client, pairs, leaves)

    logger.info("meter_done", interval_id=interval.id, root=interval.delivery_root)


Pair = tuple[str, str, int]  # (seller address, buyer address, shortfall Wh)


def _shortfall_pairs(
    db: Session, trades: list[Trade], seller_buyer_shortfall: dict[int, dict[int, int]]
) -> list[Pair]:
    """One entry per traded (seller, buyer) pair, in a fixed order, so the initial run and
    a restart build the identical tree. Every short-changed buyer gets its own leaf."""
    keys = sorted({(t.seller_id, t.buyer_id) for t in trades})
    return [
        (_addr(db, sid), _addr(db, bid), int(seller_buyer_shortfall.get(sid, {}).get(bid, 0)))
        for sid, bid in keys
    ]


def _pair_leaves(interval_id: int, pairs: list[Pair]) -> list[str]:
    if not pairs:
        zero = "0x0000000000000000000000000000000000000000"
        return [shortfall_leaf(interval_id, zero, zero, 0)]
    return [shortfall_leaf(interval_id, s, b, sf) for s, b, sf in pairs]


def _settle_pairs(
    db: Session, interval: Interval, client: ChainClient, pairs: list[Pair], leaves: list[str]
) -> None:
    for idx, (seller, buyer, sf) in enumerate(pairs):
        if sf <= 0:
            continue
        try:
            client.settle_shortfall(interval.id, seller, sf, get_proof(leaves, idx), buyer, db=db)
        except Exception as exc:
            logger.warning(
                "settle_shortfall_failed",
                interval_id=interval.id,
                seller=seller,
                buyer=buyer,
                error=str(exc)[:200],
            )


def _settle_existing_shortfalls(db: Session, interval: Interval, client: ChainClient) -> None:
    """Restart path: rebuild the same (seller, buyer) tree and settle any open shortfalls."""
    trades = db.query(Trade).filter(Trade.interval_id == interval.id).all()
    deliveries = {
        d.trade_id: d
        for d in db.query(Delivery).filter(Delivery.interval_id == interval.id).all()
    }
    seller_buyer_shortfall: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for t in trades:
        d = deliveries.get(t.id)
        sf = int(d.shortfall_wh) if d else 0
        if sf > 0:
            seller_buyer_shortfall[t.seller_id][t.buyer_id] += sf
    if not trades:
        return
    pairs = _shortfall_pairs(db, trades, seller_buyer_shortfall)
    _settle_pairs(db, interval, client, pairs, _pair_leaves(interval.id, pairs))
