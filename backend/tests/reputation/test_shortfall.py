"""Tests for shortfall settlement amounts (Phase 3)."""

from __future__ import annotations

import pytest

from app.core.params import DEFAULT_PARAMS
from app.reputation.shortfall import settle_shortfall


def test_hand_computed_shortfall() -> None:
    # promised 2 kWh, delivered 1.5 kWh, p_ref 550 paise/kWh, p_ret 800, f 0.1
    r = settle_shortfall(2000, 1500, 550, DEFAULT_PARAMS)
    assert r.shortfall_wh == 500
    assert r.payment_paise == 825  # 1.5 kWh * 550
    assert r.compensation_paise == 125  # 0.5 kWh * (800 - 550)
    assert r.penalty_paise == 27  # 0.1 * 0.5 kWh * 550 = 27.5 -> floor
    assert all(isinstance(x, int) for x in (r.payment_paise, r.compensation_paise, r.penalty_paise))


def test_full_delivery_has_no_shortfall() -> None:
    r = settle_shortfall(1000, 1000, 600)
    assert (r.shortfall_wh, r.compensation_paise, r.penalty_paise) == (0, 0, 0)
    assert r.payment_paise == 600


def test_over_delivery_pays_only_promised() -> None:
    r = settle_shortfall(1000, 1400, 600)
    assert r.delivered_wh == 1000 and r.shortfall_wh == 0 and r.payment_paise == 600


def test_total_non_delivery() -> None:
    r = settle_shortfall(1000, 0, 500)
    assert r.payment_paise == 0
    assert r.compensation_paise == 300
    assert r.penalty_paise == 50


def test_p_ref_at_retail_means_no_compensation() -> None:
    r = settle_shortfall(1000, 0, 800)
    assert r.compensation_paise == 0 and r.penalty_paise == 80


def test_negative_input_rejected() -> None:
    with pytest.raises(ValueError):
        settle_shortfall(-1, 0, 500)
