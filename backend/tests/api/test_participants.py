from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import UserRole
from tests.conftest import login


def test_create_and_patch_participant(client: TestClient, seeded_db: Session):
    acct = Account.create()
    token = login(client, seeded_db, acct.address, acct.key.hex(), UserRole.participant)
    headers = {"Authorization": f"Bearer {token}"}

    created = client.post(
        "/participants",
        headers=headers,
        json={
            "type": "prosumer",
            "feeder_node_id": "n4",
            "display_name": "alice",
            "pv_capacity_kw": 5.0,
            "battery_kwh": 10.0,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["type"] == "prosumer"
    assert body["feeder_node_id"] == "n4"
    assert body["pv_capacity_kw"] == 5.0
    pid = body["id"]

    me = client.get("/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["participant"]["id"] == pid

    patched = client.patch(
        f"/participants/{pid}", headers=headers, json={"display_name": "alice-2"}
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["display_name"] == "alice-2"

    # Security fix: equipment and feeder node are admin-only after creation, because the
    # false-report detector checks readings against declared capacity.
    for field, value in (("battery_kwh", 12.5), ("pv_capacity_kw", 1000), ("feeder_node_id", "n5")):
        r = client.patch(f"/participants/{pid}", headers=headers, json={field: value})
        assert r.status_code == 403, (field, r.text)

    admin = Account.create()
    admin_token = login(client, seeded_db, admin.address, admin.key.hex(), UserRole.admin)
    by_admin = client.patch(
        f"/participants/{pid}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"battery_kwh": 12.5},
    )
    assert by_admin.status_code == 200, by_admin.text
    assert by_admin.json()["battery_kwh"] == 12.5

    from app.db.models import AuditLog

    logs = seeded_db.query(AuditLog).filter(AuditLog.action == "participant.update").all()
    assert {tuple(sorted(log.after)) for log in logs} == {("display_name",), ("battery_kwh",)}


def test_validation_errors(client: TestClient, seeded_db: Session):
    acct = Account.create()
    token = login(client, seeded_db, acct.address, acct.key.hex(), UserRole.participant)
    headers = {"Authorization": f"Bearer {token}"}

    bad = client.post(
        "/participants",
        headers=headers,
        json={
            "type": "consumer",
            "feeder_node_id": "n4",
            "pv_capacity_kw": 2.0,
        },
    )
    assert bad.status_code == 422

    bad_ev = client.post(
        "/participants",
        headers=headers,
        json={"type": "ev", "feeder_node_id": "n4"},
    )
    assert bad_ev.status_code == 422

    bad_node = client.post(
        "/participants",
        headers=headers,
        json={"type": "consumer", "feeder_node_id": "n999"},
    )
    assert bad_node.status_code == 422
    detail = bad_node.json()["detail"]
    detail_s = detail if isinstance(detail, str) else str(detail)
    assert "feeder_node" in detail_s.lower()


def test_duplicate_participant_conflict(client: TestClient, seeded_db: Session):
    acct = Account.create()
    token = login(client, seeded_db, acct.address, acct.key.hex(), UserRole.participant)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"type": "consumer", "feeder_node_id": "n4"}
    assert client.post("/participants", headers=headers, json=payload).status_code == 201
    again = client.post("/participants", headers=headers, json=payload)
    assert again.status_code == 409
