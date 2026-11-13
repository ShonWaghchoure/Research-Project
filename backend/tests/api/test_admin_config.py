from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config_store import load_market_params
from app.db.models import AuditLog, UserRole
from tests.conftest import login


def test_admin_config_get_put_and_audit(
    client: TestClient, seeded_db: Session, admin_account
):
    admin_addr, admin_pk = admin_account
    admin_token = login(client, seeded_db, admin_addr, admin_pk, UserRole.admin)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    got = client.get("/admin/config", headers=admin_headers)
    assert got.status_code == 200, got.text
    values = got.json()["values"]
    assert values["p_fit"] == 300
    assert values["p_ret"] == 800
    previous_alpha = values["alpha"]

    put = client.put(
        "/admin/config",
        headers=admin_headers,
        json={"values": {"alpha": 0.55}},
    )
    assert put.status_code == 200, put.text
    assert put.json()["values"]["alpha"] == 0.55

    params = load_market_params(seeded_db)
    assert params.alpha == 0.55

    audits = (
        seeded_db.query(AuditLog)
        .filter(AuditLog.action == "config.update")
        .order_by(AuditLog.id.desc())
        .all()
    )
    assert len(audits) >= 1
    assert audits[0].before == {"alpha": previous_alpha}
    assert audits[0].after == {"alpha": 0.55}

    part = Account.create()
    part_token = login(
        client, seeded_db, part.address, part.key.hex(), UserRole.participant
    )
    denied = client.get(
        "/admin/config", headers={"Authorization": f"Bearer {part_token}"}
    )
    assert denied.status_code == 403
    denied_put = client.put(
        "/admin/config",
        headers={"Authorization": f"Bearer {part_token}"},
        json={"values": {"alpha": 0.1}},
    )
    assert denied_put.status_code == 403


def test_unauthenticated_admin_rejected(client: TestClient, seeded_db: Session):
    assert client.get("/admin/config").status_code == 401
