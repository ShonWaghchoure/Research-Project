import pytest
from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.schemas.attacks import ATTACK_SCENARIOS
from app.db.models import UserRole
from tests.conftest import login

# Keep attack-lab API tests fast: 12 intervals, 20 participants.
_FAST = {"participants": 20, "days": 1, "seed": 7, "max_intervals": 12}


@pytest.mark.parametrize("scenario", ATTACK_SCENARIOS)
def test_attack_run_shape(
    client: TestClient, seeded_db: Session, admin_account, scenario: str
):
    admin_addr, admin_pk = admin_account
    token = login(client, seeded_db, admin_addr, admin_pk, UserRole.admin)
    headers = {"Authorization": f"Bearer {token}"}

    res = client.post(
        "/admin/attacks/run",
        headers=headers,
        json={"scenario": scenario, "params": _FAST, "defenses": "on"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["scenario"] == scenario
    assert body["defenses"] is True
    assert body["status"] == "completed"
    assert "summary" in body
    assert "series" in body
    assert isinstance(body["series"], list)
    assert len(body["series"]) >= 1
    assert "attacker_profit_paise" in body
    assert isinstance(body["plain_summary"], str) and body["plain_summary"]
    assert body["summary"]["scenario"] == scenario
    assert "market" in body["summary"]
    point = body["series"][0]
    assert "interval" in point


def test_sybil_defenses_reduce_attacker_advantage(
    client: TestClient, seeded_db: Session, admin_account
):
    admin_addr, admin_pk = admin_account
    token = login(client, seeded_db, admin_addr, admin_pk, UserRole.admin)
    headers = {"Authorization": f"Bearer {token}"}
    params = {**_FAST, "participants": 30, "max_intervals": 24, "seed": 42}

    off = client.post(
        "/admin/attacks/run",
        headers=headers,
        json={"scenario": "sybil_farm", "params": params, "defenses": "off"},
    )
    on = client.post(
        "/admin/attacks/run",
        headers=headers,
        json={"scenario": "sybil_farm", "params": params, "defenses": "on"},
    )
    assert off.status_code == 200, off.text
    assert on.status_code == 200, on.text
    off_gain = float(off.json()["attacker_profit_paise"])
    on_gain = float(on.json()["attacker_profit_paise"])
    # With defenses on, Sybil advantage should not exceed defenses-off (soft).
    assert on_gain <= off_gain + 1.0


def test_attack_requires_admin(client: TestClient, seeded_db: Session):
    part = Account.create()
    token = login(
        client, seeded_db, part.address, part.key.hex(), UserRole.participant
    )
    denied = client.post(
        "/admin/attacks/run",
        headers={"Authorization": f"Bearer {token}"},
        json={"scenario": "sybil_farm", "params": _FAST, "defenses": "off"},
    )
    assert denied.status_code == 403
