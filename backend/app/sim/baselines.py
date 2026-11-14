"""Market-clearing baselines for comparison with the full system (pure, seeded).

    B0  grid only: no P2P trades; buyers pay p_ret, sellers export at p_fit.
    B1  fixed mid price (p_fit + p_ret)/2, first-come greedy matching, no reputation, no grid limits.
    B2  SDR pricing (Phase 1, reputation weights off) with proportional allocation of the long side
        (Nazir et al. 2025 style), no reputation, no grid limits.
    B3  the full system: ``engine.clearing.clear_interval`` with reputation-gated, grid-aware QP.

Every baseline returns ``engine.clearing.ClearingResult`` so the runner treats them uniformly;
line loadings are computed for all of them so grid violations of B1/B2 are visible.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Dict, List, Sequence

import numpy as np

from app.core.params import MarketParams
from app.engine.clearing import (
    ClearedTrade,
    ClearingResult,
    _recompute_line_loadings,
    clear_interval,
)
from app.engine.grid import Feeder
from app.engine.hashing import input_root, result_hash
from app.engine.pricing import Position, compute_reference_price

MODES = ("B0", "B1", "B2", "B3")


def _wh(q_kwh: float) -> int:
    return max(0, int(q_kwh * 1000.0 + 1e-9))


def _result(
    trades: List[ClearedTrade],
    positions: Sequence[Position],
    p_ref: float,
    p_raw: float,
    sdr: float,
    feeder: Feeder,
    params: MarketParams,
    status: str,
) -> ClearingResult:
    mb: Dict[str, int] = {}
    ms: Dict[str, int] = {}
    for t in trades:
        mb[t.buyer_id] = mb.get(t.buyer_id, 0) + t.qty_wh
        ms[t.seller_id] = ms.get(t.seller_id, 0) + t.qty_wh
    return ClearingResult(
        trades=tuple(trades),
        p_ref=p_ref,
        p_raw=p_raw,
        sdr=sdr,
        unmatched_buy_wh={p.participant_id: _wh(p.qty_kwh) - mb.get(p.participant_id, 0) for p in positions if p.side == "buy"},
        unmatched_sell_wh={p.participant_id: _wh(p.qty_kwh) - ms.get(p.participant_id, 0) for p in positions if p.side == "sell"},
        line_loading_kw=_recompute_line_loadings(trades, positions, feeder, params),
        input_root=input_root(positions),
        result_hash=result_hash(trades, p_ref),
        match_status=status,
    )


def _sdr(positions: Sequence[Position]) -> float:
    s = sum(p.qty_kwh for p in positions if p.side == "sell")
    d = sum(p.qty_kwh for p in positions if p.side == "buy")
    return s / d if d > 0 else (float("inf") if s > 0 else 1.0)


def clear_b0(positions: Sequence[Position], feeder: Feeder, params: MarketParams) -> ClearingResult:
    return _result([], positions, float(params.p_ret), float(params.p_ret), _sdr(positions), feeder, params, "grid_only")


def clear_b1(
    positions: Sequence[Position], feeder: Feeder, params: MarketParams, rng: np.random.Generator
) -> ClearingResult:
    price = (params.p_fit + params.p_ret) / 2.0
    order = list(range(len(positions)))
    rng.shuffle(order)  # arrival order
    buyers = [positions[i] for i in order if positions[i].side == "buy" and positions[i].limit_price >= price]
    sellers = [positions[i] for i in order if positions[i].side == "sell" and positions[i].limit_price <= price]
    left_s = [_wh(s.qty_kwh) for s in sellers]
    trades: List[ClearedTrade] = []
    j = 0
    for b in buyers:
        need = _wh(b.qty_kwh)
        while need > 0 and j < len(sellers):
            q = min(need, left_s[j])
            if q > 0:
                trades.append(ClearedTrade(b.participant_id, sellers[j].participant_id, q, price))
                need -= q
                left_s[j] -= q
            if left_s[j] == 0:
                j += 1
    return _result(trades, positions, price, price, _sdr(positions), feeder, params, "first_come")


def clear_b2(
    positions: Sequence[Position], feeder: Feeder, params: MarketParams, prev_p_ref: float | None
) -> ClearingResult:
    neutral = [replace(p, reputation=1.0) for p in positions]
    pr = compute_reference_price(neutral, prev_p_ref, params)
    p = pr.p_ref
    buyers = [x for x in positions if x.side == "buy" and x.limit_price >= p and x.qty_kwh > 0]
    sellers = [x for x in positions if x.side == "sell" and x.limit_price <= p and x.qty_kwh > 0]
    d = sum(_wh(b.qty_kwh) for b in buyers)
    s = sum(_wh(x.qty_kwh) for x in sellers)
    matched = min(d, s)
    trades: List[ClearedTrade] = []
    if matched > 0:
        # Proportional: each buyer gets matched * q_i / D, each seller matched * q_j / S;
        # pair volumes are the product split x_ij = alloc_i * alloc_j / matched (floored).
        alloc_b = {b.participant_id: matched * _wh(b.qty_kwh) / d for b in buyers}
        alloc_s = {x.participant_id: matched * _wh(x.qty_kwh) / s for x in sellers}
        for b in buyers:
            for x in sellers:
                q = int(alloc_b[b.participant_id] * alloc_s[x.participant_id] / matched)
                if q > 0:
                    trades.append(ClearedTrade(b.participant_id, x.participant_id, q, p))
    return _result(trades, positions, p, pr.p_raw, pr.sdr, feeder, params, "proportional")


def clear(
    mode: str,
    positions: Sequence[Position],
    feeder: Feeder,
    params: MarketParams,
    prev_p_ref: float | None,
    rng: np.random.Generator,
    *,
    apply_median_cap: bool = True,
) -> ClearingResult:
    if mode == "B0":
        return clear_b0(positions, feeder, params)
    if mode == "B1":
        return clear_b1(positions, feeder, params, rng)
    if mode == "B2":
        return clear_b2(positions, feeder, params, prev_p_ref)
    if mode == "B3":
        return clear_interval(
            positions, feeder, params, prev_p_ref, apply_median_cap=apply_median_cap
        )
    raise ValueError(f"unknown mode {mode!r}; expected one of {MODES}")
