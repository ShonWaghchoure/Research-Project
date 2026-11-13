"""Tests for the Beta reputation model (Phase 3)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.reputation.params import DEFAULT_REPUTATION_PARAMS as P
from app.reputation.score import (
    BetaState,
    Evidence,
    delivery_ratio,
    evidence_score,
    evidence_weight,
    initial_state,
    reputation,
    reveal_miss_evidence,
    run_history,
    score_bp,
    score_display,
    update,
)
from app.reputation.tiers import Tier, classify

PERFECT = Evidence(volume_kwh=P.v_ref_kwh)  # s_t = 1, n_t = 1
FAILED = Evidence(r_del=0.0, r_rev=0.0, anomaly=1.0, collusion=1.0, volume_kwh=P.v_ref_kwh)  # s_t = 0


def _after(n: int, ev: Evidence = PERFECT, phi: float = 1.0) -> BetaState:
    hist = run_history([ev] * n, P, phi=phi)
    return hist[-1] if hist else initial_state(P)


# ─── Spec worked table ─────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "n, expected",
    [(0, 0.098), (1, 0.276), (2, 0.400), (5, 0.606), (20, 0.856), (50, 0.936)],
)
def test_worked_table_phi_one(n: int, expected: float) -> None:
    assert reputation(_after(n), P) == pytest.approx(expected, abs=0.002)


def test_prior_values() -> None:
    s = initial_state(P)
    assert (s.alpha, s.beta, s.evidence_count) == (1.0, 2.0, 0)


# ─── Evidence ──────────────────────────────────────────────────────────────────


def test_evidence_score_weights() -> None:
    assert evidence_score(PERFECT) == pytest.approx(1.0)
    assert evidence_score(FAILED) == pytest.approx(0.0)
    # Only delivery failed -> s = 1 - 0.45
    assert evidence_score(Evidence(r_del=0.0, volume_kwh=1)) == pytest.approx(0.55)
    # Only collusion suspicion -> s = 1 - 0.20
    assert evidence_score(Evidence(collusion=1.0, volume_kwh=1)) == pytest.approx(0.80)


def test_evidence_weight_scales_with_volume() -> None:
    assert evidence_weight(Evidence(volume_kwh=0.0)) == 0.0
    assert evidence_weight(Evidence(volume_kwh=P.v_ref_kwh / 4)) == pytest.approx(0.25)
    assert evidence_weight(Evidence(volume_kwh=P.v_ref_kwh * 10)) == 1.0


def test_delivery_ratio() -> None:
    assert delivery_ratio(1000, 1000) == 1.0
    assert delivery_ratio(1000, 600) == pytest.approx(0.6)
    assert delivery_ratio(1000, 1500) == 1.0
    assert delivery_ratio(0, 0) == 1.0


def test_failure_penalised_about_three_times_success() -> None:
    base = BetaState(alpha=10.0, beta=4.0, evidence_count=30)
    ok = update(base, PERFECT, P, phi=1.0)
    bad = update(base, FAILED, P, phi=1.0)
    # pseudo-count increments: success +1 alpha, failure +kappa beta
    assert ok.alpha - base.alpha == pytest.approx(1.0)
    assert bad.beta - base.beta == pytest.approx(3.0)
    gain = reputation(ok) - reputation(base)
    loss = reputation(base) - reputation(bad)
    assert gain > 0 and loss >= 3 * gain


def test_zero_volume_adds_no_evidence() -> None:
    s = _after(10)
    idle = update(s, Evidence(volume_kwh=0.0), P, phi=1.0)
    assert idle == s
    none = update(s, None, P, phi=1.0)
    assert none == s


def test_partial_delivery_is_lighter_than_non_delivery() -> None:
    """Edge cases 6 / 16: honest partial shortfall costs less than full non-delivery."""
    s = _after(30)
    partial = update(s, Evidence(r_del=0.8, volume_kwh=1), P)
    full = update(s, Evidence(r_del=0.0, volume_kwh=1), P)
    assert reputation(full) < reputation(partial) < reputation(update(s, PERFECT, P))


def test_reveal_miss_is_penalised() -> None:
    s = _after(30)
    missed = update(s, reveal_miss_evidence(), P)
    assert missed.evidence_count == s.evidence_count + 1
    assert reputation(missed) < reputation(update(s, None, P))


# ─── Forgetting ────────────────────────────────────────────────────────────────


def test_phi_matches_half_life() -> None:
    assert P.phi ** P.half_life_intervals == pytest.approx(0.5)


def test_trusted_participant_who_stops_delivering_loses_trusted() -> None:
    s = _after(300, phi=P.phi)
    assert classify(s, P) is Tier.TRUSTED
    tier = Tier.TRUSTED
    lazy = Evidence(r_del=0.0, volume_kwh=1)  # stops delivering, still reveals and is honest
    for _ in range(100):
        s = update(s, lazy, P)
        tier = classify(s, P, prev_tier=tier)
    assert tier is not Tier.TRUSTED


def test_old_failures_fade_with_forgetting() -> None:
    """A participant that failed long ago recovers faster with phi < 1 than without forgetting."""
    hist = [FAILED] * 20 + [PERFECT] * 1500
    with_forget = run_history(hist, P)[-1]
    no_forget = run_history(hist, P, phi=1.0)[-1]
    assert reputation(with_forget) > reputation(no_forget)
    assert classify(with_forget, P) is Tier.TRUSTED


def test_idle_decay_keeps_mean_but_widens_uncertainty() -> None:
    """Edge case 10: under the spec decay, a long-idle participant keeps its mean but R drops."""
    s = _after(300, phi=P.phi)
    idle = s
    for _ in range(2000):
        idle = update(idle, None, P)
    assert idle.alpha / (idle.alpha + idle.beta) == pytest.approx(s.alpha / (s.alpha + s.beta))
    assert reputation(idle) < reputation(s)


def test_decay_to_prior_option_pulls_toward_prior() -> None:
    params = replace(P, decay_to_prior=True)
    s = run_history([PERFECT] * 300, params)[-1]
    for _ in range(20_000):
        s = update(s, None, params)
    assert s.alpha == pytest.approx(params.alpha0, abs=0.01)
    assert s.beta == pytest.approx(params.beta0, abs=0.01)


# ─── Encoding / properties ─────────────────────────────────────────────────────


def test_score_encodings() -> None:
    assert score_bp(0.8562) == 8562
    assert score_bp(1.5) == 10000
    assert score_display(0.5) == 50


@settings(max_examples=300, deadline=None)
@given(
    alpha=st.floats(min_value=0.01, max_value=500),
    beta=st.floats(min_value=0.01, max_value=500),
    s=st.floats(min_value=0, max_value=1),
    v=st.floats(min_value=0, max_value=5),
)
def test_reputation_always_in_unit_interval(alpha: float, beta: float, s: float, v: float) -> None:
    st0 = BetaState(alpha, beta, 0)
    nxt = update(st0, Evidence(r_del=s, volume_kwh=v), P)
    assert 0.0 <= reputation(nxt) <= 1.0


@settings(max_examples=300, deadline=None)
@given(
    alpha=st.floats(min_value=0.5, max_value=500),
    beta=st.floats(min_value=0.5, max_value=500),
)
def test_success_never_lowers_and_failure_never_raises(alpha: float, beta: float) -> None:
    s0 = BetaState(alpha, beta, 0)
    assert reputation(update(s0, PERFECT, P, phi=1.0)) >= reputation(s0) - 1e-6
    assert reputation(update(s0, FAILED, P, phi=1.0)) <= reputation(s0) + 1e-6
