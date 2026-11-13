"""Determinism tests for hashing helpers."""

from __future__ import annotations

from app.engine.clearing import ClearedTrade
from app.engine.hashing import canonical_json, input_root, keccak256_hex, result_hash
from app.engine.pricing import Position


def test_canonical_json_sorted_no_spaces() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_keccak_stable() -> None:
    assert keccak256_hex("abc") == keccak256_hex("abc")


def test_input_root_order_invariant() -> None:
    p1 = Position("a", "buy", 1.0, 800, 0.8, node_id="n1")
    p2 = Position("b", "sell", 1.0, 300, 0.8, node_id="n2")
    assert input_root([p1, p2]) == input_root([p2, p1])


def test_result_hash_order_invariant() -> None:
    t1 = ClearedTrade("b0", "s0", 1000, 550.0)
    t2 = ClearedTrade("b1", "s1", 500, 550.0)
    assert result_hash([t1, t2], 550.0) == result_hash([t2, t1], 550.0)
