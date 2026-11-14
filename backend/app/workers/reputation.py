"""Update reputation scores and post Merkle root to ReputationAnchor."""

from __future__ import annotations

from collections import defaultdict

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.chain.client import ChainClient, get_chain_client
from app.chain.merkle import build_tree, reputation_leaf
from app.db.models import (
    Delivery,
    Interval,
    Participant,
    Position,
    ReputationEvent,
    ReputationScore,
    Trade,
    User,
)
from app.reputation.score import (
    BetaState,
    Evidence,
    delivery_ratio,
    initial_state,
    reputation,
    reveal_miss_evidence,
    score_bp,
    update,
)
from app.reputation.tiers import Tier, classify
from app.workers.detection import latest_detection_scores
from app.workers.pubsub import publish_reputation

logger = structlog.get_logger(__name__)


def _prev_score(db: Session, participant_id: int, before_interval_id: int) -> ReputationScore | None:
    return (
        db.query(ReputationScore)
        .filter(
            ReputationScore.participant_id == participant_id,
            ReputationScore.interval_id < before_interval_id,
        )
        .order_by(desc(ReputationScore.interval_id))
        .first()
    )


def run(db: Session, interval: Interval, client: ChainClient | None = None) -> None:
    client = client or get_chain_client()

    existing = (
        db.query(ReputationScore)
        .filter(ReputationScore.interval_id == interval.id)
        .count()
    )
    if existing > 0:
        # Still ensure root posted (idempotent). Sort by participant_id so the
        # leaf order matches /reputation/{address}/proof.
        scores = (
            db.query(ReputationScore)
            .filter(ReputationScore.interval_id == interval.id)
            .order_by(ReputationScore.participant_id)
            .all()
        )
        if scores and scores[0].leaf_hash:
            leaves = [s.leaf_hash for s in scores if s.leaf_hash]
            if leaves:
                root = build_tree(leaves).root
                try:
                    client.post_reputation_root(interval.id, root, db=db)
                except Exception as exc:
                    logger.info("rep_root_already_or_failed", error=str(exc))
            logger.info("reputation_skip_scores_exist", interval_id=interval.id)
            return

    participants = (
        db.query(Participant)
        .filter(Participant.active.is_(True))
        .order_by(Participant.id)
        .all()
    )
    trades = db.query(Trade).filter(Trade.interval_id == interval.id).all()
    deliveries = db.query(Delivery).filter(Delivery.interval_id == interval.id).all()
    del_by_trade = {d.trade_id: d for d in deliveries}

    promised: dict[int, int] = defaultdict(int)
    delivered: dict[int, int] = defaultdict(int)
    volume: dict[int, float] = defaultdict(float)
    for t in trades:
        d = del_by_trade.get(t.id)
        dw = d.delivered_wh if d else t.qty_wh
        promised[t.seller_id] += t.qty_wh
        delivered[t.seller_id] += dw
        volume[t.seller_id] += t.qty_wh / 1000.0
        volume[t.buyer_id] += t.qty_wh / 1000.0

    reveal_misses = {
        e.participant_id
        for e in db.query(ReputationEvent)
        .filter(
            ReputationEvent.interval_id == interval.id,
            ReputationEvent.event_type == "reveal_miss",
        )
        .all()
    }
    positions = db.query(Position).filter(Position.interval_id == interval.id).all()
    revealed_ids = {p.participant_id for p in positions if p.revealed}
    committed_ids = {p.participant_id for p in positions if p.commit_hash}

    leaves: list[str] = []
    leaf_order: list[ReputationScore] = []

    for part in participants:
        prev = _prev_score(db, part.id, interval.id)
        if prev is None:
            state = initial_state()
            prev_tier = None
        else:
            state = BetaState(alpha=prev.alpha, beta=prev.beta, evidence_count=prev.evidence_count)
            try:
                prev_tier = Tier(prev.tier)
            except ValueError:
                prev_tier = None

        c_i, a_i = latest_detection_scores(db, part.id)

        if part.id in reveal_misses or (
            part.id in committed_ids and part.id not in revealed_ids
        ):
            ev: Evidence | None = reveal_miss_evidence(anomaly=a_i, collusion=c_i)
        elif part.id in volume or part.id in promised:
            r_del = delivery_ratio(promised.get(part.id, 0), delivered.get(part.id, 0))
            r_rev = 1.0 if part.id in revealed_ids else 1.0
            # Buyers who revealed: r_del = 1 (nothing promised as seller)
            if part.id not in promised:
                r_del = 1.0
            ev = Evidence(
                r_del=r_del,
                r_rev=r_rev,
                anomaly=a_i,
                collusion=c_i,
                volume_kwh=volume.get(part.id, 0.0),
            )
        elif part.id in committed_ids:
            ev = Evidence(
                r_del=1.0,
                r_rev=1.0 if part.id in revealed_ids else 0.0,
                anomaly=a_i,
                collusion=c_i,
            )
        else:
            ev = None  # idle decay

        new_state = update(state, ev)
        tier = classify(new_state, prev_tier=prev_tier)
        r = reputation(new_state)
        bp = score_bp(r)

        user = db.get(User, part.user_id)
        addr = user.address if user else "0x0000000000000000000000000000000000000000"
        leaf = reputation_leaf(addr, bp, new_state.evidence_count)

        row = ReputationScore(
            participant_id=part.id,
            interval_id=interval.id,
            score_bp=bp,
            evidence_count=new_state.evidence_count,
            alpha=new_state.alpha,
            beta=new_state.beta,
            tier=tier.value,
            leaf_hash=leaf,
        )
        db.add(row)
        leaf_order.append(row)
        leaves.append(leaf)

    db.flush()
    if not leaves:
        logger.warning("reputation_no_participants", interval_id=interval.id)
        db.commit()
        return

    tree = build_tree(leaves)
    db.commit()

    client.post_reputation_root(interval.id, tree.root, db=db)
    publish_reputation(
        {
            "interval_id": interval.id,
            "root": tree.root,
            "count": len(leaves),
        }
    )
    logger.info("reputation_done", interval_id=interval.id, root=tree.root, n=len(leaves))
