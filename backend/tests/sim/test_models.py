"""Unit tests for the physical models, meters, bots and baselines (Phase 4)."""

from __future__ import annotations

import numpy as np
import pytest

from app.core.params import DEFAULT_PARAMS as P
from app.engine.grid import default_13_node_feeder
from app.engine.pricing import Position
from app.sim.baselines import clear, clear_b0, clear_b1, clear_b2
from app.sim.bots import (
    Defector,
    FalseReporter,
    Lazy,
    Manipulator,
    NonRevealer,
    RingMember,
    Strategic,
    SybilIdentity,
)
from app.sim.forecast import (
    EV,
    SLOTS_PER_DAY,
    Battery,
    Weather,
    clear_sky_factor,
    ev_sessions,
    load_shape,
)
from app.sim.meters import MeterKey, MeterReading, SignedReading, verify

FEEDER = default_13_node_feeder()

# ─── Forecast models ───────────────────────────────────────────────────────────


def test_load_shape_sums_to_one_with_evening_peak() -> None:
    shape = [load_shape(s) for s in range(SLOTS_PER_DAY)]
    assert sum(shape) == pytest.approx(1.0)
    assert max(range(SLOTS_PER_DAY), key=lambda s: shape[s]) // 4 in (19, 20, 21)


def test_clear_sky_zero_at_night_peak_at_noon() -> None:
    assert clear_sky_factor(0) == 0.0 and clear_sky_factor(23 * 4) == 0.0
    assert clear_sky_factor(12 * 4) == pytest.approx(1.0)
    assert max(range(SLOTS_PER_DAY), key=clear_sky_factor) == 48


def test_weather_is_seeded_and_bounded() -> None:
    a = Weather.generate(192, np.random.default_rng(1))
    b = Weather.generate(192, np.random.default_rng(1))
    assert a == b
    assert all(0.05 <= c <= 1.0 for c in a.cloud)
    assert a.forecast(10) == a.actual(9)  # persistence forecast


def test_battery_charge_and_discharge_limits() -> None:
    b = Battery(capacity_kwh=5.0, soc_kwh=4.9, p_max_kw=4.0)
    residual = b.dispatch(-2.0)  # surplus: only ~0.1 kWh of room
    assert b.soc_kwh <= 5.0 + 1e-9 and residual < -1.8
    b = Battery(capacity_kwh=5.0, soc_kwh=5.0, p_max_kw=2.0)
    residual = b.dispatch(3.0)  # deficit: limited by 2 kW * 0.25 h = 0.5 kWh
    assert residual == pytest.approx(2.5)


def test_ev_v2g_respects_reserve_and_target() -> None:
    """Edge cases 7 and 8: no sale below reserve, and the target must stay reachable."""
    ev = EV(capacity_kwh=40.0, p_max_kw=7.2, v2g=True, soc_kwh=9.0, arrival=0, departure=40)
    assert ev.v2g_sell_kwh(0) == pytest.approx(min(1.8, 9.0 - 8.0))  # reserve 8 kWh
    tight = EV(capacity_kwh=40.0, p_max_kw=7.2, v2g=True, soc_kwh=30.0, arrival=0, departure=2)
    # 0.25 h of charging left after this slot: 30 + 1.8 - 32 < 0 -> nothing to sell
    assert tight.v2g_sell_kwh(0) == 0.0
    no_v2g = EV(capacity_kwh=40.0, p_max_kw=7.2, v2g=False, soc_kwh=35.0, arrival=0, departure=40)
    assert no_v2g.v2g_sell_kwh(0) == 0.0


def test_ev_charge_and_sessions() -> None:
    ev = EV(capacity_kwh=40.0, p_max_kw=3.3, v2g=False, soc_kwh=31.5, arrival=0, departure=10)
    assert ev.charge_kwh(0) == pytest.approx(0.5)  # need 0.5 < 0.825 step
    assert ev.charge_kwh(10) == 0.0  # departed
    sessions = ev_sessions(3 * SLOTS_PER_DAY, np.random.default_rng(0), 40.0)
    assert len(sessions) == 3 and all(a < d for a, d, _ in sessions)


