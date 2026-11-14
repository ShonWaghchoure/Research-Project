"""Integration tests for matching + clearing engine."""

from __future__ import annotations

import time

import pytest

from app.core.params import MarketParams
from app.engine.clearing import clear_interval
from app.engine.ev import ev_buy_limit_price
from app.engine.grid import default_13_node_feeder, scale_all_capacities, with_line_capacities
from app.engine.pricing import Position

# Use INR-scale prices for readability in engine tests.
PARAMS = MarketParams(
    p_fit=3,
    p_ret=8,
    k=2,
    alpha=1.0,
    c=3,
    r_ref=0.8,
    rho_min=0.3,
    r_cap=0.9,
    beta=0.25,
    match_lambda=1.0,
    dt_hours=0.25,
)


def _pos(
    pid: str,
    side: str,
    qty: float,
    limit: float,
    *,
    rep: float = 0.8,
    node: str = "n1",
    rmin: float = 0.0,
) -> Position:
    return Position(
        participant_id=pid,
        side=side,  # type: ignore[arg-type]
        qty_kwh=qty,
        limit_price=limit,
        reputation=rep,
        node_id=node,
        min_seller_reputation=rmin,
    )


def test_no_participant_exceeds_quantity() -> None:
    feeder = default_13_node_feeder(capacity_kw=1e6)
    positions = [
        _pos("b0", "buy", 5.0, 8.0, node="n4"),
        _pos("b1", "buy", 2.0, 8.0, node="n5"),
        _pos("s0", "sell", 4.0, 3.0, node="n8"),
        _pos("s1", "sell", 4.0, 3.0, node="n9"),
    ]
    result = clear_interval(positions, feeder, PARAMS, None)
    bought = {p.participant_id: 0 for p in positions if p.side == "buy"}
    sold = {p.participant_id: 0 for p in positions if p.side == "sell"}
    for t in result.trades:
        bought[t.buyer_id] += t.qty_wh
        sold[t.seller_id] += t.qty_wh
        assert t.price == pytest.approx(result.p_ref)
    assert bought["b0"] <= 5000
    assert bought["b1"] <= 2000
    assert sold["s0"] <= 4000
    assert sold["s1"] <= 4000


def test_all_trades_at_p_ref() -> None:
    feeder = default_13_node_feeder(capacity_kw=1e6)
    positions = [
        _pos("b0", "buy", 3.0, 8.0, node="n4"),
        _pos("s0", "sell", 3.0, 3.0, node="n8"),
    ]
    result = clear_interval(positions, feeder, PARAMS, None)
    assert result.trades
    assert all(t.price == result.p_ref for t in result.trades)


def test_zero_capacity_blocks_crossing_trade() -> None:
    feeder = default_13_node_feeder(capacity_kw=1e6)
    # Zero the only trunk leaving root toward seller's branch (n3) and buyer's (n1)
    # Put buyer on n4 (under n1), seller on n8 (under n3); zero both root laterals
    # so no peer path and no grid residual path can carry power across.
    feeder = with_line_capacities(
        feeder,
        {"l_n0_n1": 0.0, "l_n0_n3": 0.0},
    )
    positions = [
        _pos("b0", "buy", 2.0, 8.0, node="n4"),
        _pos("s0", "sell", 2.0, 3.0, node="n8"),
    ]
    result = clear_interval(positions, feeder, PARAMS, None)
    # Either no peer trades, or solver reports infeasible / empty match
    assert sum(t.qty_wh for t in result.trades) == 0


def test_large_capacity_equals_unconstrained() -> None:
    tight = default_13_node_feeder(capacity_kw=1e6)
    huge = scale_all_capacities(tight, 1e9)
    positions = [
        _pos("b0", "buy", 5.0, 8.0, node="n4"),
        _pos("b1", "buy", 5.0, 8.0, node="n5"),
        _pos("s0", "sell", 4.0, 3.0, node="n8"),
        _pos("s1", "sell", 6.0, 3.0, node="n11"),
    ]
    a = clear_interval(positions, tight, PARAMS, None)
    b = clear_interval(positions, huge, PARAMS, None)
    assert a.result_hash == b.result_hash
    assert sum(t.qty_wh for t in a.trades) == sum(t.qty_wh for t in b.trades)


