"""Reputation tiers, volume caps and the matching-eligibility hand-off (pure functions).

Spec tiers (GEMINI.md Phase 3):
    Suspended  R < 0.15 or a high-severity flag
    Probation  R < 0.30 or evidence_count < 20
    Standard   0.30 <= R < 0.80
    Trusted    R >= 0.80 and evidence_count >= 100
    Q_max = Q_base * (0.2 + 0.8 * R)

Additions (docs/DECISIONS.md, Phase 3):
  * Uncertainty never suspends: the prior gives R = 0.098 < 0.15, which would suspend every
    newcomer, and idle forgetting widens sigma and lowers R for anyone who stops trading. A
    participant that cannot trade can never earn evidence, so R < 0.15 only suspends when the
    Beta mean is also below the prior mean (net-negative evidence). Otherwise it is Probation.
  * Probation may trade P2P under the volume cap: ``matching_reputation`` lifts it to rho_min so
    the Phase 2 matching gate admits it. Only Suspended participants are excluded.
  * Hysteresis: a participant only drops a tier when R falls ``hysteresis`` below the boundary,
    so scores hovering at a threshold do not flicker (edge case 12).
"""

from __future__ import annotations

from enum import Enum

from app.reputation.params import DEFAULT_REPUTATION_PARAMS, ReputationParams
from app.reputation.score import BetaState, Evidence, initial_state, mean, reputation, update


class Tier(str, Enum):
    SUSPENDED = "suspended"
    PROBATION = "probation"
    STANDARD = "standard"
    TRUSTED = "trusted"


_RANK = {Tier.SUSPENDED: 0, Tier.PROBATION: 1, Tier.STANDARD: 2, Tier.TRUSTED: 3}


def _raw_tier(r: float, mu: float, count: int, prior_mu: float, params: ReputationParams, h: float) -> Tier:
    newcomer = count < params.newcomer_evidence
    # Uncertainty alone never suspends: a low R needs net-negative evidence (mean below the prior).
    if r < params.suspended_below - h and mu < prior_mu - 1e-9:
        return Tier.SUSPENDED
    if newcomer or r < params.probation_below - h:
        return Tier.PROBATION
    if r >= params.trusted_at - h and count >= params.trusted_evidence:
        return Tier.TRUSTED
    return Tier.STANDARD


def classify(
    state: BetaState,
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
    *,
    prev_tier: Tier | None = None,
    high_severity_flag: bool = False,
) -> Tier:
    """Tier for ``state``. Pass ``prev_tier`` to apply hysteresis on downgrades."""
    if high_severity_flag:
        return Tier.SUSPENDED
    r = reputation(state, params)
    mu = mean(state)
    prior_mu = mean(initial_state(params))
    raw = _raw_tier(r, mu, state.evidence_count, prior_mu, params, 0.0)
    if prev_tier is None or _RANK[raw] >= _RANK[prev_tier]:
        return raw
    # Downgrade: only if R is below the boundary by more than the hysteresis margin.
    lenient = _raw_tier(r, mu, state.evidence_count, prior_mu, params, params.hysteresis)
    return lenient if _RANK[lenient] < _RANK[prev_tier] else prev_tier


def volume_cap_kwh(q_base_kwh: float, r: float, params: ReputationParams = DEFAULT_REPUTATION_PARAMS) -> float:
    """Q_max = Q_base * (0.2 + 0.8 * R)."""
    r = min(1.0, max(0.0, r))
    return q_base_kwh * (params.cap_floor + (1.0 - params.cap_floor) * r)


def matching_reputation(
    state: BetaState,
    tier: Tier,
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
) -> float:
    """Reputation value to put on ``engine.pricing.Position.reputation``.

    Suspended -> 0 (excluded by the rho_min gate). Probation -> max(R, rho_min) so it can trade,
    with its quantity capped by ``volume_cap_kwh``. Otherwise the true R.
    """
    r = reputation(state, params)
    if tier is Tier.SUSPENDED:
        return 0.0
    if tier is Tier.PROBATION:
        return max(r, params.rho_min)
    return r


def intervals_to_tier(
    state: BetaState,
    target: Tier = Tier.TRUSTED,
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
    *,
    phi: float | None = None,
    max_intervals: int = 10_000,
) -> int | None:
    """Perfect full-volume intervals needed to reach ``target`` (what-if panel / E7).

    Returns None if the target is not reached within ``max_intervals``.
    """
    perfect = Evidence(volume_kwh=params.v_ref_kwh)
    current = state
    for i in range(max_intervals + 1):
        if _RANK[classify(current, params)] >= _RANK[target]:
            return i
        current = update(current, perfect, params, phi=phi)
    return None
