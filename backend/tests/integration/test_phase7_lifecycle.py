"""Phase 7 integration smoke: 3 consecutive demo intervals with bots.

Requires live postgres, redis, and Hardhat with deployed contracts.
Run: DEMO_MODE=1 INTERVAL_SECONDS=20 pytest tests/integration/test_phase7_lifecycle.py -v -s
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from eth_utils import to_checksum_address
from hexbytes import HexBytes
from sqlalchemy.orm import Session

# Must set before importing app modules that read settings / start scheduler.
os.environ.setdefault("TESTING", "0")
os.environ["DEMO_MODE"] = "1"
os.environ["DEMO_BOT_COUNT"] = "10"
os.environ["INTERVAL_SECONDS"] = "45"
os.environ["CHAIN_CONFIRMATIONS"] = "1"

pytestmark = pytest.mark.integration


def _hardhat_up() -> bool:
    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider("http://127.0.0.1:8545", request_kwargs={"timeout": 2}))
        return bool(w3.is_connected())
    except Exception:
        return False


def _deployments_ok() -> bool:
    path = Path(__file__).resolve().parents[3] / "contracts" / "deployments" / "localhost.json"
    if not path.is_file():
        return False
    import json

    raw = json.loads(path.read_text())
    return bool(raw.get("Settlement") and raw.get("ReputationAnchor"))


requires_stack = pytest.mark.skipif(
    not _hardhat_up() or not _deployments_ok(),
    reason="Hardhat + deployments required for Phase 7 integration",
)


@requires_stack
def test_three_intervals_with_bots() -> None:
    from app.core.config import settings

    # Mutate the shared settings object (workers hold a reference to it).
    object.__setattr__(settings, "DEMO_MODE", True)
    object.__setattr__(settings, "DEMO_BOT_COUNT", 10)
    object.__setattr__(settings, "INTERVAL_SECONDS", 45)
    object.__setattr__(settings, "CHAIN_CONFIRMATIONS", 1)

    import app.chain.client as chain_mod
    from app.chain.client import ChainClient
    from app.chain.merkle import build_tree, get_proof, verify_proof
    from app.db.hardhat_accounts import HARDHAT_ACCOUNTS
    from app.db.models import (
        Delivery,
        Interval,
        IntervalState,
        MeterReading,
        Participant,
        Position,
        ReputationEvent,
        ReputationScore,
        Trade,
        Transaction,
        User,
    )
    from app.db.seed import run_seed
    from app.db.session import SessionLocal
    from app.workers import bots, clock, listener

    # Fresh seed (idempotent)
    run_seed()

    # Clear prior intervals for a clean run (keep users/participants)
    db: Session = SessionLocal()
    try:
        db.query(Delivery).delete()
        db.query(Trade).delete()
        db.query(ReputationScore).delete()
        db.query(MeterReading).delete()
        db.query(ReputationEvent).delete()
        db.query(Position).delete()
        db.query(Interval).delete()
        db.query(Transaction).delete()
        db.commit()
    finally:
        db.close()

    chain_mod._client = None
    client = ChainClient()
    assert client.is_reachable(), "chain unreachable"

    # Fund/register bots before the first openInterval so setup txs do not
    # consume the commit window via Hardhat's +1s/block rule.
    bots.ensure_bots_ready(client=client)

    deadline = time.time() + 420  # 45s * 3 intervals + open headroom + slack
    metered_ids: list[int] = []
    while time.time() < deadline and len(metered_ids) < 3:
        clock.tick(client=client)
        bots.tick(client=client)
        listener.tick(client=client)
        db = SessionLocal()
        try:
            done = (
                db.query(Interval)
                .filter(
                    Interval.state == IntervalState.METERED,
                    Interval.delivery_root.isnot(None),
                    Interval.result_hash.isnot(None),
                )
                .order_by(Interval.id)
                .all()
            )
            metered_ids = [i.id for i in done]
        finally:
            db.close()
        time.sleep(0.4)

    assert len(metered_ids) >= 3, f"expected 3 metered intervals, got {metered_ids}"

    db = SessionLocal()
    try:
        for iid in metered_ids[:3]:
            iv = db.get(Interval, iid)
            assert iv is not None
            assert iv.result_hash
            assert iv.input_root
            assert iv.delivery_root
            assert iv.p_ref_paise is not None

            trades = db.query(Trade).filter(Trade.interval_id == iid).all()
            assert len(trades) > 0, f"interval {iid} produced no trades"

            onchain = client.on_chain_result_hash(iid)
            assert onchain is not None
            db_hx = iv.result_hash.lower().removeprefix("0x")
            chain_hx = onchain.lower().removeprefix("0x")
            assert chain_hx == db_hx, (
                f"result hash mismatch iv={iid} db={iv.result_hash} chain={onchain}"
            )

            # Escrow consistency: settlement escrow mapping is non-negative
            for t in trades:
                for pid in (t.buyer_id, t.seller_id):
                    part = db.get(Participant, pid)
                    assert part is not None
                    user = db.get(User, part.user_id)
                    assert user is not None
                    bal = int(
                        client.settlement.functions.escrow(
                            to_checksum_address(user.address)
                        ).call()
                    )
                    assert bal >= 0

        # Lazy bot: last demo bot account — reputation dropped + stake slashed
        lazy_acct = HARDHAT_ACCOUNTS[2 + 10 - 1]  # DEMO_BOT_COUNT=10 → index 11
        lazy_addr = to_checksum_address(lazy_acct.address)
        lazy_user = db.query(User).filter(User.address == lazy_addr).one()
        lazy_part = db.query(Participant).filter(Participant.user_id == lazy_user.id).one()
        assert lazy_part.display_name and "lazy" in lazy_part.display_name.lower()

        scores = (
            db.query(ReputationScore)
            .filter(ReputationScore.participant_id == lazy_part.id)
            .order_by(ReputationScore.interval_id)
            .all()
        )
        assert len(scores) >= 1
        # score_bp should be below a fresh prior (initial ~3333 bp for Beta(1,2))
        assert scores[-1].score_bp < 4000

        stake = int(client.registry.functions.getParticipant(lazy_addr).call()[0])
        assert stake < 10_000, f"expected slash, stake still {stake}"

        # Merkle proof verifies against on-chain ReputationAnchor root
        proof_iv = metered_ids[2]

        all_scores = (
            db.query(ReputationScore)
            .filter(ReputationScore.interval_id == proof_iv)
            .order_by(ReputationScore.participant_id)
            .all()
        )
        leaves = [s.leaf_hash for s in all_scores if s.leaf_hash]
        idx = next(i for i, s in enumerate(all_scores) if s.participant_id == lazy_part.id)
        leaf = all_scores[idx].leaf_hash
        assert leaf
        proof = get_proof(leaves, idx)
        tree = build_tree(leaves)
        assert verify_proof(leaf, proof, tree.root)

        onchain_root_hex = client.on_chain_reputation_root(proof_iv)
        assert onchain_root_hex is not None
        assert onchain_root_hex.lower().removeprefix("0x") == tree.root.lower().removeprefix(
            "0x"
        )

        ok = client.reputation_anchor.functions.verifyScore(
            proof_iv,
            lazy_addr,
            int(all_scores[idx].score_bp),
            int(all_scores[idx].evidence_count),
            [HexBytes(p) for p in proof],
        ).call()
        assert ok is True
    finally:
        db.close()
