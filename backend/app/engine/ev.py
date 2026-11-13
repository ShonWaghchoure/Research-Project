"""EV limit-price and V2G quantity helpers (pure)."""

from __future__ import annotations


def clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def ev_urgency(e_need_kwh: float, p_max_kw: float, t_left_h: float) -> float:
    """Urgency u ∈ [0, 1] = clip(E_need / (P_max * T_left), 0, 1)."""
    if p_max_kw <= 0 or t_left_h <= 0:
        return 1.0 if e_need_kwh > 0 else 0.0
    return clip(e_need_kwh / (p_max_kw * t_left_h), 0.0, 1.0)


def ev_buy_limit_price(
    p_fit: float,
    p_ret: float,
    e_need_kwh: float,
    p_max_kw: float,
    t_left_h: float,
) -> float:
    """b_i = p_fit + (p_ret - p_fit) * u_i."""
    u = ev_urgency(e_need_kwh, p_max_kw, t_left_h)
    return float(p_fit) + float(p_ret - p_fit) * u


def ev_v2g_sell_qty(soc_kwh: float, e_target_kwh: float, v2g: bool) -> float:
    """q_sell = max(0, SOC - E_target) only if v2g is True; else 0."""
    if not v2g:
        return 0.0
    return max(0.0, soc_kwh - e_target_kwh)
