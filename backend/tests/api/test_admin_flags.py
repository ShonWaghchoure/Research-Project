from datetime import datetime, timezone

from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Flag, FlagSeverity, FlagStatus, Interval, IntervalState, UserRole
from tests.conftest import login


def _interval(db: Session) -> Interval:
    iv = Interval(
        state=IntervalState.METERED,
        starts_at=datetime.now(timezone.utc),
        ends_at=datetime.now(timezone.utc),
    )
    db.add(iv)
    db.flush()
    return iv


def test_flag_queue_list_and_resolve(
    client: TestClient, seeded_db: Session, admin_account
):
    iv = _interval(seeded_db)
    flag = Flag(
        interval_id=iv.id,
        kind="collusion",
        severity=FlagSeverity.high,
        status=FlagStatus.open,
        detail={"c_i": 0.95},
    )
    seeded_db.add(flag)
    seeded_db.flush()

    admin_addr, admin_pk = admin_account
    token = login(client, seeded_db, admin_addr, admin_pk, UserRole.admin)
    headers = {"Authorization": f"Bearer {token}"}

    listed = client.get("/admin/flags", headers=headers)
    assert listed.status_code == 200, listed.text
    rows = listed.json()
    assert any(r["id"] == flag.id and r["status"] == "open" for r in rows)

    resolved = client.post(
        f"/admin/flags/{flag.id}/resolve",
        headers=headers,
        json={"status": "dismissed", "note": "false positive"},
    )
    assert resolved.status_code == 200, resolved.text
    body = resolved.json()
    assert body["status"] == "dismissed"
    assert body["detail"]["resolve_note"] == "false positive"

    part = Account.create()
    part_token = login(
        client, seeded_db, part.address, part.key.hex(), UserRole.participant
    )
    denied = client.get(
        "/admin/flags", headers={"Authorization": f"Bearer {part_token}"}
    )
    assert denied.status_code == 403


def test_simulation_controls(client: TestClient, seeded_db: Session, admin_account):
    from app.workers import sim_control

    # Reset to known state
    sim_control.start()

    admin_addr, admin_pk = admin_account
    token = login(client, seeded_db, admin_addr, admin_pk, UserRole.admin)
    headers = {"Authorization": f"Bearer {token}"}

    got = client.get("/admin/simulation", headers=headers)
    assert got.status_code == 200
    assert got.json()["running"] is True

    stopped = client.post("/admin/simulation/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["running"] is False
    assert sim_control.is_running() is False

    sped = client.put(
        "/admin/simulation/speed",
        headers=headers,
        json={"interval_seconds": 45},
    )
    assert sped.status_code == 200
    assert sped.json()["interval_seconds"] == 45

    started = client.post("/admin/simulation/start", headers=headers)
    assert started.status_code == 200
    assert started.json()["running"] is True

    log = client.get("/admin/audit-log", headers=headers)
    assert log.status_code == 200
    actions = {r["action"] for r in log.json()}
    assert "simulation.stop" in actions
    assert "simulation.speed" in actions
