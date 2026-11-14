"""Lightweight Settlement event poller for reconciliation."""

from __future__ import annotations

import structlog
from sqlalchemy.orm import Session

from app.chain.client import ChainClient, get_chain_client
from app.db.models import AuditLog, Transaction, TxStatus
from app.db.session import SessionLocal

logger = structlog.get_logger(__name__)

_last_block: int | None = None

EVENT_NAMES = (
    "IntervalOpened",
    "PositionCommitted",
    "ClearingPosted",
    "TradeSettled",
    "DeliveryPosted",
    "ShortfallSettled",
    "Deposited",
)


def tick(client: ChainClient | None = None) -> None:
    global _last_block
    client = client or get_chain_client()
    db = SessionLocal()
    try:
        if not client.is_reachable():
            return
        latest = int(client.w3.eth.block_number)
        start = 0 if _last_block is None else max(0, _last_block - 2)
        if start > latest:
            return

        settlement = client.settlement
        for name in EVENT_NAMES:
            try:
                event_abi = getattr(settlement.events, name)
            except Exception:
                continue
            try:
                logs = event_abi.get_logs(from_block=start, to_block=latest)
            except Exception as exc:
                logger.debug("event_poll_failed", event=name, error=str(exc)[:200])
                continue
            for ev in logs:
                raw_hx = ev.get("transactionHash")
                if raw_hx is None:
                    tx_hash = None
                else:
                    hx = raw_hx.hex() if hasattr(raw_hx, "hex") else str(raw_hx)
                    # Canonical 0x form for Transaction matching (String(66)).
                    tx_hash = hx if hx.startswith("0x") else "0x" + hx
                log_index = int(ev.get("logIndex") or 0)
                _upsert_event(db, name, tx_hash, dict(ev.get("args") or {}), log_index)
                if tx_hash:
                    _mark_tx_confirmed(db, tx_hash)

        _last_block = latest
        db.commit()
    except Exception:
        logger.exception("listener_tick_failed")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def _event_resource_id(name: str, tx_hash: str | None, log_index: int) -> str:
    """Unique per log, not per transaction: one settleBatch emits up to 10 TradeSettled
    events with the same tx hash, and keying on the hash alone kept only the first.
    audit_log.resource_id is varchar(64): 56 hex chars of the hash (224 bits) + ':' + index."""
    base = tx_hash.removeprefix("0x")[:56] if tx_hash else name[:56]
    return f"{base}:{log_index}"[:64]


def _upsert_event(
    db: Session, name: str, tx_hash: str | None, args: dict, log_index: int = 0
) -> None:
    resource_id = _event_resource_id(name, tx_hash, log_index)
    existing = (
        db.query(AuditLog)
        .filter(
            AuditLog.action == f"chain:{name}",
            AuditLog.resource_type == "chain_event",
            AuditLog.resource_id == resource_id,
        )
        .first()
    )
    if existing is not None:
        return
    db.add(
        AuditLog(
            actor_user_id=None,
            action=f"chain:{name}",
            resource_type="chain_event",
            resource_id=resource_id,
            after={
                "args": {k: str(v) for k, v in args.items()},
                "tx_hash": tx_hash,
                "log_index": log_index,
            },
        )
    )


def _mark_tx_confirmed(db: Session, tx_hash: str) -> None:
    hx = tx_hash if tx_hash.startswith("0x") else "0x" + tx_hash
    bare = hx[2:]
    row = (
        db.query(Transaction)
        .filter(Transaction.tx_hash.ilike(hx) | Transaction.tx_hash.ilike(bare))
        .order_by(Transaction.id.desc())
        .first()
    )
    if row is not None and row.status != TxStatus.confirmed:
        row.status = TxStatus.confirmed
        row.tx_hash = hx
        row.error = None
