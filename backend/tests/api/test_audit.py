from datetime import datetime, timezone

from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api import audit_service
from app.db.models import (
    Interval,
    IntervalState,
    Participant,
    ParticipantType,
    Position,
    PositionSide,
    Trade,
    User,
    UserRole,
)
from app.workers.clearing import run as clearing_run
from tests.conftest import login


class _CommittedChain:
    """Stub chain where every position's commit is on chain (hashes are fabricated)."""

    def is_reachable(self) -> bool:
        return True

    def on_chain_commit(self, interval_id: int, participant: str) -> str | None:
        return {"0x" + "22" * 20: "0x" + "ab" * 32, "0x" + "33" * 20: "0x" + "cd" * 32}.get(participant.lower())

    class _Call:
        def call(self) -> int:
            return 10**12  # ample escrow

    class _Fns:
        def escrow(self, _addr: str) -> "_CommittedChain._Call":
            return _CommittedChain._Call()

    settlement = type("S", (), {"functions": _Fns()})()


def _seed_cleared_interval(db: Session) -> Interval:
    """Two revealed positions that clear to a deterministic result."""
    admin = User(address="0x" + "11" * 20, role=UserRole.admin, nonce_used=True)
    buyer_u = User(address="0x" + "22" * 20, role=UserRole.participant, nonce_used=True)
    seller_u = User(address="0x" + "33" * 20, role=UserRole.participant, nonce_used=True)
    db.add_all([admin, buyer_u, seller_u])
    db.flush()

    buyer = Participant(
        user_id=buyer_u.id,
        type=ParticipantType.consumer,
        feeder_node_id="n1",
        display_name="buyer",
    )
    seller = Participant(
        user_id=seller_u.id,
        type=ParticipantType.prosumer,
        feeder_node_id="n2",
        display_name="seller",
        pv_capacity_w=5000,
    )
    db.add_all([buyer, seller])
    db.flush()

    iv = Interval(
        state=IntervalState.CLEARING,
        starts_at=datetime.now(timezone.utc),
        ends_at=datetime.now(timezone.utc),
    )
    db.add(iv)
    db.flush()

    db.add_all(
        [
            Position(
                participant_id=buyer.id,
                interval_id=iv.id,
                side=PositionSide.buy,
                qty_wh=2000,
                limit_price_paise=800,
                revealed=True,
                commit_hash="0x" + "ab" * 32,
            ),
            Position(
                participant_id=seller.id,
                interval_id=iv.id,
                side=PositionSide.sell,
                qty_wh=2000,
                limit_price_paise=300,
                revealed=True,
                commit_hash="0x" + "cd" * 32,
            ),
        ]
    )
    db.flush()
    clearing_run(db, iv, client=_CommittedChain())
    db.refresh(iv)
    assert iv.result_hash is not None
    assert iv.input_root is not None
    return iv


def test_audit_get_and_rerun_match(
    client: TestClient, seeded_db: Session, admin_account
):
    iv = _seed_cleared_interval(seeded_db)

    # Public GET
    got = client.get(f"/audit/{iv.id}")
    assert got.status_code == 200, got.text
    report = got.json()
    assert report["interval_id"] == iv.id
    assert report["input_root"]["stored"] == iv.input_root.lower()
    # Security fix: the result hash is reproducible from the published integer trades.
    assert report["result_hash"]["stored_matches_recomputed"] is True
    assert len(report["positions"]) == 2
    assert len(report["merkle_leaves"]) == 2

    admin_addr, admin_pk = admin_account
    token = login(client, seeded_db, admin_addr, admin_pk, UserRole.admin)
    headers = {"Authorization": f"Bearer {token}"}

    rerun = client.post(f"/audit/{iv.id}/rerun", headers=headers)
    assert rerun.status_code == 200, rerun.text
    body = rerun.json()
    assert body["match"] is True
    assert body["input_root"]["stored_matches_recomputed"] is True
    assert body["result_hash"]["stored_matches_recomputed"] is True

    # Direct service check
    again = audit_service.rerun_audit(seeded_db, iv)
    assert again["match"] is True


