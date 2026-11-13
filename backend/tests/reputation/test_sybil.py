"""Tests for collusion, community, anomaly and false-report detection (Phase 3)."""

from __future__ import annotations

import pytest

from app.reputation.params import DEFAULT_REPUTATION_PARAMS as P
from app.reputation.sybil import (
    Flag,
    ParticipantFeatures,
    PositionRecord,
    WindowTrade,
    anomaly_flags,
    anomaly_scores,
    build_features,
    collusion_communities,
    collusion_flags,
    collusion_scores,
    energy_balance,
    false_report_flags,
    honesty_anomaly,
    pv_plausibility,
    window_trades,
)


def T(seller: str, buyer: str, wh: int, interval: int = 1) -> WindowTrade:
    return WindowTrade(interval=interval, buyer_id=buyer, seller_id=seller, qty_wh=wh)


def _honest_market() -> list[WindowTrade]:
    """4 sellers each selling evenly to 4 buyers over several intervals."""
    sellers = ["s1", "s2", "s3", "s4"]
    buyers = ["b1", "b2", "b3", "b4"]
    return [T(s, b, 500, i) for i in range(1, 6) for s in sellers for b in buyers]


# ─── Collusion scores (acceptance check) ───────────────────────────────────────


def test_wash_trading_pair_scores_near_one() -> None:
    trades = _honest_market()
    for i in range(1, 6):
        trades += [T("w1", "w2", 1000, i), T("w2", "w1", 1000, i)]
    c = collusion_scores(trades)
    assert c["w1"] >= 0.95 and c["w2"] >= 0.95


def test_diversified_trader_scores_near_zero() -> None:
    c = collusion_scores(_honest_market())
    for s in ["s1", "s2", "s3", "s4"]:
        assert c[s] <= 0.05


def test_hand_computed_pc_and_rr() -> None:
    # A sells 3 to B, B sells 1 to A, A sells 4 to C.
    trades = [T("A", "B", 3), T("B", "A", 1), T("A", "C", 4)]
    c = collusion_scores(trades)
    # PC_A = max(3+1, 4) / 8 = 0.5 -> 0 ; RR_A = min(3,1)/(3+4) = 1/7
    assert c["A"] == pytest.approx(1 / 7, abs=1e-6)
    # PC_B = 4/4 = 1 -> 1.0
    assert c["B"] == pytest.approx(1.0)


def test_window_filter() -> None:
    trades = [T("a", "b", 1, i) for i in range(1, 201)]
    w = window_trades(trades, current_interval=200, window=96)
    assert len(w) == 96 and min(t.interval for t in w) == 105


# ─── Communities ───────────────────────────────────────────────────────────────


def test_ring_evades_pairwise_but_louvain_catches_it() -> None:
    """A 3-member ring A->B->C->A has no reciprocal pair and low PC, but forms a closed community."""
    trades = _honest_market()
    for i in range(1, 6):
        trades += [T("r1", "r2", 800, i), T("r2", "r3", 800, i), T("r3", "r1", 800, i)]
    trades.append(T("r1", "b1", 100))  # a little outside trade
    c = collusion_scores(trades)
    assert max(c["r1"], c["r2"], c["r3"]) <= 0.1
    comms = collusion_communities(trades, P, seed=0)
    assert any(set(m["members"]) == {"r1", "r2", "r3"} for m in comms)
    ring = next(m for m in comms if set(m["members"]) == {"r1", "r2", "r3"})
    assert ring["internal_ratio"] > 0.8


def test_honest_market_produces_no_community_flags() -> None:
    assert collusion_communities(_honest_market(), P, seed=0) == []


def test_communities_deterministic() -> None:
    trades = _honest_market() + [T("x", "y", 900), T("y", "x", 900)]
    assert collusion_communities(trades, P, seed=7) == collusion_communities(trades, P, seed=7)


