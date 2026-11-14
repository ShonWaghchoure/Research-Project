"""Position commit / reveal: bounds, client salt, reveal window and on-chain commit checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from eth_account import Account
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.chain.commit import compute_commit_hash
from app.db.models import Interval, IntervalState, UserRole
from tests.conftest import login


class _FakeChain:
    def __init__(self, reachable: bool = True, commit: str | None = None) -> None:
        self.reachable = reachable
        self.commit = commit

    def is_reachable(self) -> bool:
        return self.reachable

    def on_chain_commit(self, interval_id: int, participant: str) -> str | None:
        return self.commit


@pytest.fixture()
def interval(seeded_db: Session) -> Interval:
    now = datetime.now(timezone.utc)
    iv = Interval(state=IntervalState.COMMIT, starts_at=now - timedelta(seconds=10), ends_at=now + timedelta(minutes=15))
    seeded_db.add(iv)
    seeded_db.flush()
    return iv


def _participant(client: TestClient, db: Session, ptype: str = "prosumer", pv_kw: float = 4, battery_kwh: float = 5):
    acct = Account.create()
    token = login(client, db, acct.address, acct.key.hex(), UserRole.participant)
    h = {"Authorization": f"Bearer {token}"}
    r = client.post(
        "/participants",
        json={"type": ptype, "feeder_node_id": "n4", "pv_capacity_kw": pv_kw, "battery_kwh": battery_kwh},
        headers=h,
    )
    assert r.status_code == 201, r.text
    return acct, h


def test_limit_price_must_be_inside_tariff_band(client, seeded_db, interval):
    _, h = _participant(client, seeded_db)
    for price in (1, 299, 801):
        r = client.post("/positions", json={"side": "buy", "qty_wh": 1000, "limit_price_paise": price}, headers=h)
        assert r.status_code == 422, (price, r.text)
    ok = client.post("/positions", json={"side": "buy", "qty_wh": 1000, "limit_price_paise": 300}, headers=h)
    assert ok.status_code == 201, ok.text


def test_consumer_cannot_sell_and_prosumer_sell_is_capped(client, seeded_db, interval):
    _, consumer = _participant(client, seeded_db, ptype="consumer", pv_kw=0, battery_kwh=0)
    r = client.post("/positions", json={"side": "sell", "qty_wh": 1, "limit_price_paise": 500}, headers=consumer)
    assert r.status_code == 422 and "exceeds" in r.json()["detail"]

    # 4 kW PV over 0.25 h = 1000 Wh, plus a 5 kWh battery = 6000 Wh.
    _, prosumer = _participant(client, seeded_db, pv_kw=4, battery_kwh=5)
    too_much = client.post("/positions", json={"side": "sell", "qty_wh": 6001, "limit_price_paise": 500}, headers=prosumer)
    assert too_much.status_code == 422
    ok = client.post("/positions", json={"side": "sell", "qty_wh": 6000, "limit_price_paise": 500}, headers=prosumer)
    assert ok.status_code == 201, ok.text


def test_absurd_values_are_422_not_500(client, seeded_db, interval):
    _, h = _participant(client, seeded_db)
    for body in (
        {"side": "sell", "qty_wh": 2_000_000_000, "limit_price_paise": 1},
        {"side": "buy", "qty_wh": 1000, "limit_price_paise": 2**40},
        {"side": "buy", "qty_wh": 1000, "limit_price_paise": 500, "deadline": 2**40},
        {"side": "buy", "qty_wh": 1000, "limit_price_paise": 500, "deadline": 1},
    ):
        r = client.post("/positions", json=body, headers=h)
        assert r.status_code == 422, (body, r.text)


def test_client_salt_is_used_and_hash_matches(client, seeded_db, interval):
    acct, h = _participant(client, seeded_db)
    salt = "0x" + "ab" * 32
    r = client.post("/positions", json={"side": "buy", "qty_wh": 1500, "limit_price_paise": 550, "salt": salt}, headers=h)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["salt"] == salt and body["id"] == body["position_id"]
    expected = compute_commit_hash(interval.id, acct.address, 0, 1500, 550, body["deadline"], bytes.fromhex("ab" * 32))
    assert body["commit_hash"].lower() == expected.lower()
    again = client.post("/positions", json={"side": "buy", "qty_wh": 1, "limit_price_paise": 550}, headers=h)
    assert again.status_code == 409


def test_deadline_zero_means_none(client, seeded_db, interval):
    _, h = _participant(client, seeded_db)
    r = client.post("/positions", json={"side": "buy", "qty_wh": 1000, "limit_price_paise": 500, "deadline": 0}, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["deadline"] == 0


def _create_and_open_reveal(client, db, interval):
    acct, h = _participant(client, db)
    r = client.post("/positions", json={"side": "buy", "qty_wh": 1000, "limit_price_paise": 500}, headers=h)
    assert r.status_code == 201, r.text
    return h, r.json()


def test_reveal_only_during_reveal_window(client, seeded_db, interval, monkeypatch):
    h, pos = _create_and_open_reveal(client, seeded_db, interval)
    monkeypatch.setattr("app.api.positions.get_chain_client", lambda: _FakeChain(commit=pos["commit_hash"]))
    early = client.post(f"/positions/{pos['id']}/reveal", headers=h)
    assert early.status_code == 409  # still COMMIT
    interval.state = IntervalState.REVEAL
    seeded_db.flush()
    assert client.post(f"/positions/{pos['id']}/reveal", headers=h).status_code == 200


def test_reveal_requires_matching_on_chain_commit(client, seeded_db, interval, monkeypatch):
    h, pos = _create_and_open_reveal(client, seeded_db, interval)
    interval.state = IntervalState.REVEAL
    seeded_db.flush()
    url = f"/positions/{pos['id']}/reveal"

    monkeypatch.setattr("app.api.positions.get_chain_client", lambda: _FakeChain(commit=None))
    missing = client.post(url, headers=h)
    assert missing.status_code == 400 and "no on-chain commit" in missing.json()["detail"]

    monkeypatch.setattr("app.api.positions.get_chain_client", lambda: _FakeChain(commit="0x" + "00" * 31 + "01"))
    assert client.post(url, headers=h).status_code == 400

    monkeypatch.setattr("app.api.positions.get_chain_client", lambda: _FakeChain(commit=pos["commit_hash"]))
    assert client.post(url, headers=h).status_code == 200
