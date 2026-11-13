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


def _is_lazy(part: Participant | None) -> bool:
    if part is None or not part.display_name:
        return False
    return "lazy" in part.display_name.lower()


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

    seller_shortfall: dict[int, int] = defaultdict(int)
    seller_buyer_shortfall: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    export_wh: dict[int, int] = defaultdict(int)
    import_wh: dict[int, int] = defaultdict(int)

    for t in trades:
        seller = db.get(Participant, t.seller_id)
        if _is_lazy(seller):
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
        seller_shortfall[t.seller_id] += shortfall
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

    leaves: list[str] = []
    leaf_meta: list[tuple[int, str, int]] = []
    sellers = sorted({t.seller_id for t in trades})
    if not sellers:
        zero = "0x0000000000000000000000000000000000000000"
        leaves = [shortfall_leaf(interval.id, zero, 0)]
        leaf_meta = [(-1, zero, 0)]
    else:
        for sid in sellers:
            addr = _addr(db, sid)
            sf = int(seller_shortfall.get(sid, 0))
            leaves.append(shortfall_leaf(interval.id, addr, sf))
            leaf_meta.append((sid, addr, sf))

    tree = build_tree(leaves)
    interval.delivery_root = tree.root
    db.commit()

    client.post_delivery(interval.id, tree.root, db=db)

    for idx, (sid, addr, sf) in enumerate(leaf_meta):
        if sf <= 0 or sid < 0:
            continue
        buyers = seller_buyer_shortfall.get(sid, {})
        if not buyers:
            continue
        buyer_id = max(buyers.items(), key=lambda kv: kv[1])[0]
        buyer_addr = _addr(db, buyer_id)
        proof = get_proof(leaves, idx)
        try:
            client.settle_shortfall(interval.id, addr, sf, proof, buyer_addr, db=db)
        except Exception as exc:
            logger.warning(
                "settle_shortfall_failed",
                interval_id=interval.id,
                seller=addr,
                error=str(exc),
            )

    logger.info("meter_done", interval_id=interval.id, root=interval.delivery_root)


def _settle_existing_shortfalls(db: Session, interval: Interval, client: ChainClient) -> None:
    """Rebuild the same seller-ordered Merkle tree as the initial meter run."""
    trades = db.query(Trade).filter(Trade.interval_id == interval.id).all()
    deliveries = {
        d.trade_id: d
        for d in db.query(Delivery).filter(Delivery.interval_id == interval.id).all()
    }
    seller_shortfall: dict[int, int] = defaultdict(int)
    seller_buyer_shortfall: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for t in trades:
        d = deliveries.get(t.id)
        sf = int(d.shortfall_wh) if d else 0
        seller_shortfall[t.seller_id] += sf
        if sf > 0:
            seller_buyer_shortfall[t.seller_id][t.buyer_id] += sf

    sellers = sorted({t.seller_id for t in trades})
    if not sellers:
        return
    leaves = [
        shortfall_leaf(interval.id, _addr(db, sid), int(seller_shortfall.get(sid, 0)))
        for sid in sellers
    ]
    for idx, sid in enumerate(sellers):
        sf = int(seller_shortfall.get(sid, 0))
        if sf <= 0:
            continue
        buyers = seller_buyer_shortfall.get(sid, {})
        if not buyers:
            continue
        buyer_id = max(buyers.items(), key=lambda kv: kv[1])[0]
        try:
            client.settle_shortfall(
                interval.id,
                _addr(db, sid),
                sf,
                get_proof(leaves, idx),
                _addr(db, buyer_id),
                db=db,
            )
        except Exception as exc:
            logger.info("shortfall_retry_skip", seller=sid, error=str(exc)[:200])