def test_collusion_flags_are_data_only() -> None:
    trades = _honest_market() + [T("w1", "w2", 1000), T("w2", "w1", 1000)]
    scores, flags = collusion_flags(trades, P)
    assert all(isinstance(f, Flag) for f in flags)
    flagged = {pid for f in flags if f.kind == "collusion" for pid in f.participant_ids}
    assert flagged == {"w1", "w2"}
    assert all(f.severity == "high" for f in flags if f.kind == "collusion")


# ─── Anomaly detection ─────────────────────────────────────────────────────────


def _normal_features(n: int) -> list[ParticipantFeatures]:
    return [
        ParticipantFeatures(
            participant_id=f"p{i:02d}",
            size_variance=0.10 + 0.01 * (i % 5),
            acceptance_rate=0.70 + 0.01 * (i % 7),
            volume_share=1.0 / n,
            price_offset=0.02 * ((i % 3) - 1),
        )
        for i in range(n)
    ]


def test_outlier_gets_highest_anomaly_score() -> None:
    feats = _normal_features(30) + [
        ParticipantFeatures("attacker", size_variance=9.0, acceptance_rate=0.05, volume_share=0.4, price_offset=0.9)
    ]
    a = anomaly_scores(feats, seed=0)
    normal = [v for k, v in a.items() if k != "attacker"]
    assert a["attacker"] > max(normal)
    assert a["attacker"] >= 0.3
    assert sorted(normal)[len(normal) // 2] <= 0.1  # typical honest score stays low
    assert all(0.0 <= v <= 1.0 for v in a.values())
    assert any(f.participant_ids == ("attacker",) for f in anomaly_flags(a, threshold=0.3))


def test_anomaly_deterministic_and_small_markets_skipped() -> None:
    feats = _normal_features(20)
    assert anomaly_scores(feats, seed=3) == anomaly_scores(feats, seed=3)
    assert set(anomaly_scores(_normal_features(5)).values()) == {0.0}


def test_build_features() -> None:
    recs = [
        PositionRecord("a", qty_kwh=1.0, limit_price=600, matched_kwh=1.0, p_ref=550),
        PositionRecord("a", qty_kwh=3.0, limit_price=600, matched_kwh=1.0, p_ref=550),
        PositionRecord("b", qty_kwh=2.0, limit_price=500, matched_kwh=2.0, p_ref=550),
    ]
    f = {x.participant_id: x for x in build_features(recs, corridor=500)}
    assert f["a"].size_variance == pytest.approx(1.0)
    assert f["a"].acceptance_rate == pytest.approx(0.5)
    assert f["a"].volume_share == pytest.approx(0.5)
    assert f["a"].price_offset == pytest.approx(0.1)
    assert f["b"].price_offset == pytest.approx(-0.1)


# ─── False reports ─────────────────────────────────────────────────────────────


def test_pv_plausibility() -> None:
    # 4 kW, full sun, 15 min -> 1.0 kWh physical max, 1.1 kWh with tolerance
    assert pv_plausibility(1.0, 4.0, 1.0, P) == 0.0
    assert pv_plausibility(1.65, 4.0, 1.0, P) == pytest.approx(0.5)
    assert pv_plausibility(2.2, 4.0, 1.0, P) == pytest.approx(1.0)
    assert pv_plausibility(0.5, 4.0, 0.0, P) == 1.0  # production reported at night


def test_energy_balance() -> None:
    ok = energy_balance({"a": 1.0, "b": -0.5}, 0.52, P)
    assert ok.ok
    bad = energy_balance({"a": 3.0, "b": -0.5}, 0.5, P)
    assert not bad.ok and bad.mismatch_ratio == pytest.approx(4.0)
    flags = false_report_flags({"a": 0.6, "b": 0.0}, bad, ["a", "b"])
    kinds = sorted(f.kind for f in flags)
    assert kinds == ["energy_imbalance", "false_report"]


def test_honesty_anomaly_takes_worse_signal() -> None:
    assert honesty_anomaly(0.2, 0.7) == 0.7
    assert honesty_anomaly(1.5, 0.0) == 1.0
