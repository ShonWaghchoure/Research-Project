"""Fairness and market-outcome metrics (pure functions).

Spec metrics (GEMINI.md Phase 3):
    jain_index           J = (sum f)^2 / (n * sum f^2), f_k = matched share of k's offer/demand
    gini                 of per-participant welfare gain vs. grid-only trading
    hhi                  sum s_j^2, s_j = seller j's share of matched volume
    small_actor_parity   matched share of smallest 50% / their offered share
    price_impact         max |change in p_raw| any one participant causes by doubling its qty
    reputation_mobility  1 - Spearman rank correlation of scores between two snapshots
    reputation_gini      gini of reputation scores
    welfare_efficiency   matched welfare / unconstrained optimal welfare

Report metrics (project report sections 4.3 / 4.4, edge cases doc):
    seller_satisfaction_index, buyer bill saving %, seller revenue uplift %, surplus split,
    matching_rate (market resilience), grid_trust_density, grid_backup_frequency.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Sequence

from app.core.params import DEFAULT_PARAMS, MarketParams
from app.engine.pricing import Position
from app.engine.pricing import price_impact as _price_impact
from app.reputation.tiers import Tier


def _r(x: float) -> float:
    return round(float(x), 6)


# ─── Distribution metrics ──────────────────────────────────────────────────────


def jain_index(values: Sequence[float]) -> float:
    """1 = perfectly even, 1/n = one participant gets everything. Empty or all-zero -> 1."""
    if not values:
        return 1.0
    s = sum(values)
    sq = sum(v * v for v in values)
    if sq <= 0:
        return 1.0
    return _r(s * s / (len(values) * sq))


def matched_shares(offered_wh: Mapping[str, int], matched_wh: Mapping[str, int]) -> Dict[str, float]:
    """f_k = matched / offered for every participant with a non-zero offer or demand."""
    return {
        pid: min(1.0, matched_wh.get(pid, 0) / q) for pid, q in sorted(offered_wh.items()) if q > 0
    }


def gini(values: Sequence[float]) -> float:
    """Gini coefficient in [0, 1). Negative values are clipped to 0 (see DECISIONS.md)."""
    xs = sorted(max(0.0, float(v)) for v in values)
    n = len(xs)
    total = sum(xs)
    if n == 0 or total <= 0:
        return 0.0
    # G = (2 * sum_i i*x_i) / (n * sum x) - (n + 1) / n, with i = 1..n on sorted values
    weighted = sum((i + 1) * x for i, x in enumerate(xs))
    return _r(2.0 * weighted / (n * total) - (n + 1.0) / n)


def hhi(seller_volume_wh: Mapping[str, float]) -> float:
    total = sum(v for v in seller_volume_wh.values() if v > 0)
    if total <= 0:
        return 0.0
    return _r(sum((v / total) ** 2 for v in seller_volume_wh.values() if v > 0))


def small_actor_parity(offered_wh: Mapping[str, int], matched_wh: Mapping[str, int]) -> float:
    """(matched share of the smallest 50% by offered volume) / (their offered share).

    1 = small participants get their proportional share; < 1 = they are under-served.
    No matched volume -> 1.0 (nothing to compare).
    """
    items = sorted(((q, pid) for pid, q in offered_wh.items() if q > 0))
    if len(items) < 2:
        return 1.0
    small = [pid for _, pid in items[: len(items) // 2]]
    total_off = sum(q for q, _ in items)
    total_match = sum(matched_wh.get(pid, 0) for _, pid in items)
    if total_off <= 0 or total_match <= 0:
        return 1.0
    off_share = sum(offered_wh[p] for p in small) / total_off
    match_share = sum(matched_wh.get(p, 0) for p in small) / total_match
    return _r(match_share / off_share) if off_share > 0 else 1.0


# ─── Price impact ──────────────────────────────────────────────────────────────


def price_impact(positions: Sequence[Position], params: MarketParams = DEFAULT_PARAMS) -> Dict[str, float]:
    """Per participant: |change in p_raw| from doubling its own quantity, as a fraction of
    the corridor (p_ret - p_fit). Uses ``engine.pricing.price_impact``."""
    corridor = float(params.p_ret - params.p_fit)
    out: Dict[str, float] = {}
    for p in positions:
        if p.qty_kwh <= 0:
            continue
        d = _price_impact(positions, p.participant_id, p.qty_kwh, params)
        out[p.participant_id] = _r(abs(d) / corridor) if corridor > 0 else 0.0
    return out


def max_price_impact(positions: Sequence[Position], params: MarketParams = DEFAULT_PARAMS) -> float:
    impacts = price_impact(positions, params)
    return max(impacts.values()) if impacts else 0.0


# ─── Reputation distribution ───────────────────────────────────────────────────


def _ranks(xs: Sequence[float]) -> List[float]:
    """Average ranks (ties share the mean rank)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def _pearson(a: Sequence[float], b: Sequence[float]) -> float | None:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return None
    return cov / (va * vb) ** 0.5


