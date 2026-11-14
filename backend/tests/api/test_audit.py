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
    User,
    UserRole,
)
from app.workers.clearing import run as clearing_run
from tests.conftest import login


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
    clearing_run(db, iv)
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
