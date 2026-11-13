"""Unit and property tests for the SDR pricing engine."""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.params import MarketParams
from app.engine.pricing import Position, compute_reference_price, price_impact

# Worked-example params from Phase 1 spec (INR/kWh units, no smoothing).
WORKED_PARAMS = MarketParams(p_fit=3, p_ret=8, k=2, alpha=1.0, c=3, r_ref=0.8)


def _pos(
    pid: str,
    side: str,
    qty: float,
    *,
    reputation: float = 0.8,
    limit_price: float = 5.0,
) -> Position:
    return Position(
        participant_id=pid,
        side=side,  # type: ignore[arg-type]
        qty_kwh=qty,
        limit_price=limit_price,
        reputation=reputation,
    )


def _positions_for_sdr(sdr: float) -> list[Position]:
    """Build simple positions with w=1 and no median capping that yield exact SDR."""
    # S/D = sdr → sell 1, buy 1/sdr when sdr > 0.
    sell_qty = 1.0
    buy_qty = sell_qty / sdr
    return [
        _pos("s0", "sell", sell_qty),
        _pos("b0", "buy", buy_qty),
    ]


# ── Worked values ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "sdr,expected",
    [
        (0.25, 7.71),
        (0.5, 7.00),
        (1.0, 5.50),
        (2.0, 4.00),
        (4.0, 3.29),
    ],
)
def test_worked_sdr_to_price(sdr: float, expected: float) -> None:
    result = compute_reference_price(
        _positions_for_sdr(sdr),
        prev_p_ref=None,
        params=WORKED_PARAMS,
    )
    assert result.sdr == pytest.approx(sdr, abs=1e-9)
    assert result.p_raw == pytest.approx(expected, abs=0.01)
    assert result.p_ref == pytest.approx(expected, abs=0.01)


def test_empty_market_midpoint() -> None:
    result = compute_reference_price([], prev_p_ref=None, params=WORKED_PARAMS)
    assert result.p_ref == pytest.approx(5.5)
    assert result.supply == 0.0
    assert result.demand == 0.0


def test_zero_demand_floor() -> None:
    result = compute_reference_price(
        [_pos("s0", "sell", 10.0)],
        prev_p_ref=None,
        params=WORKED_PARAMS,
    )
    assert result.p_ref == WORKED_PARAMS.p_fit
    assert result.demand == 0.0
    assert result.supply > 0.0


def test_zero_supply_ceiling() -> None:
    result = compute_reference_price(
        [_pos("b0", "buy", 10.0)],
        prev_p_ref=None,
        params=WORKED_PARAMS,
    )
    assert result.p_ref == WORKED_PARAMS.p_ret
    assert result.supply == 0.0
    assert result.demand > 0.0


def test_smoothing_with_prev() -> None:
    params = MarketParams(p_fit=3, p_ret=8, k=2, alpha=0.7, c=3, r_ref=0.8)
    # Balanced market → p_raw = 5.5
    result = compute_reference_price(
        _positions_for_sdr(1.0),
        prev_p_ref=8.0,
        params=params,
    )
    expected = 0.7 * 5.5 + 0.3 * 8.0  # 6.25
    assert result.p_raw == pytest.approx(5.5, abs=0.01)
    assert result.p_ref == pytest.approx(expected, abs=0.01)


def test_median_cap_limits_outlier() -> None:
    # Median of sell qtys [1, 1, 100] = 1; cap = 3. Without cap, supply is huge.
    positions = [
        _pos("s0", "sell", 1.0),
        _pos("s1", "sell", 1.0),
        _pos("s2", "sell", 100.0),
        _pos("b0", "buy", 10.0),
    ]
    capped = compute_reference_price(positions, None, WORKED_PARAMS, apply_median_cap=True)
    uncapped = compute_reference_price(positions, None, WORKED_PARAMS, apply_median_cap=False)
    assert capped.supply == pytest.approx(1.0 + 1.0 + 3.0)  # 100 capped to 3
    assert uncapped.supply == pytest.approx(102.0)
    assert capped.p_raw > uncapped.p_raw  # less supply → higher price


def test_reputation_weight_caps_at_one() -> None:
    # R > R_ref should not exceed weight 1.
    low = compute_reference_price(
        [_pos("s0", "sell", 10.0, reputation=0.4), _pos("b0", "buy", 10.0)],
        None,
        WORKED_PARAMS,
    )
    high = compute_reference_price(
        [_pos("s0", "sell", 10.0, reputation=1.0), _pos("b0", "buy", 10.0)],
        None,
        WORKED_PARAMS,
    )
    # Low rep seller → less effective supply → higher price
    assert low.supply < high.supply
    assert low.p_raw > high.p_raw


def test_price_impact_sell_increase_lowers_price() -> None:
    positions = _positions_for_sdr(1.0)
    delta = price_impact(positions, "s0", delta_kwh=1.0, params=WORKED_PARAMS)
    assert delta < 0.0


def test_price_impact_unknown_participant() -> None:
    with pytest.raises(ValueError, match="participant_id not found"):
        price_impact(_positions_for_sdr(1.0), "missing", 1.0, WORKED_PARAMS)


