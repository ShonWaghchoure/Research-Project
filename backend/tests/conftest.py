"""Shared fixtures for Phase 6 API tests (real Postgres, rolled-back transactions)."""

from __future__ import annotations

import os

# Prevent market scheduler from starting during unit/API tests.
os.environ["TESTING"] = "1"

import pytest
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import to_checksum_address
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config_store import seed_config
from app.db.deps import get_db
from app.db.hardhat_accounts import HARDHAT_ACCOUNTS
from app.db.models import FeederNode, User, UserRole
from app.db.seed import seed_feeder
from app.db.session import engine
from app.main import app


@pytest.fixture()
def db() -> Session:
    connection = engine.connect()
    transaction = connection.begin()
    TestingSession = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = TestingSession()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess: Session, trans) -> None:  # type: ignore[no-untyped-def]
        if trans.nested and not trans._parent.nested:  # noqa: SLF001
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db: Session) -> TestClient:
    def _override():  # type: ignore[no-untyped-def]
        yield db

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def seeded_db(db: Session) -> Session:
    seed_feeder(db)
    seed_config(db)
    if db.get(FeederNode, "n4") is None:
        db.add(FeederNode(id="n4", name="n4", is_root=False))
    db.flush()
    return db


@pytest.fixture()
def admin_account() -> tuple[str, str]:
    a = HARDHAT_ACCOUNTS[0]
    return a.address, a.private_key


@pytest.fixture()
def participant_account() -> tuple[str, str]:
    a = HARDHAT_ACCOUNTS[2]
    return a.address, a.private_key


def login(client: TestClient, db: Session, address: str, private_key: str, role: UserRole) -> str:
    """Ensure user exists with role, complete SIWE, return JWT."""
    checksum = to_checksum_address(address)
    user = db.query(User).filter(User.address == checksum).one_or_none()
    if user is None:
        user = User(address=checksum, role=role, nonce_used=True)
        db.add(user)
        db.flush()
    else:
        user.role = role
        db.flush()

    r = client.post("/auth/nonce", json={"address": checksum})
    assert r.status_code == 200, r.text
    data = r.json()
    sig = Account.from_key(private_key).sign_message(
        encode_defunct(text=data["message"])
    ).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    v = client.post(
        "/auth/verify",
        json={"address": checksum, "message": data["message"], "signature": sig},
    )
    assert v.status_code == 200, v.text
    return v.json()["access_token"]
