"""Reputation query endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from eth_utils import is_address, to_checksum_address
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.chain.merkle import build_tree, get_proof
from app.core.config_store import load_market_params
from app.db.deps import get_db
from app.db.models import (
    Interval,
    Participant,
    ReputationEvent,
    ReputationScore,
    User,
)
from app.reputation.score import BetaState, initial_state, reputation
from app.reputation.tiers import Tier, classify, intervals_to_tier, volume_cap_kwh
from app.schemas.market import (
    ReputationComponents,
    ReputationHistoryOut,
    ReputationHistoryPointOut,
    ReputationOut,
    ReputationProofOut,
)

router = APIRouter(tags=["reputation"])


def _user_by_address(db: Session, address: str) -> User:
    if not is_address(address):
        raise HTTPException(status_code=422, detail="invalid Ethereum address")
    checksum = to_checksum_address(address)
    user = db.query(User).filter(User.address == checksum).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="address not found")
    return user


def _participant(db: Session, user: User) -> Participant:
    part = db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="participant not found")
    return part


def _components(
    db: Session,
    participant_id: int,
    interval_id: int | None,
) -> ReputationComponents:
    query = db.query(ReputationEvent).filter(
        ReputationEvent.participant_id == participant_id,
        ReputationEvent.event_type == "score_evidence",
    )
    if interval_id is not None:
        query = query.filter(ReputationEvent.interval_id <= interval_id)
    event = query.order_by(desc(ReputationEvent.interval_id), desc(ReputationEvent.id)).first()
    payload = event.payload if event and isinstance(event.payload, dict) else {}
    return ReputationComponents(
        delivery=float(payload.get("delivery", 1.0)),
        reveal=float(payload.get("reveal", 1.0)),
        honesty=float(payload.get("honesty", 1.0)),
        collusion=float(payload.get("collusion_free", 1.0)),
    )


def _history_point(
    db: Session,
    participant_id: int,
    row: ReputationScore,
    interval: Interval,
) -> ReputationHistoryPointOut:
    return ReputationHistoryPointOut(
        interval_id=row.interval_id,
        ends_at=interval.ends_at,
        score=row.score_bp / 10_000.0,
        score_bp=row.score_bp,
        tier=row.tier,
        evidence_count=row.evidence_count,
        components=_components(db, participant_id, row.interval_id),
    )


@router.get("/reputation/{address}", response_model=ReputationOut)
def get_reputation(address: str, db: Session = Depends(get_db)) -> ReputationOut:
    user = _user_by_address(db, address)
    part = _participant(db, user)
    row = (
        db.query(ReputationScore)
        .filter(ReputationScore.participant_id == part.id)
        .order_by(desc(ReputationScore.interval_id))
        .first()
    )
    if row is None:
        state = initial_state()
        score_bp = int(round(reputation(state) * 10_000))
        evidence_count = 0
        alpha, beta = state.alpha, state.beta
        tier = classify(state).value
        interval_id = 0
        ends_at = user.created_at or datetime.now(timezone.utc)
        leaf_hash = None
    else:
        state = BetaState(
            alpha=row.alpha,
            beta=row.beta,
            evidence_count=row.evidence_count,
        )
        score_bp = row.score_bp
        evidence_count = row.evidence_count
        alpha, beta = row.alpha, row.beta
        tier = row.tier
        interval_id = row.interval_id
        interval = db.get(Interval, row.interval_id)
        ends_at = interval.ends_at if interval is not None else row.created_at
        leaf_hash = row.leaf_hash

    return ReputationOut(
        address=to_checksum_address(user.address),
        interval_id=interval_id,
        ends_at=ends_at,
        score=score_bp / 10_000.0,
        score_bp=score_bp,
        evidence_count=evidence_count,
        tier=tier,
        components=_components(db, part.id, interval_id or None),
        alpha=alpha,
        beta=beta,
        intervals_to_trusted=intervals_to_tier(state, target=Tier.TRUSTED),
        volume_cap_kwh=volume_cap_kwh(load_market_params(db).q_base_kwh, reputation(state)),
        updated_at=row.created_at if row is not None else ends_at,
        leaf_hash=leaf_hash,
    )


@router.get("/reputation/{address}/history", response_model=ReputationHistoryOut)
def reputation_history(
    address: str,
    db: Session = Depends(get_db),
) -> ReputationHistoryOut:
    user = _user_by_address(db, address)
    part = _participant(db, user)
    rows = (
        db.query(ReputationScore)
        .filter(ReputationScore.participant_id == part.id)
        .order_by(ReputationScore.interval_id)
        .all()
    )
    intervals = {
        row.id: row
        for row in db.query(Interval)
        .filter(Interval.id.in_([score.interval_id for score in rows]))
        .all()
    }
    return ReputationHistoryOut(
        address=to_checksum_address(user.address),
        history=[
            _history_point(db, part.id, row, intervals[row.interval_id])
            for row in rows
            if row.interval_id in intervals
        ],
    )


@router.get("/reputation/{address}/proof", response_model=ReputationProofOut)
def reputation_proof(
    address: str,
    interval_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
) -> ReputationProofOut:
    user = _user_by_address(db, address)
    part = _participant(db, user)
    row = (
        db.query(ReputationScore)
        .filter(
            ReputationScore.participant_id == part.id,
            ReputationScore.interval_id == interval_id,
        )
        .one_or_none()
    )
    if row is None or not row.leaf_hash:
        raise HTTPException(status_code=404, detail="score not found for interval")

    scores = (
        db.query(ReputationScore)
        .filter(
            ReputationScore.interval_id == interval_id,
            ReputationScore.leaf_hash.isnot(None),
        )
        .order_by(ReputationScore.participant_id)
        .all()
    )
    leaves = [score.leaf_hash for score in scores if score.leaf_hash]
    try:
        index = next(i for i, score in enumerate(scores) if score.participant_id == part.id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="leaf missing") from exc
    tree = build_tree(leaves)
    return ReputationProofOut(
        address=to_checksum_address(user.address),
        interval_id=interval_id,
        score_bp=row.score_bp,
        evidence_count=row.evidence_count,
        leaf_hash=row.leaf_hash,
        proof=get_proof(leaves, index),
        root=tree.root,
    )
