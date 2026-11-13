from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import UserRole
from tests.conftest import login


def test_nonce_and_verify_roundtrip(client: TestClient, db: Session):
    acct = Account.create()
    token = login(client, db, acct.address, acct.key.hex(), UserRole.participant)
    assert isinstance(token, str) and len(token) > 20

    me = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert body["address"].lower() == acct.address.lower()
    assert body["role"] == "participant"
    assert body["participant"] is None


def test_nonce_is_single_use(client: TestClient, db: Session):
    acct = Account.create()
    address = acct.address
    pk = acct.key.hex()
    r = client.post("/auth/nonce", json={"address": address})
    assert r.status_code == 200
    message = r.json()["message"]
    sig = Account.from_key(pk).sign_message(encode_defunct(text=message)).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig

    first = client.post(
        "/auth/verify",
        json={"address": address, "message": message, "signature": sig},
    )
    assert first.status_code == 200

    second = client.post(
        "/auth/verify",
        json={"address": address, "message": message, "signature": sig},
    )
    assert second.status_code == 401
    assert "nonce" in second.json()["detail"].lower()


def test_bad_signature_rejected(client: TestClient, db: Session):
    acct = Account.create()
    r = client.post("/auth/nonce", json={"address": acct.address})
    message = r.json()["message"]
    other = Account.create()
    sig = other.sign_message(encode_defunct(text=message)).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    v = client.post(
        "/auth/verify",
        json={"address": acct.address, "message": message, "signature": sig},
    )
    assert v.status_code == 401
