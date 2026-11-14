"""web3.py chain client with idempotent operator transactions and nonce management."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any, Optional

import structlog
from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_utils import to_checksum_address
from hexbytes import HexBytes
from sqlalchemy.orm import Session
from web3 import Web3
from web3.contract.contract import Contract
from web3.types import TxParams

from app.chain.deployments import DeploymentBundle, load_deployments
from app.core.config import settings
from app.db.models import Transaction, TxStatus
from app.db.session import SessionLocal

logger = structlog.get_logger(__name__)

BuildFn = Callable[[Contract], Any]  # returns a ContractFunction


class NonceManager:
    """Thread-safe per-address nonce tracker."""

    def __init__(self, w3: Web3) -> None:
        self._w3 = w3
        self._lock = threading.Lock()
        self._nonces: dict[str, int] = {}

    def next(self, address: str) -> int:
        addr = to_checksum_address(address)
        with self._lock:
            if addr not in self._nonces:
                self._nonces[addr] = int(self._w3.eth.get_transaction_count(addr, "pending"))
            n = self._nonces[addr]
            self._nonces[addr] = n + 1
            return n

    def reset(self, address: str) -> None:
        addr = to_checksum_address(address)
        with self._lock:
            self._nonces[addr] = int(self._w3.eth.get_transaction_count(addr, "pending"))


class ChainClient:
    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        chain_id: int | None = None,
        operator_key: str | None = None,
        confirmations: int | None = None,
        deployment: DeploymentBundle | None = None,
    ) -> None:
        self.rpc_url = rpc_url or settings.CHAIN_RPC_URL
        self.chain_id = int(chain_id if chain_id is not None else settings.CHAIN_ID)
        self.confirmations = (
            confirmations if confirmations is not None else settings.confirmations
        )
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url, request_kwargs={"timeout": 30.0}))
        self.deployment = deployment or load_deployments(self.chain_id)
        key = operator_key or settings.OPERATOR_PRIVATE_KEY
        self.operator: LocalAccount = Account.from_key(key)
        self.nonces = NonceManager(self.w3)
        self._contracts: dict[str, Contract] = {}

    def is_reachable(self) -> bool:
        try:
            return bool(self.w3.is_connected())
        except Exception:
            return False

    def contract(self, name: str) -> Contract:
        if name not in self._contracts:
            info = self.deployment.contracts[name]
            addr = to_checksum_address(
                getattr(settings, f"{_settings_attr(name)}", None) or info.address
            )
            self._contracts[name] = self.w3.eth.contract(address=addr, abi=info.abi)
        return self._contracts[name]

    @property
    def settlement(self) -> Contract:
        return self.contract("Settlement")

    @property
    def registry(self) -> Contract:
        return self.contract("Registry")

    @property
    def reputation_anchor(self) -> Contract:
        return self.contract("ReputationAnchor")

    @property
    def mock_inr(self) -> Contract:
        return self.contract("MockINR")

    def participant_account(self, private_key: str) -> LocalAccount:
        return Account.from_key(private_key)

    def sync_chain_time(self, unix_ts: int) -> None:
        """Advance Hardhat/Anvil time if behind ``unix_ts`` (no-op on other nets)."""
        if self.chain_id != 31337:
            return
        try:
            latest = int(self.w3.eth.get_block("latest")["timestamp"])
            if unix_ts <= latest:
                return
            self.w3.provider.make_request(  # type: ignore[union-attr]
                "evm_setNextBlockTimestamp", [int(unix_ts)]
            )
            self.w3.provider.make_request("evm_mine", [])  # type: ignore[union-attr]
        except Exception as exc:
            logger.warning("sync_chain_time_failed", error=str(exc))

    def send_operator_tx(
        self,
        method: str,
        idempotency_key: str,
        build_fn: BuildFn,
        *,
        contract_name: str = "Settlement",
        db: Session | None = None,
    ) -> Transaction:
        return self.send_tx(
            method=method,
            idempotency_key=idempotency_key,
            build_fn=build_fn,
            account=self.operator,
            contract_name=contract_name,
            db=db,
        )

    def send_tx(
        self,
        *,
        method: str,
        idempotency_key: str,
        build_fn: BuildFn,
        account: LocalAccount,
        contract_name: str = "Settlement",
        db: Session | None = None,
        value: int = 0,
    ) -> Transaction:
        own_session = db is None
        session = db or SessionLocal()
        try:
            existing = (
                session.query(Transaction)
                .filter(Transaction.idempotency_key == idempotency_key)
                .one_or_none()
            )
            if existing is not None:
                if existing.status == TxStatus.confirmed:
                    # Hardhat restarts wipe chain state while DB rows remain; only
                    # skip re-send when the receipt still exists on the live RPC.
                    if existing.tx_hash and self._tx_still_on_chain(existing.tx_hash):
                        return existing
                    logger.warning(
                        "idempotent_tx_missing_on_chain",
                        key=idempotency_key,
                        tx=existing.tx_hash,
                    )
                    existing.status = TxStatus.pending
                    existing.error = "receipt missing after chain reset"
                    existing.tx_hash = None
                    session.commit()
                elif existing.status == TxStatus.submitted and existing.tx_hash:
                    if self._tx_still_on_chain(existing.tx_hash):
                        self._await_and_finalize(session, existing)
                        return existing
                    existing.status = TxStatus.pending
                    existing.error = "submitted tx missing after chain reset"
                    existing.tx_hash = None
                    session.commit()
                elif existing.status == TxStatus.failed:
                    # Allow retry with same key by resetting to pending.
                    existing.status = TxStatus.pending
                    existing.error = None
                    existing.tx_hash = None
                    session.commit()

            row = existing
            if row is None:
                row = Transaction(
                    idempotency_key=idempotency_key,
                    method=method,
                    status=TxStatus.pending,
                    payload={"contract": contract_name, "from": account.address},
                )
                session.add(row)
                session.commit()
                session.refresh(row)

            contract = self.contract(contract_name)
            fn = build_fn(contract)
            tx_hash = self._sign_and_send(account, fn, value=value)
            row.tx_hash = tx_hash
            row.status = TxStatus.submitted
            session.commit()

            self._await_and_finalize(session, row)
            return row
        except Exception as exc:
            logger.exception("send_tx_failed", method=method, key=idempotency_key)
            try:
                row2 = (
                    session.query(Transaction)
                    .filter(Transaction.idempotency_key == idempotency_key)
                    .one_or_none()
                )
                if row2 is not None and row2.status != TxStatus.confirmed:
                    row2.status = TxStatus.failed
                    row2.error = str(exc)[:2000]
                    session.commit()
            except Exception:
                session.rollback()
            raise
        finally:
            if own_session:
                session.close()

    def _sign_and_send(self, account: LocalAccount, fn: Any, *, value: int = 0) -> str:
        addr = to_checksum_address(account.address)
        nonce = self.nonces.next(addr)
        tx: TxParams = fn.build_transaction(
            {
                "from": addr,
                "nonce": nonce,
                "chainId": self.chain_id,
                "gas": 3_000_000,
                "gasPrice": self.w3.eth.gas_price,
                "value": value,
            }
        )
        signed = account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
        try:
            tx_hash = self.w3.eth.send_raw_transaction(raw)
        except Exception:
            self.nonces.reset(addr)
            raise
        # hexbytes 2.x returns bare hex; always store canonical 0x form.
        return _norm_hex(HexBytes(tx_hash).hex())

    def _tx_still_on_chain(self, tx_hash: str) -> bool:
        """Return True if ``tx_hash`` has a receipt on the current RPC."""
        try:
            receipt = self.w3.eth.get_transaction_receipt(_norm_hex(tx_hash))
            return receipt is not None and int(receipt.get("status", 0)) == 1
        except Exception:
            return False

    def _await_and_finalize(self, session: Session, row: Transaction) -> None:
        if not row.tx_hash:
            return
        try:
            hx = _norm_hex(row.tx_hash)
            if row.tx_hash != hx:
                row.tx_hash = hx
                session.commit()
            receipt = self.w3.eth.wait_for_transaction_receipt(hx, timeout=120)
            target = int(receipt["blockNumber"]) + max(0, self.confirmations - 1)
            while int(self.w3.eth.block_number) < target:
                time.sleep(0.05)
            if int(receipt.get("status", 0)) != 1:
                row.status = TxStatus.failed
                row.error = "transaction reverted"
            else:
                row.status = TxStatus.confirmed
                row.error = None
            session.commit()
        except Exception as exc:
            logger.warning("await_receipt_failed", tx=row.tx_hash, error=str(exc))
            # Leave as submitted for restart reconciliation.

    # --- Settlement helpers -------------------------------------------------

    def open_interval(
        self,
        interval_id: int,
        commit_deadline: int,
        reveal_deadline: int,
        *,
        db: Session | None = None,
    ) -> Transaction:
        return self.send_operator_tx(
            "openInterval",
            f"settle:{interval_id}:openInterval",
            lambda c: c.functions.openInterval(
                int(interval_id), int(commit_deadline), int(reveal_deadline)
            ),
            db=db,
        )

    def post_clearing(
        self,
        interval_id: int,
        input_root: str,
        result_hash: str,
        p_ref_paise: int,
        *,
        db: Session | None = None,
    ) -> Transaction:
        return self.send_operator_tx(
            "postClearing",
            f"settle:{interval_id}:postClearing",
            lambda c: c.functions.postClearing(
                int(interval_id),
                _to_bytes32(input_root),
                _to_bytes32(result_hash),
                int(p_ref_paise),
            ),
            db=db,
        )

    def settle_batch(
        self,
        interval_id: int,
        trades: list[tuple[str, str, int, int]],
        batch_index: int,
        *,
        db: Session | None = None,
    ) -> Transaction:
        structs = [
            (to_checksum_address(b), to_checksum_address(s), int(q), int(p))
            for b, s, q, p in trades
        ]
        return self.send_operator_tx(
            "settleBatch",
            f"settle:{interval_id}:batch:{batch_index}",
            lambda c: c.functions.settleBatch(int(interval_id), structs),
            db=db,
        )

    def post_delivery(
        self,
        interval_id: int,
        delivery_root: str,
        *,
        db: Session | None = None,
    ) -> Transaction:
        return self.send_operator_tx(
            "postDelivery",
            f"settle:{interval_id}:postDelivery",
            lambda c: c.functions.postDelivery(int(interval_id), _to_bytes32(delivery_root)),
            db=db,
        )

    def settle_shortfall(
        self,
        interval_id: int,
        participant: str,
        shortfall_wh: int,
        proof: list[str],
        buyer: str,
        *,
        db: Session | None = None,
    ) -> Transaction:
        proof_bytes = [_to_bytes32(p) for p in proof]
        return self.send_operator_tx(
            "settleShortfall",
            f"settle:{interval_id}:shortfall:{participant.lower()}",
            lambda c: c.functions.settleShortfall(
                int(interval_id),
                to_checksum_address(participant),
                int(shortfall_wh),
                proof_bytes,
                to_checksum_address(buyer),
            ),
            db=db,
        )

    def post_reputation_root(
        self,
        interval_id: int,
        root: str,
        *,
        db: Session | None = None,
    ) -> Transaction:
        return self.send_operator_tx(
            "postRoot",
            f"rep:{interval_id}:postRoot",
            lambda c: c.functions.postRoot(int(interval_id), _to_bytes32(root)),
            contract_name="ReputationAnchor",
            db=db,
        )

    def commit_position(
        self,
        account: LocalAccount,
        interval_id: int,
        commit_hash: str,
        *,
        db: Session | None = None,
    ) -> Transaction:
        return self.send_tx(
            method="commitPosition",
            idempotency_key=f"commit:{interval_id}:{account.address.lower()}",
            build_fn=lambda c: c.functions.commitPosition(
                int(interval_id), _to_bytes32(commit_hash)
            ),
            account=account,
            contract_name="Settlement",
            db=db,
        )

    def on_chain_commit(self, interval_id: int, participant: str) -> Optional[str]:
        h = self.settlement.functions.commits(
            int(interval_id), to_checksum_address(participant)
        ).call()
        if isinstance(h, (bytes, bytearray, HexBytes)):
            return _bytes32_hex(h)
        return None

    def on_chain_interval(self, interval_id: int) -> tuple:
        """Raw Settlement.intervals(id) tuple.

        Order: commitDeadline, revealDeadline, opened, clearingPosted,
        deliveryPosted, inputRoot, resultHash, deliveryRoot, pRefPaise.
        """
        return self.settlement.functions.intervals(int(interval_id)).call()

    def on_chain_interval_opened(self, interval_id: int) -> bool:
        iv = self.on_chain_interval(interval_id)
        return bool(_iv_field(iv, 2, "opened"))

    def on_chain_clearing_posted(self, interval_id: int) -> bool:
        iv = self.on_chain_interval(interval_id)
        return bool(_iv_field(iv, 3, "clearingPosted"))

    def on_chain_delivery_posted(self, interval_id: int) -> bool:
        iv = self.on_chain_interval(interval_id)
        return bool(_iv_field(iv, 4, "deliveryPosted"))

    def on_chain_input_root(self, interval_id: int) -> Optional[str]:
        iv = self.on_chain_interval(interval_id)
        return _bytes32_hex(_iv_field(iv, 5, "inputRoot"))

    def on_chain_result_hash(self, interval_id: int) -> Optional[str]:
        iv = self.on_chain_interval(interval_id)
        return _bytes32_hex(_iv_field(iv, 6, "resultHash"))

    def on_chain_reputation_root(self, interval_id: int) -> Optional[str]:
        root = self.reputation_anchor.functions.roots(int(interval_id)).call()
        return _bytes32_hex(root)


def _norm_hex(value: str) -> str:
    hx = value.lower()
    return hx if hx.startswith("0x") else "0x" + hx


def _iv_field(iv: Any, index: int, name: str) -> Any:
    """Read a Settlement.intervals field by name when possible, else by index."""
    if hasattr(iv, name):
        return getattr(iv, name)
    try:
        return iv[name]  # type: ignore[index]
    except Exception:
        return iv[index]


def _bytes32_hex(value: Any) -> Optional[str]:
    hx = _norm_hex(HexBytes(value).hex())
    return None if int(hx, 16) == 0 else hx


def _to_bytes32(value: str | bytes) -> bytes:
    if isinstance(value, bytes):
        raw = value
    else:
        raw = bytes.fromhex(_norm_hex(value).removeprefix("0x"))
    if len(raw) != 32:
        raise ValueError(f"expected 32 bytes, got {len(raw)}")
    return raw


def _settings_attr(contract_name: str) -> str:
    return {
        "Ping": "PING_CONTRACT_ADDRESS",
        "MockINR": "MOCK_INR_ADDRESS",
        "Registry": "REGISTRY_ADDRESS",
        "ReputationAnchor": "REPUTATION_ANCHOR_ADDRESS",
        "Settlement": "SETTLEMENT_ADDRESS",
    }.get(contract_name, contract_name.upper() + "_ADDRESS")


_client: ChainClient | None = None
_client_lock = threading.Lock()


def get_chain_client() -> ChainClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = ChainClient()
        return _client
