"""Global parameters for the Fair and Trustworthy P2P Energy Trading Simulator."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketParams:
    # Prices in paise per kWh (INR 3 = 300 paise, INR 8 = 800 paise)
    p_fit: int = 300
    p_ret: int = 800

    # Interval durations in seconds
    interval_seconds: int = 900
    demo_interval_seconds: int = 45

    # SDR and matching parameters
    k: int = 2
    alpha: float = 0.7
    c: int = 3
    r_ref: float = 0.8
    rho_min: float = 0.3
    r_cap: float = 0.9
    beta: float = 25.0  # <= 5% of (p_ret - p_fit) = 25.0 paise
    match_lambda: float = 1.0  # proportional-share soft penalty weight
    dt_hours: float = 0.25  # interval length for kWh→kW conversion
    q_base_kwh: float = 2.0  # reputation volume-cap base per interval

    # Reputation scoring weights: (w_del, w_rev, w_hon, w_col)
    w_del: float = 0.45
    w_rev: float = 0.15
    w_hon: float = 0.20
    w_col: float = 0.20

    # Beta prior and decay parameters
    alpha0: float = 1.0
    beta0: float = 2.0
    kappa: float = 3.0
    z: float = 1.0
    half_life_intervals: int = 672  # H

    # Defenses & penalties
    shortfall_penalty_f: float = 0.1
    collusion_window_intervals: int = 96


DEFAULT_PARAMS = MarketParams()