# ── Hypothesis property tests (≥200 examples each) ─────────────────────────


@st.composite
def market_positions(draw: st.DrawFn) -> list[Position]:
    n_sell = draw(st.integers(min_value=1, max_value=8))
    n_buy = draw(st.integers(min_value=1, max_value=8))
    positions: list[Position] = []
    for i in range(n_sell):
        positions.append(
            _pos(
                f"s{i}",
                "sell",
                draw(st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False)),
                reputation=draw(
                    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
                ),
            )
        )
    for i in range(n_buy):
        positions.append(
            _pos(
                f"b{i}",
                "buy",
                draw(st.floats(min_value=0.1, max_value=50.0, allow_nan=False, allow_infinity=False)),
                reputation=draw(
                    st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
                ),
            )
        )
    return positions


@given(positions=market_positions())
@settings(max_examples=200, deadline=None)
def test_p_ref_always_in_band(positions: list[Position]) -> None:
    result = compute_reference_price(positions, prev_p_ref=None, params=WORKED_PARAMS)
    assert WORKED_PARAMS.p_fit <= result.p_ref <= WORKED_PARAMS.p_ret
    assert math.isfinite(result.p_ref)


@given(
    base=market_positions(),
    extra_sell=st.floats(min_value=0.1, max_value=20.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200, deadline=None)
def test_p_raw_non_increasing_as_supply_grows(base: list[Position], extra_sell: float) -> None:
    # Cap off: isolates the SDR formula (higher supply → lower p_raw). Median-cap
    # book-composition effects are covered by the dedicated cap tests.
    baseline = compute_reference_price(base, None, WORKED_PARAMS, apply_median_cap=False)
    grown = base + [_pos("s_extra", "sell", extra_sell, reputation=1.0)]
    after = compute_reference_price(grown, None, WORKED_PARAMS, apply_median_cap=False)
    assert after.p_raw <= baseline.p_raw + 1e-9


@st.composite
def substantial_market(draw: st.DrawFn) -> list[Position]:
    """Market with enough volume that tiny Sybil offers are relatively small."""
    n_sell = draw(st.integers(min_value=2, max_value=6))
    n_buy = draw(st.integers(min_value=2, max_value=6))
    positions: list[Position] = []
    for i in range(n_sell):
        positions.append(
            _pos(
                f"s{i}",
                "sell",
                draw(st.floats(min_value=5.0, max_value=40.0, allow_nan=False, allow_infinity=False)),
                reputation=draw(
                    st.floats(min_value=0.3, max_value=1.0, allow_nan=False, allow_infinity=False)
                ),
            )
        )
    for i in range(n_buy):
        positions.append(
            _pos(
                f"b{i}",
                "buy",
                draw(st.floats(min_value=5.0, max_value=40.0, allow_nan=False, allow_infinity=False)),
                reputation=draw(
                    st.floats(min_value=0.3, max_value=1.0, allow_nan=False, allow_infinity=False)
                ),
            )
        )
    return positions


@given(base=substantial_market())
@settings(max_examples=200, deadline=None)
def test_sybil_farm_limited_price_impact(base: list[Position]) -> None:
    baseline = compute_reference_price(base, None, WORKED_PARAMS)
    sybils = [_pos(f"sybil_{i}", "sell", 0.01, reputation=0.1) for i in range(50)]
    after = compute_reference_price(base + sybils, None, WORKED_PARAMS)
    band = float(WORKED_PARAMS.p_ret - WORKED_PARAMS.p_fit)
    assert abs(after.p_raw - baseline.p_raw) < 0.01 * band


@given(
    n_others=st.integers(min_value=3, max_value=7),
    peer_qty=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False),
    buy_qty=st.floats(min_value=20.0, max_value=80.0, allow_nan=False, allow_infinity=False),
)
@settings(max_examples=200, deadline=None)
def test_median_cap_reduces_doubling_impact(
    n_others: int,
    peer_qty: float,
    buy_qty: float,
) -> None:
    # Target starts above c*median of peer-dominated book so further growth is capped.
    # With odd n_others all at peer_qty and one large target, median ≈ peer_qty.
    target_qty = peer_qty * float(WORKED_PARAMS.c)  # already at the cap boundary
    positions = [_pos("target", "sell", target_qty)]
    for i in range(n_others):
        positions.append(_pos(f"s{i}", "sell", peer_qty))
    positions.append(_pos("b0", "buy", buy_qty))

    impact_capped = abs(price_impact(positions, "target", target_qty, WORKED_PARAMS))

    before = compute_reference_price(positions, None, WORKED_PARAMS, apply_median_cap=False)
    doubled = [
        _pos(
            p.participant_id,
            p.side,
            p.qty_kwh * 2 if p.participant_id == "target" else p.qty_kwh,
            reputation=p.reputation,
        )
        for p in positions
    ]
    after = compute_reference_price(doubled, None, WORKED_PARAMS, apply_median_cap=False)
    impact_uncapped = abs(after.p_raw - before.p_raw)

    assert impact_capped <= impact_uncapped + 1e-9
