"""Reputation-layer parameters (Phase 3).

Global values (weights, Beta prior, kappa, z, half-life, rho_min, shortfall f) come from
``app.core.params.MarketParams`` so there is one source of truth. The extra thresholds below
are Phase 3 specifics; see docs/DECISIONS.md (Phase 3) for the reasoning behind each default.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.params import DEFAULT_PARAMS, MarketParams


@dataclass(frozen=True)
class ReputationParams:
    # Evidence weights (w_del, w_rev, w_hon, w_col)
    w_del: float = 0.45
    w_rev: float = 0.15
    w_hon: float = 0.20
    w_col: float = 0.20

    # Beta prior and update
    alpha0: float = 1.0
    beta0: float = 2.0
    kappa: float = 3.0
    z: float = 1.0
    half_life_intervals: int = 672  # H; phi = 0.5 ** (1 / H)
    decay_to_prior: bool = False  # spec: decay pseudo-counts toward 0 (see DECISIONS.md)

    # Evidence weight n_t = min(1, v_t / v_ref)
    v_ref_kwh: float = 1.0

    # Tier thresholds
    suspended_below: float = 0.15
    probation_below: float = 0.30  # equals rho_min
    trusted_at: float = 0.80
    newcomer_evidence: int = 20  # evidence_count < 20 -> Probation
    trusted_evidence: int = 100  # Trusted needs evidence_count >= 100
    hysteresis: float = 0.02  # downgrade only when R < threshold - hysteresis

    # Volume cap Q_max = Q_base * (cap_floor + (1 - cap_floor) * R)
    cap_floor: float = 0.2

    # Matching gate (from Phase 2 engine)
    rho_min: float = 0.30

    # Shortfall
    shortfall_penalty_f: float = 0.1

    # Collusion / detection
    collusion_window_intervals: int = 96
    collusion_flag_at: float = 0.5
    collusion_high_at: float = 0.9
    community_internal_ratio: float = 0.8
    community_max_fraction: float = 0.5  # ignore communities covering > 50% of the market
    pv_tolerance: float = 1.1
    balance_tolerance: float = 0.05  # 5% of substation reading

    @staticmethod
    def from_market(mp: MarketParams = DEFAULT_PARAMS) -> "ReputationParams":
        return ReputationParams(
            w_del=mp.w_del,
            w_rev=mp.w_rev,
            w_hon=mp.w_hon,
            w_col=mp.w_col,
            alpha0=mp.alpha0,
            beta0=mp.beta0,
            kappa=mp.kappa,
            z=mp.z,
            half_life_intervals=mp.half_life_intervals,
            rho_min=mp.rho_min,
            probation_below=mp.rho_min,
            shortfall_penalty_f=mp.shortfall_penalty_f,
            collusion_window_intervals=mp.collusion_window_intervals,
        )

    @property
    def phi(self) -> float:
        if self.half_life_intervals <= 0:
            return 1.0
        return float(0.5 ** (1.0 / self.half_life_intervals))


DEFAULT_REPUTATION_PARAMS = ReputationParams.from_market()
