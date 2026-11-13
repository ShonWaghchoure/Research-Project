"""Tests for fairness and market-outcome metrics, checked against hand calculations (Phase 3)."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.params import DEFAULT_PARAMS, MarketParams
from app.engine.pricing import Position
from app.engine.pricing import price_impact as engine_price_impact
from app.reputation.fairness import (
    TradeView,
    gini,
    grid_backup_frequency,
    grid_trust_density,
    hhi,
    jain_index,
    market_economics,
    matched_shares,
    matching_rate,
    max_price_impact,
    price_impact,
    reputation_gini,
    reputation_mobility,
    seller_satisfaction_index,
    small_actor_parity,
    trade_welfare,
    welfare_efficiency,
    welfare_gains,
)
from app.reputation.tiers import Tier

# ─── Jain ──────────────────────────────────────────────────────────────────────


def test_jain_four_equal_is_one() -> None:
    assert jain_index([0.5, 0.5, 0.5, 0.5]) == pytest.approx(1.0)


def test_jain_one_winner_of_four() -> None:
    assert jain_index([1.0, 0.0, 0.0, 0.0]) == pytest.approx(0.25)


def test_jain_hand_value() -> None:
    # (1+2+3)^2 / (3 * (1+4+9)) = 36 / 42
    assert jain_index([1, 2, 3]) == pytest.approx(36 / 42, abs=1e-6)


def test_matched_shares() -> None:
    f = matched_shares({"a": 1000, "b": 2000, "c": 0}, {"a": 1000, "b": 500})
    assert f == {"a": 1.0, "b": 0.25}


@settings(max_examples=200, deadline=None)
@given(st.lists(st.floats(min_value=0, max_value=100), min_size=1, max_size=50))
def test_jain_bounds(xs: list[float]) -> None:
    j = jain_index(xs)
    assert 1.0 / len(xs) - 1e-6 <= j <= 1.0 + 1e-6


# ─── Gini / HHI ────────────────────────────────────────────────────────────────


def test_gini_equal_is_zero() -> None:
    assert gini([5, 5, 5, 5]) == pytest.approx(0.0)


def test_gini_one_has_all() -> None:
    assert gini([0, 0, 0, 10]) == pytest.approx(0.75)  # (n-1)/n


def test_gini_hand_value() -> None:
    assert gini([1, 2, 3, 4]) == pytest.approx(0.25)


@settings(max_examples=200, deadline=None)
@given(st.lists(st.floats(min_value=0, max_value=1000), min_size=1, max_size=50))
def test_gini_bounds(xs: list[float]) -> None:
    assert 0.0 <= gini(xs) < 1.0


def test_hhi() -> None:
    assert hhi({"a": 50, "b": 50}) == pytest.approx(0.5)
    assert hhi({"a": 100}) == pytest.approx(1.0)
    assert hhi({"a": 25, "b": 25, "c": 25, "d": 25}) == pytest.approx(0.25)
    assert hhi({}) == 0.0


# ─── Small-actor parity ────────────────────────────────────────────────────────


def test_small_actor_parity_proportional_is_one() -> None:
    offered = {"a": 1000, "b": 1000, "c": 4000, "d": 4000}
    matched = {"a": 500, "b": 500, "c": 2000, "d": 2000}
    assert small_actor_parity(offered, matched) == pytest.approx(1.0)


def test_small_actor_parity_small_shut_out() -> None:
    offered = {"a": 1000, "b": 1000, "c": 4000, "d": 4000}
    matched = {"c": 4000, "d": 4000}
    assert small_actor_parity(offered, matched) == pytest.approx(0.0)


def test_small_actor_parity_favoured() -> None:
    # small half offers 2/10 = 0.2 of volume but receives 2/4 = 0.5 of matches -> 2.5
    offered = {"a": 1000, "b": 1000, "c": 4000, "d": 4000}
    matched = {"a": 1000, "b": 1000, "c": 1000, "d": 1000}
    assert small_actor_parity(offered, matched) == pytest.approx(2.5)


# ─── Price impact ──────────────────────────────────────────────────────────────


def _pos(pid: str, side: str, q: float, r: float = 0.9) -> Position:
    return Position(participant_id=pid, side=side, qty_kwh=q, limit_price=500, reputation=r)  # type: ignore[arg-type]


def test_price_impact_uses_engine() -> None:
    ps = [_pos("s1", "sell", 2), _pos("s2", "sell", 2), _pos("b1", "buy", 3), _pos("b2", "buy", 3)]
    corridor = DEFAULT_PARAMS.p_ret - DEFAULT_PARAMS.p_fit
    expected = abs(engine_price_impact(ps, "s1", 2, DEFAULT_PARAMS)) / corridor
    assert price_impact(ps)["s1"] == pytest.approx(expected, abs=1e-6)


def test_median_cap_limits_whale_impact() -> None:
    sellers = [_pos(f"s{i}", "sell", 1.0) for i in range(5)]
    buyers = [_pos(f"b{i}", "buy", 1.0) for i in range(5)]
    whale = _pos("whale", "sell", 20.0)
    impacts = price_impact(sellers + buyers + [whale])
    # whale is capped at 3x median, so doubling its offer changes nothing
    assert impacts["whale"] == pytest.approx(0.0)
    assert max_price_impact(sellers + buyers + [whale]) > 0


# ─── Reputation distribution ───────────────────────────────────────────────────


def test_mobility_frozen_ranking_is_zero() -> None:
    start = {"a": 0.2, "b": 0.5, "c": 0.9}
    end = {"a": 0.3, "b": 0.6, "c": 0.95}
    assert reputation_mobility(start, end) == pytest.approx(0.0)


def test_mobility_reversed_ranking_is_two() -> None:
    start = {"a": 0.2, "b": 0.5, "c": 0.9}
    end = {"a": 0.9, "b": 0.5, "c": 0.2}
    assert reputation_mobility(start, end) == pytest.approx(2.0)


def test_mobility_launch_day_constant_is_zero() -> None:
    assert reputation_mobility({"a": 0.1, "b": 0.1}, {"a": 0.5, "b": 0.3}) == 0.0


def test_reputation_gini_and_trust_density() -> None:
    assert reputation_gini({"a": 0.5, "b": 0.5}) == pytest.approx(0.0)
    tiers = {"a": Tier.TRUSTED, "b": Tier.STANDARD, "c": Tier.PROBATION, "d": Tier.TRUSTED}
    assert grid_trust_density(tiers) == pytest.approx(0.5)


# ─── Welfare and economics ─────────────────────────────────────────────────────


def test_welfare_and_efficiency() -> None:
    ps = [
        Position("b1", "buy", 1.0, limit_price=700, reputation=0.9),
        Position("s1", "sell", 1.0, limit_price=400, reputation=0.9),
    ]
    w = trade_welfare([TradeView("b1", "s1", 1000)], ps)
    assert w == pytest.approx(300.0)
    assert welfare_efficiency(w, 400.0) == pytest.approx(0.75)
    assert welfare_efficiency(0.0, 0.0) == 1.0


def test_welfare_gains_vs_grid() -> None:
    g = welfare_gains([TradeView("b1", "s1", 2000)], 550, DEFAULT_PARAMS, participants=["b1", "s1", "x"])
    assert g == {"b1": 500.0, "s1": 500.0, "x": 0.0}  # 2 kWh * 250 each side


def test_market_economics_hand_values() -> None:
    m = market_economics([TradeView("b1", "s1", 1000)], {"b2": 1000}, {}, 550, DEFAULT_PARAMS)
    assert m.buyer_bill_p2p == pytest.approx(1350.0)  # 1*550 + 1*800
    assert m.buyer_bill_grid_only == pytest.approx(1600.0)
    assert m.buyer_saving_pct == pytest.approx(15.625)
    assert m.seller_revenue_p2p == pytest.approx(550.0)
    assert m.seller_uplift_pct == pytest.approx(83.333333, abs=1e-5)
    assert m.buyer_surplus_share == pytest.approx(0.5)  # p_ref is the corridor midpoint


def test_surplus_split_follows_price() -> None:
    p = MarketParams()
    low = market_economics([TradeView("b", "s", 1000)], {}, {}, 350, p)
    assert low.buyer_surplus_share == pytest.approx(0.9)


def test_seller_satisfaction_and_matching_rate() -> None:
    assert seller_satisfaction_index({"s1": 10, "s2": 10, "s3": 0}, {"s1": 5}) == pytest.approx(0.5)
    assert matching_rate(4000, 10_000, 3000) == pytest.approx(0.75)
    assert matching_rate(0, 1000, 0) == 1.0


def test_grid_backup_frequency_reveals_structural_exclusion() -> None:
    """Edge case 14: 'iso' is unmatched every interval even though each interval looks fine."""
    history = [({"a": 1000, "iso": 1000}, {"a": 1000})] * 4 + [({"a": 1000}, {"a": 0})]
    freq = grid_backup_frequency(history)
    assert freq["iso"] == pytest.approx(1.0)
    assert freq["a"] == pytest.approx(0.2)
