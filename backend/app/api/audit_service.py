"""Audit helpers: published inputs/results and deterministic engine re-run."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.chain.client import ChainClient, get_chain_client
from app.core.config import settings
from app.core.config_store import load_market_params
from app.db.models import Interval, Participant, Position, PositionSide, ReputationScore, Trade
from app.engine.clearing import clear_interval
from app.engine.hashing import canonical_json, input_root, keccak256, result_hash
from app.engine.pricing import Position as EngPosition
from app.reputation.score import BetaState, initial_state, reputation
from app.reputation.tiers import Tier, classify, matching_reputation, volume_cap_kwh
from app.workers.clearing import engine_version
from app.workers.feeder_load import load_feeder


def _rep_before(db: Session, participant_id: int, before_interval_id: int) -> tuple[BetaState, Tier | None]:
    row = (
        db.query(ReputationScore)
        .filter(
            ReputationScore.participant_id == participant_id,
            ReputationScore.interval_id < before_interval_id,
        )
        .order_by(desc(ReputationScore.interval_id))
        .first()
    )
    if row is None:
        return initial_state(), None
    try:
        prev = Tier(row.tier)
    except ValueError:
        prev = None
    return BetaState(alpha=row.alpha, beta=row.beta, evidence_count=row.evidence_count), prev


def build_engine_positions(db: Session, interval: Interval) -> list[EngPosition]:
    """Rebuild the engine positions that clearing would have used (reputation as-of then)."""
    positions = (
        db.query(Position)
        .filter(Position.interval_id == interval.id, Position.revealed.is_(True))
        .all()
    )
    eng: list[EngPosition] = []
    for pos in positions:
        part = db.get(Participant, pos.participant_id)
        if part is None or not part.active:
            continue
        state, prev_tier = _rep_before(db, pos.participant_id, interval.id)
        tier = classify(state, prev_tier=prev_tier)
        r_match = matching_reputation(state, tier)
        qty_kwh = pos.qty_wh / 1000.0
        r_true = reputation(state)
        cap = volume_cap_kwh(qty_kwh, r_true)
        qty_kwh = min(qty_kwh, cap)
        eng.append(
            EngPosition(
                participant_id=str(pos.participant_id),
                side="buy" if pos.side == PositionSide.buy else "sell",
                qty_kwh=qty_kwh,
                limit_price=float(pos.limit_price_paise),
                reputation=r_match,
                node_id=part.feeder_node_id,
            )
        )
    return eng


def merkle_leaf_records(positions: list[EngPosition]) -> list[dict[str, Any]]:
    records = sorted(
        (
            {
                "participant_id": p.participant_id,
                "side": p.side,
                "qty_kwh": float(p.qty_kwh),
                "limit_price": float(p.limit_price),
                "reputation": float(p.reputation),
                "node_id": getattr(p, "node_id", "n0"),
                "min_seller_reputation": float(getattr(p, "min_seller_reputation", 0.0)),
            }
            for p in positions
        ),
        key=lambda r: (r["participant_id"], r["side"], r["qty_kwh"], r["limit_price"]),
    )
    out: list[dict[str, Any]] = []
    for r in records:
        leaf = "0x" + keccak256(canonical_json(r)).hex()
        out.append({**r, "leaf": leaf})
    return out


def _norm(h: Optional[str]) -> Optional[str]:
    if not h:
        return None
    hx = h.lower()
    return hx if hx.startswith("0x") else "0x" + hx


def _triple(stored: Optional[str], recomputed: Optional[str], on_chain: Optional[str]) -> dict[str, Any]:
    s, r, o = _norm(stored), _norm(recomputed), _norm(on_chain)
    return {
        "stored": s,
        "recomputed": r,
        "on_chain": o,
        "stored_matches_recomputed": (s == r) if s and r else None,
        "stored_matches_on_chain": (s == o) if s and o else None,
        "recomputed_matches_on_chain": (r == o) if r and o else None,
    }


def explorer_links(interval_id: int, client: ChainClient | None = None) -> dict[str, Optional[str]]:
    chain_id = settings.CHAIN_ID
    if chain_id == 31337:
        # Local Hardhat — no public block explorer.
        settlement = settings.SETTLEMENT_ADDRESS
        return {
            "network": "localhost",
            "settlement": settlement,
            "interval_hint": f"Settlement.intervals({interval_id})",
            "block_explorer": None,
        }
    if chain_id == 11155111:
        settlement = settings.SETTLEMENT_ADDRESS
        return {
            "network": "sepolia",
            "settlement": settlement,
            "block_explorer": f"https://sepolia.etherscan.io/address/{settlement}" if settlement else None,
            "interval_hint": f"Settlement.intervals({interval_id})",
        }
    return {"network": str(chain_id), "block_explorer": None, "settlement": settings.SETTLEMENT_ADDRESS}


def get_audit(db: Session, interval: Interval, client: ChainClient | None = None) -> dict[str, Any]:
    client = client or get_chain_client()
    positions = (
        db.query(Position)
        .filter(Position.interval_id == interval.id, Position.revealed.is_(True))
        .order_by(Position.participant_id)
        .all()
    )
    trades = db.query(Trade).filter(Trade.interval_id == interval.id).all()
    eng = build_engine_positions(db, interval)

    on_input: Optional[str] = None
    on_result: Optional[str] = None
    try:
        if client.is_reachable() and client.on_chain_interval_opened(interval.id):
            on_input = client.on_chain_input_root(interval.id)
            on_result = client.on_chain_result_hash(interval.id)
    except Exception:
        on_input = None
        on_result = None

    return {
        "interval_id": interval.id,
        "state": interval.state.value,
        "engine_version": interval.engine_version,
        "p_ref_paise": interval.p_ref_paise,
        "sdr": interval.sdr,
        "positions": [
            {
                "participant_id": p.participant_id,
                "side": p.side.value,
                "qty_wh": p.qty_wh,
                "limit_price_paise": p.limit_price_paise,
                "revealed": p.revealed,
            }
            for p in positions
        ],
        "trades": [
            {
                "buyer_id": t.buyer_id,
                "seller_id": t.seller_id,
                "qty_wh": t.qty_wh,
                "price_paise": t.price_paise,
            }
            for t in trades
        ],
        "input_root": _triple(interval.input_root, input_root(eng) if eng else None, on_input),
        "result_hash": _triple(interval.result_hash, None, on_result),
        "merkle_leaves": merkle_leaf_records(eng),
        "explorer": explorer_links(interval.id, client),
    }


def rerun_audit(db: Session, interval: Interval, client: ChainClient | None = None) -> dict[str, Any]:
    """Re-run clear_interval with reputation as-of the original clearing and compare hashes."""
    client = client or get_chain_client()
    if interval.result_hash is None:
        raise ValueError("interval has not been cleared yet")

    params = load_market_params(db)
    feeder = load_feeder(db)
    eng = build_engine_positions(db, interval)

    prev_p: Optional[float] = None
    prev_iv = (
        db.query(Interval)
        .filter(Interval.id < interval.id, Interval.p_ref_paise.isnot(None))
        .order_by(desc(Interval.id))
        .first()
    )
    if prev_iv is not None and prev_iv.p_ref_paise is not None:
        prev_p = float(prev_iv.p_ref_paise)

    result = clear_interval(eng, feeder, params, prev_p)

    on_input: Optional[str] = None
    on_result: Optional[str] = None
    try:
        if client.is_reachable() and client.on_chain_interval_opened(interval.id):
            on_input = client.on_chain_input_root(interval.id)
            on_result = client.on_chain_result_hash(interval.id)
    except Exception:
        pass

    # Also compute result_hash from stored trades for a second view — primary is engine re-run.
    stored_trades_view = [
        type("T", (), {"buyer_id": str(t.buyer_id), "seller_id": str(t.seller_id), "qty_wh": t.qty_wh, "price": float(t.price_paise)})()
        for t in db.query(Trade).filter(Trade.interval_id == interval.id).all()
    ]
    _ = result_hash(stored_trades_view, float(interval.p_ref_paise or 0))  # available if needed

    input_t = _triple(interval.input_root, result.input_root, on_input)
    result_t = _triple(interval.result_hash, result.result_hash, on_result)
    match = bool(input_t["stored_matches_recomputed"] and result_t["stored_matches_recomputed"])

    note = ""
    if interval.engine_version and interval.engine_version != engine_version():
        note = (
            f"Stored engine_version={interval.engine_version} differs from current "
            f"{engine_version()}; hashes may diverge if clearing code changed."
        )

    return {
        "interval_id": interval.id,
        "engine_version_stored": interval.engine_version,
        "engine_version_now": engine_version(),
        "input_root": input_t,
        "result_hash": result_t,
        "match": match,
        "note": note,
    }
