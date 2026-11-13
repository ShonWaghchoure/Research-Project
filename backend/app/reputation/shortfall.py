"""Shortfall settlement amounts (pure functions, integer paise out).

For shortfall e = promised - delivered (Wh), at clearing price p_ref (paise/kWh):
    compensation to buyer = e * (p_ret - p_ref)      (buyer covers the gap from the grid at retail)
    penalty fee           = f * e * p_ref,  f = 0.1
    payment for delivered = delivered * p_ref         (pro-rated settlement, edge cases 6 / 16)

Energy is Wh and prices are paise per kWh, so every amount is divided by 1000 and rounded down,
matching the contract rule ``payment = qtyWh * pricePaise / 1000`` (GEMINI.md Phase 5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.core.params import DEFAULT_PARAMS, MarketParams


@dataclass(frozen=True)
class ShortfallResult:
    shortfall_wh: int
    delivered_wh: int
    payment_paise: int  # buyer -> seller for energy actually delivered
    compensation_paise: int  # seller stake -> buyer
    penalty_paise: int  # seller stake -> operator / treasury


def _floor_paise(wh: int, paise_per_kwh: float) -> int:
    return max(0, math.floor(wh * paise_per_kwh / 1000.0 + 1e-9))


def settle_shortfall(
    promised_wh: int,
    delivered_wh: int,
    p_ref_paise: float,
    params: MarketParams = DEFAULT_PARAMS,
) -> ShortfallResult:
    if promised_wh < 0 or delivered_wh < 0:
        raise ValueError("promised_wh and delivered_wh must be non-negative")
    delivered = min(delivered_wh, promised_wh)  # over-delivery is not paid as a P2P trade
    e = promised_wh - delivered
    spread = max(0.0, float(params.p_ret) - float(p_ref_paise))
    return ShortfallResult(
        shortfall_wh=e,
        delivered_wh=delivered,
        payment_paise=_floor_paise(delivered, p_ref_paise),
        compensation_paise=_floor_paise(e, spread),
        penalty_paise=_floor_paise(e, params.shortfall_penalty_f * float(p_ref_paise)),
    )