def reputation_mobility(start: Mapping[str, float], end: Mapping[str, float]) -> float:
    """1 - Spearman(start, end) over participants present in both, in [0, 2].

    0 = ranking frozen (permanent elite); 1 = no relation; 2 = fully reversed.
    Fewer than 2 participants, or a constant snapshot (e.g. launch day), -> 0.0.
    """
    ids = sorted(set(start) & set(end))
    if len(ids) < 2:
        return 0.0
    rho = _pearson(_ranks([start[i] for i in ids]), _ranks([end[i] for i in ids]))
    return 0.0 if rho is None else _r(1.0 - rho)


def reputation_gini(scores: Mapping[str, float]) -> float:
    return gini(list(scores.values()))


def grid_trust_density(tiers: Mapping[str, Tier]) -> float:
    """Share of participants in the Trusted tier (report metric 'grid trust density')."""
    if not tiers:
        return 0.0
    return _r(sum(1 for t in tiers.values() if t is Tier.TRUSTED) / len(tiers))


# ─── Welfare and market economics ──────────────────────────────────────────────


@dataclass(frozen=True)
class TradeView:
    buyer_id: str
    seller_id: str
    qty_wh: int


def trade_welfare(trades: Iterable[TradeView], positions: Sequence[Position]) -> float:
    """Sum over trades of (b_i - a_j) * kWh, in price units * kWh."""
    limit = {p.participant_id: p.limit_price for p in positions}
    return sum((limit[t.buyer_id] - limit[t.seller_id]) * t.qty_wh / 1000.0 for t in trades)


def welfare_efficiency(matched_welfare: float, optimal_welfare: float) -> float:
    """matched / unconstrained optimal. Optimal <= 0 (nothing to gain) -> 1.0."""
    if optimal_welfare <= 0:
        return 1.0
    return _r(max(0.0, matched_welfare) / optimal_welfare)


def welfare_gains(
    trades: Iterable[TradeView],
    p_ref: float,
    params: MarketParams = DEFAULT_PARAMS,
    participants: Iterable[str] = (),
) -> Dict[str, float]:
    """Per-participant gain vs. grid-only trading (price units * kWh).

    Buyer saves (p_ret - p_ref) per kWh bought P2P; seller earns (p_ref - p_fit) per kWh sold.
    Participants listed in ``participants`` with no trade get 0 (so Gini counts them).
    """
    gains: Dict[str, float] = {pid: 0.0 for pid in participants}
    for t in trades:
        kwh = t.qty_wh / 1000.0
        gains[t.buyer_id] = gains.get(t.buyer_id, 0.0) + kwh * (params.p_ret - p_ref)
        gains[t.seller_id] = gains.get(t.seller_id, 0.0) + kwh * (p_ref - params.p_fit)
    return gains


