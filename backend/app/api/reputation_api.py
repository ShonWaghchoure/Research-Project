"""Reputation query endpoints."""

from __future__ import annotations

from eth_utils import to_checksum_address
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.chain.merkle import build_tree, get_proof
from app.db.deps import get_db
from app.db.models import Participant, ReputationScore, User
from app.schemas.market import ReputationHistoryOut, ReputationOut, ReputationProofOut

router = APIRouter(tags=["reputation"])


def _user_by_address(db: Session, address: str) -> User:
    checksum = to_checksum_address(address)
    user = db.query(User).filter(User.address == checksum).one_or_none()
    if user is None:
        # try case-insensitive
        user = db.query(User).filter(User.address.ilike(checksum)).one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="address not found")
    return user


def _participant(db: Session, user: User) -> Participant:
    part = db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="participant not found")
    return part


def _score_out(address: str, row: ReputationScore) -> ReputationOut:
    return ReputationOut(
        address=address,
        interval_id=row.interval_id,
        score_bp=row.score_bp,
        evidence_count=row.evidence_count,
        alpha=row.alpha,
        beta=row.beta,
        tier=row.tier,
        leaf_hash=row.leaf_hash,
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
        raise HTTPException(status_code=404, detail="no reputation score")
    return _score_out(to_checksum_address(user.address), row)


@router.get("/reputation/{address}/history", response_model=ReputationHistoryOut)
def reputation_history(address: str, db: Session = Depends(get_db)) -> ReputationHistoryOut:
    user = _user_by_address(db, address)
    part = _participant(db, user)
    rows = (
        db.query(ReputationScore)
        .filter(ReputationScore.participant_id == part.id)
        .order_by(ReputationScore.interval_id)
        .all()
    )
    addr = to_checksum_address(user.address)
    return ReputationHistoryOut(address=addr, history=[_score_out(addr, r) for r in rows])


@router.get("/reputation/{address}/proof", response_model=ReputationProofOut)
def reputation_proof(
    address: str,
    interval_id: int = Query(...),
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

    all_scores = (
        db.query(ReputationScore)
        .filter(ReputationScore.interval_id == interval_id)
        .order_by(ReputationScore.participant_id)
        .all()
    )
    leaves = [s.leaf_hash for s in all_scores if s.leaf_hash]
    try:
        idx = next(i for i, s in enumerate(all_scores) if s.participant_id == part.id)
    except StopIteration as exc:
        raise HTTPException(status_code=404, detail="leaf missing") from exc
    tree = build_tree(leaves)
    proof = get_proof(leaves, idx)
    return ReputationProofOut(
        address=to_checksum_address(user.address),
        interval_id=interval_id,
        score_bp=row.score_bp,
        evidence_count=row.evidence_count,
        leaf_hash=row.leaf_hash,
        proof=proof,
        root=tree.root,
    )
