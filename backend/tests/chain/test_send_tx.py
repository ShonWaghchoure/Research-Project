"""send_tx must never treat a failed write as done, and never re-send a tx it could not
check (both found in the security audit). Uses a fake node and in-memory SQLite."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from web3.exceptions import TransactionNotFound

from app.chain.client import ChainClient, NonceManager, TxNotConfirmed, TxReverted
from app.db.models import Transaction, TxStatus


class FakeEth:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.block_number = 10
        self.gas_price = 1
        self.receipt_status = 1
        self.rpc_down = False
        self.mined = True
        self.known = True

    def get_transaction_count(self, a, b):  # noqa: ANN001
        return len(self.sent)

    def send_raw_transaction(self, raw):  # noqa: ANN001
        self.sent.append(raw)
        return bytes([len(self.sent)]) * 32

    def wait_for_transaction_receipt(self, h, timeout):  # noqa: ANN001
        if not self.mined:
            raise TimeoutError("not mined")
        return {"blockNumber": 10, "status": self.receipt_status}

    def get_transaction_receipt(self, h):  # noqa: ANN001
        if self.rpc_down:
            raise TimeoutError("rpc timeout")
        if not self.mined:
            raise TransactionNotFound("no receipt")
        return {"status": self.receipt_status}

    def get_transaction(self, h):  # noqa: ANN001
        if not self.known:
            raise TransactionNotFound("unknown")
        return {"hash": h}


class FakeFn:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def build_transaction(self, p):  # noqa: ANN001
        if self.fail:
            raise ValueError("gas estimation failed")
        return p


class Acct:
    address = "0x" + "11" * 20

    def sign_transaction(self, tx):  # noqa: ANN001
        class R:
            raw_transaction = b"raw"

        return R()


@pytest.fixture()
def env():
    eng = create_engine("sqlite://")
    Transaction.__table__.create(eng)
    db = sessionmaker(bind=eng)()
    c = ChainClient.__new__(ChainClient)
    c.w3 = type("W3", (), {"eth": FakeEth()})()
    c.chain_id = 31337
    c.confirmations = 1
    c.nonces = NonceManager(c.w3)
    c.contract = lambda name: None  # type: ignore[method-assign]
    return c, db


def _send(c, db, key="k", fn=None):  # noqa: ANN001
    return c.send_tx(method="postClearing", idempotency_key=key, build_fn=lambda _c: fn or FakeFn(), account=Acct(), db=db)


def test_reverted_tx_raises(env):
    c, db = env
    c.w3.eth.receipt_status = 0
    with pytest.raises(TxReverted):
        _send(c, db)
    assert db.query(Transaction).one().status == TxStatus.failed


def test_rpc_error_on_confirmed_tx_raises_instead_of_resending(env):
    c, db = env
    _send(c, db)
    assert len(c.w3.eth.sent) == 1
    c.w3.eth.rpc_down = True
    with pytest.raises(TimeoutError):
        _send(c, db)
    assert len(c.w3.eth.sent) == 1  # not re-sent


def test_unmined_tx_stays_submitted_and_is_not_resent(env):
    c, db = env
    c.w3.eth.mined = False
    with pytest.raises(TxNotConfirmed):
        _send(c, db)
    assert db.query(Transaction).one().status == TxStatus.submitted
    with pytest.raises(TxNotConfirmed):
        _send(c, db)  # still in mempool: waits again, does not broadcast a second copy
    assert len(c.w3.eth.sent) == 1
    c.w3.eth.mined = True
    assert _send(c, db).status == TxStatus.confirmed
    assert len(c.w3.eth.sent) == 1


def test_tx_missing_after_chain_reset_is_resent(env):
    c, db = env
    _send(c, db)
    real_receipt = c.w3.eth.get_transaction_receipt
    calls = {"n": 0}

    def receipt_after_reset(h):  # first lookup: node restarted and has no record of the tx
        calls["n"] += 1
        if calls["n"] == 1:
            raise TransactionNotFound("unknown")
        return real_receipt(h)

    c.w3.eth.get_transaction_receipt = receipt_after_reset
    c.w3.eth.known = False
    assert _send(c, db).status == TxStatus.confirmed
    assert len(c.w3.eth.sent) == 2  # safe to re-send: the node definitely lost it


def test_nonce_released_when_build_fails(env):
    c, db = env
    with pytest.raises(ValueError):
        _send(c, db, key="a", fn=FakeFn(fail=True))
    _send(c, db, key="b")
    # The failed build released nonce 0, so "b" used it and the next free nonce is 1
    # (without the fix it would be 2, leaving a permanent gap at nonce 0).
    assert c.nonces.next(Acct.address) == 1