def test_audit_rerun_requires_operator(
    client: TestClient, seeded_db: Session
):
    iv = _seed_cleared_interval(seeded_db)
    part = Account.create()
    token = login(
        client, seeded_db, part.address, part.key.hex(), UserRole.participant
    )
    denied = client.post(
        f"/audit/{iv.id}/rerun",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert denied.status_code == 403


def test_audit_withholds_bids_until_reveal_window_closes(client: TestClient, db: Session):
    """Security fix: during COMMIT/REVEAL the audit endpoint must not publish revealed
    bids, or late revealers could see everyone's price before deciding to reveal."""
    for state in (IntervalState.OPEN, IntervalState.COMMIT, IntervalState.REVEAL):
        iv = Interval(state=state, starts_at=datetime.now(timezone.utc), ends_at=datetime.now(timezone.utc))
        db.add(iv)
        db.flush()
        r = client.get(f"/audit/{iv.id}")
        assert r.status_code == 409, (state, r.text)
        assert "positions" not in r.json()



def test_clearing_drops_revealed_positions_without_onchain_commit(seeded_db: Session):
    """Security fix: a position marked revealed in the DB but never committed on chain
    (e.g. its commitPosition reverted) must not clear; it is a reveal miss instead."""
    from app.db.models import ReputationEvent

    class _OnlyBuyerCommitted(_CommittedChain):
        def on_chain_commit(self, interval_id: int, participant: str) -> str | None:
            return "0x" + "ab" * 32 if participant.lower() == "0x" + "22" * 20 else None

    iv = Interval(state=IntervalState.CLEARING, starts_at=datetime.now(timezone.utc), ends_at=datetime.now(timezone.utc))
    users = [User(address="0x" + c * 20, role=UserRole.participant, nonce_used=True) for c in ("22", "33")]
    seeded_db.add_all([iv, *users])
    seeded_db.flush()
    buyer = Participant(user_id=users[0].id, type=ParticipantType.consumer, feeder_node_id="n1")
    seller = Participant(user_id=users[1].id, type=ParticipantType.prosumer, feeder_node_id="n2", pv_capacity_w=5000)
    seeded_db.add_all([buyer, seller])
    seeded_db.flush()
    seeded_db.add_all([
        Position(participant_id=buyer.id, interval_id=iv.id, side=PositionSide.buy, qty_wh=2000,
                 limit_price_paise=800, revealed=True, commit_hash="0x" + "ab" * 32),
        Position(participant_id=seller.id, interval_id=iv.id, side=PositionSide.sell, qty_wh=2000,
                 limit_price_paise=300, revealed=True, commit_hash="0x" + "cd" * 32),
    ])
    seeded_db.flush()
    clearing_run(seeded_db, iv, client=_OnlyBuyerCommitted())
    assert seeded_db.query(Trade).filter(Trade.interval_id == iv.id).count() == 0
    miss = seeded_db.query(ReputationEvent).filter(
        ReputationEvent.interval_id == iv.id, ReputationEvent.participant_id == seller.id
    ).one()
    assert miss.event_type == "reveal_miss" and miss.payload["reason"] == "no matching on-chain commit"


def test_buy_is_capped_by_onchain_escrow(seeded_db: Session):
    """Bug fix: an unfunded buyer used to clear in full and then revert the whole settle
    batch. Buys are now capped at what on-chain escrow can pay at the buyer's limit."""

    class _SmallEscrow(_CommittedChain):
        class _Fns:
            def escrow(self, _addr: str):  # noqa: ANN202
                return type("C", (), {"call": lambda self: 800})()  # ₹8.00 covers 1 kWh at ₹8

        settlement = type("S", (), {"functions": _Fns()})()

    iv = Interval(state=IntervalState.CLEARING, starts_at=datetime.now(timezone.utc), ends_at=datetime.now(timezone.utc))
    users = [User(address="0x" + c * 20, role=UserRole.participant, nonce_used=True) for c in ("22", "33")]
    seeded_db.add_all([iv, *users])
    seeded_db.flush()
    buyer = Participant(user_id=users[0].id, type=ParticipantType.consumer, feeder_node_id="n1")
    seller = Participant(user_id=users[1].id, type=ParticipantType.prosumer, feeder_node_id="n2", pv_capacity_w=5000)
    seeded_db.add_all([buyer, seller])
    seeded_db.flush()
    seeded_db.add_all([
        Position(participant_id=buyer.id, interval_id=iv.id, side=PositionSide.buy, qty_wh=2000,
                 limit_price_paise=800, revealed=True, commit_hash="0x" + "ab" * 32),
        Position(participant_id=seller.id, interval_id=iv.id, side=PositionSide.sell, qty_wh=2000,
                 limit_price_paise=300, revealed=True, commit_hash="0x" + "cd" * 32),
    ])
    seeded_db.flush()
    clearing_run(seeded_db, iv, client=_SmallEscrow())
    bought = sum(t.qty_wh for t in seeded_db.query(Trade).filter(Trade.interval_id == iv.id))
    assert 0 < bought <= 1000


def test_audit_rerun_still_matches_after_profile_and_config_changes(
    client: TestClient, seeded_db: Session, admin_account
):
    """Bug fix: re-runs used current profiles and config, so a later node change, an
    inactive flag or an alpha tweak made honest past intervals look tampered with."""
    from app.core.config_store import update_config

    iv = _seed_cleared_interval(seeded_db)
    assert iv.clearing_inputs and len(iv.clearing_inputs["positions"]) == 2

    for part in seeded_db.query(Participant).all():
        part.feeder_node_id = "n5"
        part.active = False
    update_config(seeded_db, {"alpha": 0.33, "k": 3}, updated_by=None)
    seeded_db.flush()

    again = audit_service.rerun_audit(seeded_db, iv)
    assert again["match"] is True
    assert again["input_root"]["stored_matches_recomputed"] is True
