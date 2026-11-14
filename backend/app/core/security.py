"""JWT and SIWE-style personal_sign verification."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import is_address, to_checksum_address

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def new_nonce() -> str:
    return secrets.token_hex(16)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_siwe_message(
    *,
    address: str,
    nonce: str,
    chain_id: int,
    issued_at: datetime,
    domain: str | None = None,
    uri: str | None = None,
    ttl_seconds: int | None = None,
) -> str:
    """EIP-4361 message (personal_sign). Deterministic for the same inputs, so the server
    can rebuild the exact text it issued and require the signature to cover it."""
    domain = domain or settings.SIWE_DOMAIN
    uri = uri or settings.SIWE_URI
    ttl = settings.SIWE_NONCE_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    issued = issued_at.replace(microsecond=0)
    checksum = to_checksum_address(address)
    return (
        f"{domain} wants you to sign in with your Ethereum account:\n"
        f"{checksum}\n"
        f"\n"
        f"Sign in to Fair and Trustworthy P2P Energy Trading.\n"
        f"\n"
        f"URI: {uri}\n"
        f"Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {_iso(issued)}\n"
        f"Expiration Time: {_iso(issued + timedelta(seconds=ttl))}"
    )


def recover_signer(message: str, signature: str) -> str:
    signed = encode_defunct(text=message)
    recovered = Account.recover_message(signed, signature=signature)
    return to_checksum_address(recovered)


def verify_siwe(
    *,
    address: str,
    message: str,
    signature: str,
    expected_message: str,
    issued_at: datetime,
    now: datetime | None = None,
) -> str:
    """Accept only the exact message this server issued, before it expires, signed by
    `address`. Checking for the nonce inside an arbitrary message is not enough: an
    attacker could embed a victim's nonce in a message for another site."""
    if not is_address(address):
        raise ValueError("invalid address")
    checksum = to_checksum_address(address)
    now = now or datetime.now(timezone.utc)
    if issued_at.tzinfo is None:
        issued_at = issued_at.replace(tzinfo=timezone.utc)
    if now > issued_at + timedelta(seconds=settings.SIWE_NONCE_TTL_SECONDS):
        raise ValueError("sign-in message expired, request a new one")
    if message.replace("\r\n", "\n") != expected_message:
        raise ValueError("message does not match the one issued")
    try:
        signer = recover_signer(message, signature)
    except Exception as exc:  # malformed signature
        raise ValueError("invalid signature") from exc
    if signer.lower() != checksum.lower():
        raise ValueError("signature does not match address")
    return checksum


def create_access_token(
    *,
    subject: str,
    role: str,
    user_id: int,
    expires_minutes: int = ACCESS_TOKEN_EXPIRE_MINUTES,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": to_checksum_address(subject),
        "role": role,
        "uid": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
