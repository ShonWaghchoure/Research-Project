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


def build_siwe_message(*, address: str, nonce: str, chain_id: int, domain: str = "localhost") -> str:
    """EIP-4361-inspired message (personal_sign)."""
    issued = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    checksum = to_checksum_address(address)
    return (
        f"{domain} wants you to sign in with your Ethereum account:\n"
        f"{checksum}\n"
        f"\n"
        f"Sign in to Fair and Trustworthy P2P Energy Trading.\n"
        f"\n"
        f"URI: http://{domain}:3000\n"
        f"Version: 1\n"
        f"Chain ID: {chain_id}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued}"
    )


def recover_signer(message: str, signature: str) -> str:
    signed = encode_defunct(text=message)
    recovered = Account.recover_message(signed, signature=signature)
    return to_checksum_address(recovered)


def verify_siwe(*, address: str, message: str, signature: str, expected_nonce: str) -> str:
    if not is_address(address):
        raise ValueError("invalid address")
    checksum = to_checksum_address(address)
    if f"Nonce: {expected_nonce}" not in message:
        raise ValueError("nonce mismatch")
    if checksum.lower() not in message.lower():
        raise ValueError("address not present in message")
    signer = recover_signer(message, signature)
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
