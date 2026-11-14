"""Interval clearing pipeline: pricing → matching → Wh integerization (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from app.core.params import MarketParams
from app.engine.grid import Feeder, build_pi_matrix, incidence_root_to_node
from app.engine.hashing import input_root, result_hash
from app.engine.matching import MatchTrade, match_orders
from app.engine.pricing import Position, compute_reference_price


@dataclass(frozen=True)
class ClearedTrade:
    buyer_id: str
    seller_id: str
    qty_wh: int
    price: float


@dataclass(frozen=True)
class ClearingResult:
    trades: Tuple[ClearedTrade, ...]
    p_ref: float
    p_raw: float
    sdr: float
    unmatched_buy_wh: Dict[str, int]
    unmatched_sell_wh: Dict[str, int]
    line_loading_kw: Dict[str, float]
    input_root: str
    result_hash: str
    match_status: str


def _kwh_to_wh_floor(qty_kwh: float) -> int:
    return max(0, int(qty_kwh * 1000.0))


def _wh_to_kwh(qty_wh: int) -> float:
    return qty_wh / 1000.0


def _recompute_line_loadings(
    trades: Sequence[ClearedTrade],
    positions: Sequence[Position],
    feeder: Feeder,
    params: MarketParams,
) -> Dict[str, float]:
    buyers = [p for p in positions if p.side == "buy"]
    sellers = [p for p in positions if p.side == "sell"]
    buyer_nodes = {p.participant_id: p.node_id for p in buyers}
    seller_nodes = {p.participant_id: p.node_id for p in sellers}
    pi = build_pi_matrix(
        feeder,
        [p.participant_id for p in buyers],
        [p.participant_id for p in sellers],
        buyer_nodes,
        seller_nodes,
    )
    root_inc = {
        n: incidence_root_to_node(feeder, n)
        for n in {*buyer_nodes.values(), *seller_nodes.values(), feeder.root}
    }

    matched_b = {p.participant_id: 0.0 for p in buyers}
    matched_s = {p.participant_id: 0.0 for p in sellers}
    for t in trades:
        kwh = _wh_to_kwh(t.qty_wh)
        matched_b[t.buyer_id] = matched_b.get(t.buyer_id, 0.0) + kwh
        matched_s[t.seller_id] = matched_s.get(t.seller_id, 0.0) + kwh

    dt = params.dt_hours
    loadings: Dict[str, float] = {line.id: 0.0 for line in feeder.lines}
    for line in feeder.lines:
        flow = 0.0
        for t in trades:
            coeff = pi[line.id].get((t.buyer_id, t.seller_id), 0)
            if coeff:
                flow += coeff * _wh_to_kwh(t.qty_wh)
        for b in buyers:
            residual = max(0.0, b.qty_kwh - matched_b.get(b.participant_id, 0.0))
            eta = root_inc[b.node_id].get(line.id, 0)
            if eta:
                flow += eta * residual
        for s in sellers:
            residual = max(0.0, s.qty_kwh - matched_s.get(s.participant_id, 0.0))
            eta = root_inc[s.node_id].get(line.id, 0)
            if eta:
                flow += (-eta) * residual
        loadings[line.id] = flow / dt
    return loadings


def _trades_from_qty(
    floors: Sequence[tuple[MatchTrade, int, float]],
    qty: Sequence[int],
    p_ref: float,
) -> List[ClearedTrade]:
    cleared: List[ClearedTrade] = []
    for i, (t, _, _) in enumerate(floors):
        if qty[i] > 0:
            cleared.append(
                ClearedTrade(
                    buyer_id=t.buyer_id,
                    seller_id=t.seller_id,
                    qty_wh=qty[i],
                    price=p_ref,
                )
            )
    return cleared


def _line_caps_ok(
    trades: Sequence[ClearedTrade],
    positions: Sequence[Position],
    feeder: Feeder,
    params: MarketParams,
) -> bool:
    loadings = _recompute_line_loadings(trades, positions, feeder, params)
    for line in feeder.lines:
        if abs(loadings.get(line.id, 0.0)) > line.capacity_kw + 1e-6:
            return False
    return True


def _largest_remainder_repair(
    float_trades: Sequence[MatchTrade],
    positions: Sequence[Position],
    p_ref: float,
    feeder: Feeder,
    params: MarketParams,
) -> List[ClearedTrade]:
    """Round each trade down to Wh, then allocate remainders without violating caps.

    Remainders are awarded largest-fraction first only when quantity caps and
    feeder line capacities both stay satisfied.
    """
    buyers = {p.participant_id: p for p in positions if p.side == "buy"}
    sellers = {p.participant_id: p for p in positions if p.side == "sell"}

    buyer_cap = {pid: _kwh_to_wh_floor(p.qty_kwh) for pid, p in buyers.items()}
    seller_cap = {pid: _kwh_to_wh_floor(p.qty_kwh) for pid, p in sellers.items()}

    floors: List[tuple[MatchTrade, int, float]] = []
    for t in float_trades:
        wh_exact = t.qty_kwh * 1000.0
        floor = int(wh_exact)
        frac = wh_exact - floor
        floors.append((t, floor, frac))

    buyer_used = {pid: 0 for pid in buyer_cap}
    seller_used = {pid: 0 for pid in seller_cap}
    qty = [f for _, f, _ in floors]
    for i, (t, floor, _) in enumerate(floors):
        buyer_used[t.buyer_id] = buyer_used.get(t.buyer_id, 0) + floor
        seller_used[t.seller_id] = seller_used.get(t.seller_id, 0) + floor
        qty[i] = floor

    # Award remainders by largest fractional part while quantity caps allow.
    awarded: List[int] = []
    order = sorted(range(len(floors)), key=lambda i: floors[i][2], reverse=True)
    for i in order:
        t = floors[i][0]
        if floors[i][2] <= 0:
            continue
        if buyer_used[t.buyer_id] >= buyer_cap.get(t.buyer_id, 0):
            continue
        if seller_used[t.seller_id] >= seller_cap.get(t.seller_id, 0):
            continue
        qty[i] += 1
        buyer_used[t.buyer_id] += 1
        seller_used[t.seller_id] += 1
        awarded.append(i)

    # If line capacities are violated, strip remainders in reverse award order.
    candidate = _trades_from_qty(floors, qty, p_ref)
    if not _line_caps_ok(candidate, positions, feeder, params):
        for i in reversed(awarded):
            t = floors[i][0]
            qty[i] -= 1
            buyer_used[t.buyer_id] -= 1
            seller_used[t.seller_id] -= 1
            candidate = _trades_from_qty(floors, qty, p_ref)
            if _line_caps_ok(candidate, positions, feeder, params):
                break

    return _trades_from_qty(floors, qty, p_ref)


def clear_interval(
    positions: Sequence[Position],
    feeder: Feeder,
    params: MarketParams,
    prev_p_ref: float | None,
    *,
    apply_median_cap: bool = True,
) -> ClearingResult:
    """Price → match → integerize → hash."""
    price = compute_reference_price(
        positions, prev_p_ref, params, apply_median_cap=apply_median_cap
    )
    matched = match_orders(positions, feeder, price.p_ref, price.sdr, params)
    cleared = _largest_remainder_repair(
        matched.trades, positions, price.p_ref, feeder, params
    )

    buyers = {p.participant_id: p for p in positions if p.side == "buy"}
    sellers = {p.participant_id: p for p in positions if p.side == "sell"}
    matched_b = {pid: 0 for pid in buyers}
    matched_s = {pid: 0 for pid in sellers}
    for t in cleared:
        matched_b[t.buyer_id] = matched_b.get(t.buyer_id, 0) + t.qty_wh
        matched_s[t.seller_id] = matched_s.get(t.seller_id, 0) + t.qty_wh

    unmatched_buy = {
        pid: max(0, _kwh_to_wh_floor(p.qty_kwh) - matched_b.get(pid, 0)) for pid, p in buyers.items()
    }
    unmatched_sell = {
        pid: max(0, _kwh_to_wh_floor(p.qty_kwh) - matched_s.get(pid, 0)) for pid, p in sellers.items()
    }

    loadings = _recompute_line_loadings(cleared, positions, feeder, params)
    in_root = input_root(positions)
    out_hash = result_hash(cleared, price.p_ref)

    return ClearingResult(
        trades=tuple(cleared),
        p_ref=price.p_ref,
        p_raw=price.p_raw,
        sdr=price.sdr,
        unmatched_buy_wh=unmatched_buy,
        unmatched_sell_wh=unmatched_sell,
        line_loading_kw=loadings,
        input_root=in_root,
        result_hash=out_hash,
        match_status=matched.status,
    )
