"""Commit-hash helpers matching Settlement.computeCommitHash."""

from __future__ import annotations

from eth_abi import encode
from eth_hash.auto import keccak
from eth_utils import to_checksum_address

SIDE_BUY = 0
SIDE_SELL = 1


def side_to_uint8(side: str) -> int:
    s = side.lower().strip()
    if s == "buy":
        return SIDE_BUY
    if s == "sell":
        return SIDE_SELL
    raise ValueError(f"unknown side: {side!r}")


def compute_commit_hash(
    interval_id: int,
    participant: str,
    side: int | str,
    qty_wh: int,
    limit_price_paise: int,
    deadline: int,
    salt: bytes | str,
) -> str:
    """keccak256(abi.encode(intervalId, participant, side, qtyWh, limitPricePaise, deadline, salt))."""
    side_u8 = side_to_uint8(side) if isinstance(side, str) else int(side)
    if isinstance(salt, str):
        salt_hex = salt.removeprefix("0x")
        salt_b = bytes.fromhex(salt_hex)
    else:
        salt_b = salt
    if len(salt_b) != 32:
        raise ValueError("salt must be 32 bytes")
    encoded = encode(
        ["uint256", "address", "uint8", "uint64", "uint32", "uint64", "bytes32"],
        [
            int(interval_id),
            to_checksum_address(participant),
            side_u8,
            int(qty_wh),
            int(limit_price_paise),
            int(deadline),
            salt_b,
        ],
    )
    return "0x" + keccak(encoded).hex()