def test_proportional_share_two_sellers() -> None:
    # Two sellers 3:1 with low demand → matched volume ≈ 3:1
    feeder = default_13_node_feeder(capacity_kw=1e6)
    positions = [
        _pos("b0", "buy", 4.0, 8.0, node="n0"),
        _pos("s_big", "sell", 9.0, 3.0, node="n0"),
        _pos("s_small", "sell", 3.0, 3.0, node="n0"),
    ]
    # Force SDR > 1 so sellers are long side (supply 12, demand 4)
    result = clear_interval(positions, feeder, PARAMS, None)
    sold = {"s_big": 0, "s_small": 0}
    for t in result.trades:
        sold[t.seller_id] += t.qty_wh
    total = sold["s_big"] + sold["s_small"]
    assert total > 0
    ratio = sold["s_big"] / max(sold["s_small"], 1)
    assert 2.0 <= ratio <= 4.5  # about 3:1 with solver / rounding tolerance


def test_below_rho_min_gets_no_peer_trade() -> None:
    feeder = default_13_node_feeder(capacity_kw=1e6)
    positions = [
        _pos("b0", "buy", 5.0, 8.0, rep=0.8, node="n4"),
        _pos("s_bad", "sell", 5.0, 3.0, rep=0.1, node="n8"),  # below rho_min
        _pos("s_ok", "sell", 5.0, 3.0, rep=0.8, node="n9"),
    ]
    result = clear_interval(positions, feeder, PARAMS, None)
    assert all(t.seller_id != "s_bad" for t in result.trades)
    assert any(t.seller_id == "s_ok" for t in result.trades)


def test_ev_urgency_raises_limit_price() -> None:
    calm = ev_buy_limit_price(PARAMS.p_fit, PARAMS.p_ret, 1.0, 7.0, 8.0)
    urgent = ev_buy_limit_price(PARAMS.p_fit, PARAMS.p_ret, 20.0, 7.0, 1.0)
    assert urgent > calm


def test_clear_interval_deterministic_hashes() -> None:
    feeder = default_13_node_feeder(capacity_kw=1e6)
    positions = [
        _pos("b0", "buy", 3.0, 8.0, node="n4"),
        _pos("b1", "buy", 2.0, 7.0, node="n5"),
        _pos("s0", "sell", 4.0, 3.0, node="n8"),
        _pos("s1", "sell", 1.5, 4.0, node="n11"),
    ]
    a = clear_interval(positions, feeder, PARAMS, None)
    b = clear_interval(positions, feeder, PARAMS, None)
    assert a.input_root == b.input_root
    assert a.result_hash == b.result_hash
    assert a.trades == b.trades


def test_line_loadings_within_capacity() -> None:
    feeder = default_13_node_feeder(capacity_kw=50.0)
    positions = [
        _pos("b0", "buy", 2.0, 8.0, node="n4"),
        _pos("s0", "sell", 2.0, 3.0, node="n8"),
    ]
    result = clear_interval(positions, feeder, PARAMS, None)
    caps = {line.id: line.capacity_kw for line in feeder.lines}
    for line_id, loading in result.line_loading_kw.items():
        assert abs(loading) <= caps[line_id] + 1e-5


@pytest.mark.parametrize("n", [50, 100, 200])
def test_clearing_benchmark(n: int, capsys: pytest.CaptureFixture[str]) -> None:
    feeder = default_13_node_feeder(capacity_kw=1e6)
    positions: list[Position] = []
    nodes = [f"n{i}" for i in range(1, 13)]
    for i in range(n // 2):
        positions.append(
            _pos(f"b{i}", "buy", 1.0 + (i % 5) * 0.1, 8.0, node=nodes[i % len(nodes)])
        )
        positions.append(
            _pos(f"s{i}", "sell", 1.0 + (i % 3) * 0.1, 3.0, node=nodes[(i + 3) % len(nodes)])
        )
    t0 = time.perf_counter()
    result = clear_interval(positions, feeder, PARAMS, None)
    elapsed = time.perf_counter() - t0
    print(f"clearing_benchmark n={n} elapsed_s={elapsed:.3f} trades={len(result.trades)}")
    assert elapsed < 10.0  # well under "a few seconds" with headroom for CI
    assert result.result_hash.startswith("0x")


def test_kwh_to_wh_floor_does_not_lose_a_watt_hour():
    """Bug fix: float round-trip floored e.g. 1001 Wh to 1000 Wh (1,482 of 1..200,000)."""
    from app.engine.clearing import _kwh_to_wh_floor

    assert all(_kwh_to_wh_floor(q / 1000.0) == q for q in range(1, 200_001))
    assert _kwh_to_wh_floor(1.2345678) == 1234  # genuine fractions still floor
