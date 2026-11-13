"""Tests for EV helpers."""

from __future__ import annotations

from app.engine.ev import ev_buy_limit_price, ev_urgency, ev_v2g_sell_qty


def test_urgency_raises_limit_price() -> None:
    low = ev_buy_limit_price(300, 800, e_need_kwh=1.0, p_max_kw=7.0, t_left_h=10.0)
    high = ev_buy_limit_price(300, 800, e_need_kwh=20.0, p_max_kw=7.0, t_left_h=1.0)
    assert low < high
    assert high == 800  # fully urgent → retail


def test_urgency_clip() -> None:
    assert ev_urgency(0.0, 7.0, 1.0) == 0.0
    assert ev_urgency(100.0, 7.0, 1.0) == 1.0


def test_v2g_sell_qty() -> None:
    assert ev_v2g_sell_qty(soc_kwh=40.0, e_target_kwh=30.0, v2g=True) == 10.0
    assert ev_v2g_sell_qty(soc_kwh=40.0, e_target_kwh=30.0, v2g=False) == 0.0
    assert ev_v2g_sell_qty(soc_kwh=20.0, e_target_kwh=30.0, v2g=True) == 0.0
