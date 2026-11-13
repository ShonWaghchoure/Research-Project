"""Tests for tiers, volume caps, hysteresis and the newcomer cold-start path (Phase 3)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.reputation.params import DEFAULT_REPUTATION_PARAMS as P
from app.reputation.score import BetaState, Evidence, initial_state, reputation, update
from app.reputation.tiers import (
    Tier,
    classify,
    intervals_to_tier,
    matching_reputation,
    volume_cap_kwh,
)

# z = 0 makes R equal the mean exactly, so states can be built for a precise R.
EXACT = replace(P, z=0.0)


def _state(r: float, count: int) -> BetaState:
    return BetaState(alpha=r * 1000, beta=(1 - r) * 1000, evidence_count=count)


@pytest.mark.parametrize(
    "r, count, expected",
    [
        (0.10, 200, Tier.SUSPENDED),
        (0.20, 200, Tier.PROBATION),
        (0.50, 10, Tier.PROBATION),  # too little evidence
        (0.50, 200, Tier.STANDARD),
        (0.85, 50, Tier.STANDARD),  # high R but not enough evidence for Trusted
        (0.85, 100, Tier.TRUSTED),
    ],
)
def test_spec_tier_rules(r: float, count: int, expected: Tier) -> None:
    assert classify(_state(r, count), EXACT) is expected


def test_high_severity_flag_suspends() -> None:
    assert classify(_state(0.95, 500), EXACT, high_severity_flag=True) is Tier.SUSPENDED


def test_volume_cap() -> None:
    assert volume_cap_kwh(10.0, 0.0) == pytest.approx(2.0)
    assert volume_cap_kwh(10.0, 1.0) == pytest.approx(10.0)
    assert volume_cap_kwh(10.0, 0.5) == pytest.approx(6.0)


# ─── Cold start (report 5.4, edge case 9) ──────────────────────────────────────


def test_newcomer_is_probation_not_suspended() -> None:
    s = initial_state(P)
    assert reputation(s, P) < P.suspended_below  # 0.098 under the prior
    assert classify(s, P) is Tier.PROBATION


def test_newcomer_can_enter_matching() -> None:
    s = initial_state(P)
    assert matching_reputation(s, classify(s, P), P) >= P.rho_min


def test_newcomer_who_defaults_loses_grace() -> None:
    s = update(initial_state(P), Evidence(r_del=0.0, r_rev=0.0, volume_kwh=1), P)
    assert classify(s, P) is Tier.SUSPENDED
    assert matching_reputation(s, Tier.SUSPENDED, P) == 0.0


def test_newcomer_climbs_to_trusted_without_ever_being_excluded() -> None:
    s = initial_state(P)
    for _ in range(100):
        tier = classify(s, P)
        assert tier is not Tier.SUSPENDED
        assert matching_reputation(s, tier, P) >= P.rho_min
        s = update(s, Evidence(volume_kwh=1), P)
    assert classify(s, P) is Tier.TRUSTED


def test_intervals_to_trusted() -> None:
    # Evidence gate (100 intervals) dominates once R passes 0.8 at ~20 intervals.
    assert intervals_to_tier(initial_state(P), Tier.TRUSTED, P) == 100
    assert intervals_to_tier(initial_state(P), Tier.STANDARD, P) == 20


# ─── Hysteresis (edge case 12) ─────────────────────────────────────────────────


def test_hysteresis_prevents_flicker() -> None:
    just_below = _state(0.29, 200)
    assert classify(just_below, EXACT) is Tier.PROBATION
    assert classify(just_below, EXACT, prev_tier=Tier.STANDARD) is Tier.STANDARD
    clearly_below = _state(0.27, 200)
    assert classify(clearly_below, EXACT, prev_tier=Tier.STANDARD) is Tier.PROBATION


def test_hysteresis_never_upgrades() -> None:
    assert classify(_state(0.5, 200), EXACT, prev_tier=Tier.PROBATION) is Tier.STANDARD
    assert classify(_state(0.79, 200), EXACT, prev_tier=Tier.STANDARD) is Tier.STANDARD
    assert classify(_state(0.79, 200), EXACT, prev_tier=Tier.TRUSTED) is Tier.TRUSTED


def test_matching_reputation_passes_true_r_for_standard() -> None:
    s = _state(0.5, 200)
    assert matching_reputation(s, Tier.STANDARD, EXACT) == pytest.approx(0.5)