# ─── Meters ────────────────────────────────────────────────────────────────────


def test_meter_signature_roundtrip_and_tamper() -> None:
    key = MeterKey(42, "p001")
    assert MeterKey(42, "p001").address == key.address  # deterministic
    reading = MeterReading("p001", 5, export_wh=1200, import_wh=0, pv_wh=1500)
    signed = key.sign(reading)
    assert verify(signed, key.address)
    tampered = SignedReading(MeterReading("p001", 5, 9999, 0, 1500), signed.signature)
    assert not verify(tampered, key.address)
    assert not verify(signed, MeterKey(42, "p002").address)


# ─── Bots ──────────────────────────────────────────────────────────────────────


def test_bot_behaviours() -> None:
    assert Lazy(shortfall=0.4).deliver(0, 1000, 1000) == 600
    assert Strategic(inflate=0.5).shape_position(0, "sell", 2.0, 400, 300, 800) == ("sell", 3.0, 300)
    assert Manipulator(withhold=0.3).shape_position(0, "sell", 10.0, 350, 300, 800) == ("sell", pytest.approx(7.0), 350)
    assert SybilIdentity().shape_position(0, "sell", 0, 0, 300, 800) == ("buy", 0.4, 800)
    d = Defector(after=10)
    assert d.deliver(9, 500, 500) == 500 and d.deliver(10, 500, 500) == 0
    fr = FalseReporter(inflate=1.0, start=5, end=6)
    assert fr.report_pv(4, 1.0) == 1.0 and fr.report_pv(5, 1.0) == 2.0
    assert fr.report_delivery(5, 300, 1000) == 1000 and fr.report_delivery(6, 300, 1000) == 300
    rng = np.random.default_rng(0)
    reveals = [NonRevealer(p_reveal=0.5).reveals(t, rng) for t in range(400)]
    assert 0.4 < sum(reveals) / 400 < 0.6


def test_ring_trades_are_reciprocal() -> None:
    members = ["a", "b"]
    ring = RingMember(qty_kwh=1.0)
    even = ring.bilateral(0, members, "a") + ring.bilateral(0, members, "b")
    assert sorted(even) == [("a", "b", 1.0), ("b", "a", 1.0)]
    assert not ring.public_market


# ─── Baselines ─────────────────────────────────────────────────────────────────


def _book() -> list[Position]:
    return [
        Position("s1", "sell", 3.0, 320, 0.9, node_id="n1"),
        Position("s2", "sell", 1.0, 320, 0.9, node_id="n2"),
        Position("b1", "buy", 2.0, 780, 0.9, node_id="n3"),
    ]


def test_b0_grid_only() -> None:
    r = clear_b0(_book(), FEEDER, P)
    assert r.trades == () and r.unmatched_buy_wh == {"b1": 2000}


def test_b1_fixed_price_first_come() -> None:
    r = clear_b1(_book(), FEEDER, P, np.random.default_rng(0))
    assert all(t.price == 550 for t in r.trades)
    assert sum(t.qty_wh for t in r.trades) == 2000
    sold = {s: sum(t.qty_wh for t in r.trades if t.seller_id == s) for s in ("s1", "s2")}
    assert sold["s1"] <= 3000 and sold["s2"] <= 1000


def test_b2_proportional_three_to_one() -> None:
    r = clear_b2(_book(), FEEDER, P, None)
    sold = {s: sum(t.qty_wh for t in r.trades if t.seller_id == s) for s in ("s1", "s2")}
    assert sold["s1"] == 1500 and sold["s2"] == 500
    assert all(t.price == r.p_ref for t in r.trades)


def test_unknown_mode_rejected() -> None:
    with pytest.raises(ValueError):
        clear("B9", _book(), FEEDER, P, None, np.random.default_rng(0))
