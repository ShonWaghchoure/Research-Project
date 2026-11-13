"""Demo-mode bot driver: register, fund, commit, and reveal via same paths as humans."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

import structlog
from eth_utils import to_checksum_address
from hexbytes import HexBytes
from sqlalchemy.orm import Session
from web3.contract.contract import Contract

from app.chain.client import ChainClient, get_chain_client
from app.chain.commit import compute_commit_hash, side_to_uint8
from app.core.config import settings
from app.db.hardhat_accounts import HARDHAT_ACCOUNTS, HardhatAccount
from app.db.models import Interval, IntervalState, Participant, Position, PositionSide, User
from app.db.session import SessionLocal
from app.workers.phase_timing import expected_state

logger = structlog.get_logger(__name__)

# Hardhat indices 2.. used as demo bots (0=admin, 1=operator)
BOT_START_INDEX = 2
ESCROW_DEPOSIT = 50_000  # paise
STAKE_AMOUNT = 10_000


def _bot_accounts(count: int) -> list[tuple[int, HardhatAccount]]:
    out: list[tuple[int, HardhatAccount]] = []
    for i in range(BOT_START_INDEX, min(BOT_START_INDEX + count, len(HARDHAT_ACCOUNTS))):
        out.append((i, HARDHAT_ACCOUNTS[i]))
    return out


def _ensure_lazy_name(db: Session, part: Participant, acct_index: int) -> None:
    # Mark the last bot as lazy (non-revealing + shortfall)
    if part.display_name and "lazy" in part.display_name.lower():
        return
    bots = _bot_accounts(settings.DEMO_BOT_COUNT)
    if not bots:
        return
    last_idx = bots[-1][0]
    if acct_index == last_idx:
        part.display_name = f"demo-lazy-{acct_index:02d}"
        db.flush()


def _fund_bot_tokens(client: ChainClient, account, db: Session, need: int) -> None:
    """Ensure wallet token balance covers ``need`` (faucet once/day, else operator mint)."""
    if need <= 0:
        return
    addr = to_checksum_address(account.address)
    token: Contract = client.mock_inr
    bal = int(token.functions.balanceOf(addr).call())
    if bal >= need:
        return

    claimed = False
    try:
        claimed = bool(token.functions.hasClaimedToday(addr).call())
    except Exception:
        claimed = False

    if not claimed:
        try:
            client.send_tx(
                method="faucet",
                idempotency_key=f"bot:{addr.lower()}:faucet:{datetime.now(timezone.utc).date()}",
                build_fn=lambda c: c.functions.faucet(),
                account=account,
                contract_name="MockINR",
                db=db,
            )
        except Exception as exc:
            # Permanent daily lock — do not leave a failed idempotency row to retry.
            _suppress_permanent_tx_failure(db, f"bot:{addr.lower()}:faucet:{datetime.now(timezone.utc).date()}", exc)
            logger.info("bot_faucet_skip", addr=addr, error=str(exc)[:160])

    bal = int(token.functions.balanceOf(addr).call())
    if bal >= need:
        return

    # Demo fallback: operator mints the shortfall (faucet exhausted / spent).
    shortfall = need - bal
    try:
        client.send_operator_tx(
            "mint",
            f"bot:{addr.lower()}:mint:{shortfall}",
            lambda c, a=addr, amt=shortfall: c.functions.mint(a, amt),
            contract_name="MockINR",
            db=db,
        )
    except Exception as exc:
        logger.warning("bot_mint_failed", addr=addr, error=str(exc)[:200])


def _suppress_permanent_tx_failure(db: Session, idempotency_key: str, exc: Exception) -> None:
    """Mark a known-permanent revert as confirmed-skip so send_tx will not retry it."""
    from app.db.models import Transaction, TxStatus

    msg = str(exc).lower()
    permanent = "already claimed" in msg or "already registered" in msg
    if not permanent:
        return
    row = (
        db.query(Transaction)
        .filter(Transaction.idempotency_key == idempotency_key)
        .one_or_none()
    )
    if row is None:
        return
    row.status = TxStatus.confirmed
    row.error = str(exc)[:500]
    db.commit()


def _ensure_onchain(client: ChainClient, account, part: Participant, db: Session) -> None:
    """Faucet, stake, register, approve, deposit escrow — all idempotent."""
    addr = to_checksum_address(account.address)
    token: Contract = client.mock_inr
    registry = client.registry
    settlement = client.settlement

    pinfo = registry.functions.getParticipant(addr).call()
    registered = bool(pinfo[4]) if len(pinfo) > 4 else bool(pinfo[-2])
    stake = int(pinfo[0])
    escrow = int(settlement.functions.escrow(addr).call())

    need = 0
    if stake < STAKE_AMOUNT:
        need += STAKE_AMOUNT
    if escrow < ESCROW_DEPOSIT // 2:
        need += ESCROW_DEPOSIT
    _fund_bot_tokens(client, account, db, need)

    # Approve registry + settlement max
    for spender_name, spender in (("Registry", registry.address), ("Settlement", settlement.address)):
        allowance = int(token.functions.allowance(addr, spender).call())
        if allowance < STAKE_AMOUNT + ESCROW_DEPOSIT:
            client.send_tx(
                method="approve",
                idempotency_key=f"bot:{addr.lower()}:approve:{spender_name}",
                build_fn=lambda c, s=spender: c.functions.approve(s, 2**256 - 1),
                account=account,
                contract_name="MockINR",
                db=db,
            )

    if stake < STAKE_AMOUNT:
        client.send_tx(
            method="stake",
            idempotency_key=f"bot:{addr.lower()}:stake",
            build_fn=lambda c: c.functions.stake(STAKE_AMOUNT),
            account=account,
            contract_name="Registry",
            db=db,
        )
    if not registered:
        meter_hash = HexBytes(client.w3.keccak(text=f"meter:{part.id}:{addr.lower()}"))
        try:
            client.send_tx(
                method="register",
                idempotency_key=f"bot:{addr.lower()}:register",
                build_fn=lambda c, h=meter_hash: c.functions.register(h),
                account=account,
                contract_name="Registry",
                db=db,
            )
        except Exception as exc:
            _suppress_permanent_tx_failure(db, f"bot:{addr.lower()}:register", exc)
            logger.info("bot_register_skip", addr=addr, error=str(exc)[:200])

    escrow = int(settlement.functions.escrow(addr).call())
    if escrow < ESCROW_DEPOSIT // 2:
        client.send_tx(
            method="deposit",
            idempotency_key=f"bot:{addr.lower()}:deposit:{part.id}",
            build_fn=lambda c: c.functions.deposit(ESCROW_DEPOSIT),
            account=account,
            contract_name="Settlement",
            db=db,
        )


def _create_position(
    db: Session,
    client: ChainClient,
    interval: Interval,
    part: Participant,
    account,
    side: PositionSide,
) -> None:
    existing = (
        db.query(Position)
        .filter(Position.participant_id == part.id, Position.interval_id == interval.id)
        .one_or_none()
    )
    if existing is not None:
        return

    qty_wh = 2000 + (part.id % 5) * 500  # 2–4 kWh
    if side == PositionSide.buy:
        limit = 800
    else:
        limit = 300
    deadline = int(interval.ends_at.replace(tzinfo=timezone.utc).timestamp()) if interval.ends_at.tzinfo is None else int(interval.ends_at.timestamp())
    salt = secrets.token_bytes(32)
    salt_hex = "0x" + salt.hex()
    commit = compute_commit_hash(
        interval.id,
        account.address,
        side_to_uint8(side.value),
        qty_wh,
        limit,
        deadline,
        salt,
    )
    pos = Position(
        participant_id=part.id,
        interval_id=interval.id,
        side=side,
        qty_wh=qty_wh,
        limit_price_paise=limit,
        commit_hash=commit,
        salt=salt_hex,
        deadline=deadline,
        revealed=False,
    )
    db.add(pos)
    db.commit()

    try:
        client.commit_position(account, interval.id, commit, db=db)
    except Exception as exc:
        logger.warning("bot_commit_failed", part=part.id, error=str(exc)[:300])


def ensure_bots_ready(client: ChainClient | None = None) -> None:
    """Idempotent faucet/stake/register/deposit for all demo bots (no commits)."""
    if not settings.DEMO_MODE:
        return
    client = client or get_chain_client()
    db = SessionLocal()
    try:
        if not client.is_reachable():
            return
        for idx, acct in _bot_accounts(settings.DEMO_BOT_COUNT):
            user = (
                db.query(User)
                .filter(User.address == to_checksum_address(acct.address))
                .one_or_none()
            )
            if user is None:
                continue
            part = db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
            if part is None:
                continue
            _ensure_lazy_name(db, part, idx)
            account = client.participant_account(acct.private_key)
            try:
                _ensure_onchain(client, account, part, db)
            except Exception as exc:
                logger.warning("bot_onchain_failed", addr=acct.address, error=str(exc)[:200])
        db.commit()
    except Exception:
        logger.exception("bots_ready_failed")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def tick(client: ChainClient | None = None) -> None:
    if not settings.DEMO_MODE:
        return
    client = client or get_chain_client()
    db = SessionLocal()
    try:
        if not client.is_reachable():
            return
        interval = db.query(Interval).order_by(Interval.id.desc()).first()
        if interval is None:
            # No market yet — still keep bots funded for the first open.
            ensure_bots_ready(client)
            return
        now = datetime.now(timezone.utc)
        phase = expected_state(interval.starts_at, interval.ends_at, now)
        # Also respect DB state if already advanced
        state = interval.state

        bots = _bot_accounts(settings.DEMO_BOT_COUNT)
        for idx, acct in bots:
            user = (
                db.query(User)
                .filter(User.address == to_checksum_address(acct.address))
                .one_or_none()
            )
            if user is None:
                continue
            part = db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
            if part is None:
                continue
            _ensure_lazy_name(db, part, idx)
            account = client.participant_account(acct.private_key)

            # Keep bots funded/registered outside the commit window so setup
            # txs do not burn Hardhat time against commitDeadline.
            try:
                _ensure_onchain(client, account, part, db)
            except Exception as exc:
                logger.warning("bot_onchain_failed", addr=acct.address, error=str(exc)[:200])
                continue

            if state in (IntervalState.OPEN, IntervalState.COMMIT) or phase in (
                IntervalState.OPEN,
                IntervalState.COMMIT,
            ):
                # Skip commits until the interval is open on chain and the
                # commit window is still live.
                try:
                    iv = client.on_chain_interval(interval.id)
                    opened = bool(iv[2]) if not hasattr(iv, "opened") else bool(iv.opened)
                    commit_dl = int(iv[0] if not hasattr(iv, "commitDeadline") else iv.commitDeadline)
                    chain_now = int(client.w3.eth.get_block("latest")["timestamp"])
                    if not opened or chain_now >= commit_dl:
                        continue
                except Exception:
                    continue
                side = PositionSide.buy if idx % 2 == 0 else PositionSide.sell
                _create_position(db, client, interval, part, account, side)

            if state == IntervalState.REVEAL or phase == IntervalState.REVEAL:
                pos = (
                    db.query(Position)
                    .filter(
                        Position.participant_id == part.id,
                        Position.interval_id == interval.id,
                    )
                    .one_or_none()
                )
                if pos is None or pos.revealed:
                    continue
                # Lazy bots still reveal so they clear and get shortfall-slashed
                # (under-delivery is applied in workers/meter.py by display name).
                pos.revealed = True
                db.commit()
        db.commit()
    except Exception:
        logger.exception("bots_tick_failed")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()
