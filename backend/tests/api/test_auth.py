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


def _sign(pk: str, message: str) -> str:
    sig = Account.from_key(pk).sign_message(encode_defunct(text=message)).signature.hex()
    return sig if sig.startswith("0x") else "0x" + sig


def test_phished_message_with_valid_nonce_rejected(client: TestClient, db: Session):
    """Security fix: a victim's real nonce embedded in a message for another site, signed by
    the victim, must not log the attacker in."""
    victim = Account.create()
    nonce = client.post("/auth/nonce", json={"address": victim.address}).json()["nonce"]
    phish = (
        "evil.example wants you to sign in with your Ethereum account:\n"
        f"{victim.address}\n\nClaim your airdrop.\n\nURI: https://evil.example\n"
        f"Version: 1\nChain ID: 1\nNonce: {nonce}\nIssued At: 2001-01-01T00:00:00Z"
    )
    r = client.post(
        "/auth/verify",
        json={"address": victim.address, "message": phish, "signature": _sign(victim.key.hex(), phish)},
    )
    assert r.status_code == 401
    assert "does not match" in r.json()["detail"]


def test_expired_nonce_rejected(client: TestClient, db: Session):
    from datetime import datetime, timedelta, timezone

    from app.db.models import User

    acct = Account.create()
    message = client.post("/auth/nonce", json={"address": acct.address}).json()["message"]
    user = db.query(User).filter(User.address == acct.address).one()
    # Pretend the nonce was issued long ago; the server rebuilds the message from this time.
    user.nonce_issued_at = datetime.now(timezone.utc) - timedelta(hours=1)
    db.commit()
    r = client.post(
        "/auth/verify",
        json={"address": acct.address, "message": message, "signature": _sign(acct.key.hex(), message)},
    )
    assert r.status_code == 401
    assert "expired" in r.json()["detail"]


def test_issued_message_names_configured_domain_and_expiry(client: TestClient, db: Session):
    from app.core.config import settings

    acct = Account.create()
    message = client.post("/auth/nonce", json={"address": acct.address}).json()["message"]
    assert message.startswith(f"{settings.SIWE_DOMAIN} wants you to sign in")
    assert f"URI: {settings.SIWE_URI}\n" in message
    assert "\nExpiration Time: " in message


def test_token_with_only_uid_rejected(client: TestClient, db: Session):
    """Security fix: a token forged for the admin's user id but not naming the admin's
    address (e.g. with a leaked/default secret) is rejected."""
    import jwt as pyjwt

    from app.core.config import settings

    admin = Account.create()
    login(client, db, admin.address, admin.key.hex(), UserRole.admin)
    from app.db.models import User

    uid = db.query(User).filter(User.address == admin.address).one().id
    forged = pyjwt.encode({"uid": uid, "role": "admin", "exp": 4102444800}, settings.JWT_SECRET, "HS256")
    r = client.get("/admin/config", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 401
