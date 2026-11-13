"""Beta reputation with forgetting and a lower confidence bound (pure functions).

Model (GEMINI.md Phase 3; Beta Reputation System, Josang & Ismail 2002, with forgetting):

    s_t   = w_del*r_del + w_rev*r_rev + w_hon*r_hon + w_col*(1 - c_i)
    n_t   = min(1, v_t / v_ref)                        (evidence weight from traded kWh)
    alpha = phi*alpha + n_t*s_t
    beta  = phi*beta  + kappa*n_t*(1 - s_t)            (failures weigh kappa = 3x more)
    mu    = alpha / (alpha + beta)
    sigma = sqrt(alpha*beta / ((alpha+beta)^2 * (alpha+beta+1)))
    R     = max(0, mu - z*sigma)                       (lower confidence bound, z = 1)

phi = 0.5 ** (1/H), H = 672 intervals (7 days of 15-minute intervals).
No I/O, no clock, no randomness.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.reputation.params import DEFAULT_REPUTATION_PARAMS, ReputationParams


@dataclass(frozen=True)
class BetaState:
    alpha: float
    beta: float
    evidence_count: int = 0  # intervals that contributed evidence (n_t > 0)


@dataclass(frozen=True)
class Evidence:
    """One interval of behavioural evidence for one participant.

    r_del:      min(1, delivered / promised); use ``delivery_ratio``.
    r_rev:      1.0 if the committed position was revealed, else 0.0.
    anomaly:    a_i in [0, 1] from detection (IsolationForest / false-report checks).
    collusion:  c_i in [0, 1] from the collusion detector.
    volume_kwh: energy traded this interval (drives the evidence weight).
    weight_override: force n_t (used for reveal misses, where nothing was traded).
    """

    r_del: float = 1.0
    r_rev: float = 1.0
    anomaly: float = 0.0
    collusion: float = 0.0
    volume_kwh: float = 0.0
    weight_override: float | None = None


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def delivery_ratio(promised_wh: int, delivered_wh: int) -> float:
    """r_del = min(1, delivered / promised). Nothing promised -> 1.0 (no failure)."""
    if promised_wh <= 0:
        return 1.0
    return _clip01(max(0, delivered_wh) / promised_wh)


def reveal_miss_evidence(anomaly: float = 0.0, collusion: float = 0.0) -> Evidence:
    """Evidence for a participant that committed but never revealed.

    A miss trades nothing, so v_t = 0 would otherwise add no evidence and make
    non-revealing free. We count it at full weight with r_rev = 0 and r_del = 0
    (the commitment was not honoured). See docs/DECISIONS.md.
    """
    return Evidence(
        r_del=0.0,
        r_rev=0.0,
        anomaly=anomaly,
        collusion=collusion,
        volume_kwh=0.0,
        weight_override=1.0,
    )


def initial_state(params: ReputationParams = DEFAULT_REPUTATION_PARAMS) -> BetaState:
    return BetaState(alpha=params.alpha0, beta=params.beta0, evidence_count=0)


def evidence_score(ev: Evidence, params: ReputationParams = DEFAULT_REPUTATION_PARAMS) -> float:
    """s_t in [0, 1]. r_hon = 1 - anomaly."""
    r_hon = 1.0 - _clip01(ev.anomaly)
    s = (
        params.w_del * _clip01(ev.r_del)
        + params.w_rev * _clip01(ev.r_rev)
        + params.w_hon * r_hon
        + params.w_col * (1.0 - _clip01(ev.collusion))
    )
    return _clip01(s)


def evidence_weight(ev: Evidence, params: ReputationParams = DEFAULT_REPUTATION_PARAMS) -> float:
    """n_t = min(1, v_t / v_ref)."""
    if ev.weight_override is not None:
        return _clip01(ev.weight_override)
    if ev.volume_kwh <= 0 or params.v_ref_kwh <= 0:
        return 0.0
    return min(1.0, ev.volume_kwh / params.v_ref_kwh)


def _decay(value: float, prior: float, phi: float, to_prior: bool) -> float:
    if to_prior:
        return prior + phi * (value - prior)
    return phi * value


def update(
    state: BetaState,
    ev: Evidence | None,
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
    *,
    phi: float | None = None,
) -> BetaState:
    """Advance one interval. ``ev=None`` means the participant was idle (decay only)."""
    f = params.phi if phi is None else phi
    alpha = _decay(state.alpha, params.alpha0, f, params.decay_to_prior)
    beta = _decay(state.beta, params.beta0, f, params.decay_to_prior)
    count = state.evidence_count
    if ev is not None:
        n = evidence_weight(ev, params)
        if n > 0:
            s = evidence_score(ev, params)
            alpha += n * s
            beta += params.kappa * n * (1.0 - s)
            count += 1
    return BetaState(alpha=alpha, beta=beta, evidence_count=count)


def mean(state: BetaState) -> float:
    total = state.alpha + state.beta
    if total <= 0:
        return 0.0
    return state.alpha / total


def std(state: BetaState) -> float:
    a, b = state.alpha, state.beta
    total = a + b
    if total <= 0:
        return 0.0
    return math.sqrt(a * b / (total * total * (total + 1.0)))


def reputation(state: BetaState, params: ReputationParams = DEFAULT_REPUTATION_PARAMS) -> float:
    """R = max(0, mu - z*sigma), rounded to 6 dp so it is stable across machines."""
    r = max(0.0, mean(state) - params.z * std(state))
    return round(min(1.0, r), 6)


def score_bp(r: float) -> int:
    """Reputation as uint16 basis points (0..10000) for ReputationAnchor leaves."""
    return int(round(_clip01(r) * 10000))


def score_display(r: float) -> int:
    """Reputation on the 0..100 scale used in the project report."""
    return int(round(_clip01(r) * 100))


def run_history(
    evidence: list[Evidence | None],
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
    *,
    start: BetaState | None = None,
    phi: float | None = None,
) -> list[BetaState]:
    """Apply a sequence of intervals; returns the state after each one."""
    state = start if start is not None else initial_state(params)
    out: list[BetaState] = []
    for ev in evidence:
        state = update(state, ev, params, phi=phi)
        out.append(state)
    return out
