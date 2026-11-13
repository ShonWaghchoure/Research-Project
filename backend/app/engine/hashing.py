"""Deterministic hashing helpers for clearing inputs/outputs (pure)."""

from __future__ import annotations

import json
from typing import Any, Sequence

from eth_hash.auto import keccak


def canonical_json(obj: Any) -> str:
    """Canonical JSON: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def keccak256(data: bytes | str) -> bytes:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return bytes(keccak(data))


def keccak256_hex(data: bytes | str) -> str:
    return "0x" + keccak256(data).hex()


def _position_record(position: Any) -> dict[str, Any]:
    return {
        "participant_id": position.participant_id,
        "side": position.side,
        "qty_kwh": float(position.qty_kwh),
        "limit_price": float(position.limit_price),
        "reputation": float(position.reputation),
        "node_id": getattr(position, "node_id", "n0"),
        "min_seller_reputation": float(getattr(position, "min_seller_reputation", 0.0)),
    }


def input_root(positions: Sequence[Any]) -> str:
    """Merkle root over sorted revealed positions (keccak pairwise)."""
    records = sorted(
        (_position_record(p) for p in positions),
        key=lambda r: (r["participant_id"], r["side"], r["qty_kwh"], r["limit_price"]),
    )
    leaves = [keccak256(canonical_json(r)) for r in records]
    return _merkle_root(leaves)


def _trade_record(trade: Any) -> dict[str, Any]:
    return {
        "buyer_id": trade.buyer_id,
        "seller_id": trade.seller_id,
        "qty_wh": int(trade.qty_wh),
        "price": float(trade.price),
    }


def result_hash(trades: Sequence[Any], p_ref: float) -> str:
    """Hash over sorted trade list + p_ref."""
    payload = {
        "p_ref": float(p_ref),
        "trades": sorted(
            (_trade_record(t) for t in trades),
            key=lambda r: (r["buyer_id"], r["seller_id"], r["qty_wh"], r["price"]),
        ),
    }
    return keccak256_hex(canonical_json(payload))


def _merkle_root(leaves: Sequence[bytes]) -> str:
    if not leaves:
        return keccak256_hex(b"")
    layer = list(leaves)
    while len(layer) > 1:
        if len(layer) % 2 == 1:
            layer.append(layer[-1])
        nxt: list[bytes] = []
        for i in range(0, len(layer), 2):
            nxt.append(keccak256(layer[i] + layer[i + 1]))
        layer = nxt
    return "0x" + layer[0].hex()