@dataclass(frozen=True)
class MarketEconomics:
    buyer_bill_p2p: float
    buyer_bill_grid_only: float
    buyer_saving_pct: float
    seller_revenue_p2p: float
    seller_revenue_grid_only: float
    seller_uplift_pct: float
    buyer_surplus: float
    seller_surplus: float
    buyer_surplus_share: float  # buyer / (buyer + seller); 0.5 = gains split evenly


def market_economics(
    trades: Iterable[TradeView],
    unmatched_buy_wh: Mapping[str, int],
    unmatched_sell_wh: Mapping[str, int],
    p_ref: float,
    params: MarketParams = DEFAULT_PARAMS,
) -> MarketEconomics:
    """Bills and revenues vs. the grid-only baseline (Nazir et al. comparison, report 4.4).

    Amounts are in price units (paise in production) and are not rounded to integers here:
    these are evaluation metrics, not settlement amounts.
    """
    matched_kwh = sum(t.qty_wh for t in trades) / 1000.0
    unb = sum(unmatched_buy_wh.values()) / 1000.0
    uns = sum(unmatched_sell_wh.values()) / 1000.0
    p_ret, p_fit = float(params.p_ret), float(params.p_fit)

    bill_p2p = matched_kwh * p_ref + unb * p_ret
    bill_grid = (matched_kwh + unb) * p_ret
    rev_p2p = matched_kwh * p_ref + uns * p_fit
    rev_grid = (matched_kwh + uns) * p_fit
    bs = matched_kwh * (p_ret - p_ref)
    ss = matched_kwh * (p_ref - p_fit)
    return MarketEconomics(
        buyer_bill_p2p=_r(bill_p2p),
        buyer_bill_grid_only=_r(bill_grid),
        buyer_saving_pct=_r(100.0 * (1 - bill_p2p / bill_grid)) if bill_grid > 0 else 0.0,
        seller_revenue_p2p=_r(rev_p2p),
        seller_revenue_grid_only=_r(rev_grid),
        seller_uplift_pct=_r(100.0 * (rev_p2p / rev_grid - 1)) if rev_grid > 0 else 0.0,
        buyer_surplus=_r(bs),
        seller_surplus=_r(ss),
        buyer_surplus_share=_r(bs / (bs + ss)) if bs + ss > 0 else 0.5,
    )


def seller_satisfaction_index(offered_sell_wh: Mapping[str, int], matched_sell_wh: Mapping[str, int]) -> float:
    """Share of sellers with an offer that sold at least 1 Wh P2P (Nazir et al. [1])."""
    sellers = [pid for pid, q in offered_sell_wh.items() if q > 0]
    if not sellers:
        return 1.0
    return _r(sum(1 for pid in sellers if matched_sell_wh.get(pid, 0) > 0) / len(sellers))


def matching_rate(total_buy_wh: int, total_sell_wh: int, matched_wh: int) -> float:
    """Market resilience: matched volume / maximum matchable volume min(supply, demand)."""
    cap = min(total_buy_wh, total_sell_wh)
    if cap <= 0:
        return 1.0
    return _r(min(1.0, matched_wh / cap))


def grid_backup_frequency(
    history: Sequence[tuple[Mapping[str, int], Mapping[str, int]]],
) -> Dict[str, float]:
    """Per participant: fraction of its active intervals that were served 100% by the grid.

    ``history`` is one (offered_wh, matched_wh) pair per interval. Edge case 14: a participant
    can look fine in every single interval yet always end up on grid fallback.
    """
    active: Dict[str, int] = {}
    fallback: Dict[str, int] = {}
    for offered, matched in history:
        for pid, q in offered.items():
            if q <= 0:
                continue
            active[pid] = active.get(pid, 0) + 1
            if matched.get(pid, 0) <= 0:
                fallback[pid] = fallback.get(pid, 0) + 1
    return {pid: _r(fallback.get(pid, 0) / n) for pid, n in sorted(active.items())}
