"""QP matching with reputation, fairness soft-share, and feeder limits (pure I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import cvxpy as cp
import numpy as np

from app.core.params import MarketParams
from app.engine.grid import Feeder, build_pi_matrix, incidence_root_to_node
from app.engine.pricing import Position

EPS = 1e-9
TRADE_EPS = 1e-8


@dataclass(frozen=True)
class MatchTrade:
    buyer_id: str
    seller_id: str
    qty_kwh: float


@dataclass(frozen=True)
class MatchResult:
    trades: Tuple[MatchTrade, ...]
    unmatched_buy_kwh: Dict[str, float]
    unmatched_sell_kwh: Dict[str, float]
    line_loading_kw: Dict[str, float]
    status: str


def _eligible_pairs(
    buyers: Sequence[Position],
    sellers: Sequence[Position],
    p_ref: float,
    params: MarketParams,
) -> List[Tuple[Position, Position]]:
    pairs: List[Tuple[Position, Position]] = []
    for b in buyers:
        if b.reputation < params.rho_min or b.qty_kwh <= 0:
            continue
        if p_ref > b.limit_price + EPS:
            continue
        for s in sellers:
            if s.reputation < params.rho_min or s.qty_kwh <= 0:
                continue
            if s.limit_price - EPS > p_ref:
                continue
            if s.reputation < b.min_seller_reputation:
                continue
            # a_j <= p_ref <= b_i
            if s.limit_price <= p_ref + EPS and p_ref <= b.limit_price + EPS:
                pairs.append((b, s))
    return pairs


def _empty_result(
    buyers: Sequence[Position],
    sellers: Sequence[Position],
    feeder: Feeder,
    status: str,
) -> MatchResult:
    return MatchResult(
        trades=(),
        unmatched_buy_kwh={b.participant_id: b.qty_kwh for b in buyers},
        unmatched_sell_kwh={s.participant_id: s.qty_kwh for s in sellers},
        line_loading_kw={line.id: 0.0 for line in feeder.lines},
        status=status,
    )


def match_orders(
    positions: Sequence[Position],
    feeder: Feeder,
    p_ref: float,
    sdr: float,
    params: MarketParams,
) -> MatchResult:
    """Solve the peer-matching QP. All accepted trades clear at ``p_ref``."""
    buyers = [p for p in positions if p.side == "buy" and p.qty_kwh > 0]
    sellers = [p for p in positions if p.side == "sell" and p.qty_kwh > 0]

    if not buyers or not sellers:
        return _empty_result(buyers, sellers, feeder, "no_counterparties")

    pairs = _eligible_pairs(buyers, sellers, p_ref, params)
    if not pairs:
        return _empty_result(buyers, sellers, feeder, "no_eligible_pairs")

    buyer_ids = [b.participant_id for b in buyers]
    seller_ids = [s.participant_id for s in sellers]
    buyer_index = {pid: i for i, pid in enumerate(buyer_ids)}
    seller_index = {pid: i for i, pid in enumerate(seller_ids)}
    n_b, n_s, n_p = len(buyers), len(sellers), len(pairs)

    # Flat decision vector over eligible pairs only.
    x = cp.Variable(n_p, nonneg=True)

    pair_buyer_idx = np.array([buyer_index[b.participant_id] for b, _ in pairs], dtype=int)
    pair_seller_idx = np.array([seller_index[s.participant_id] for _, s in pairs], dtype=int)

    # Incidence: buyer_map[i, k] = 1 if pair k involves buyer i
    buyer_map = np.zeros((n_b, n_p), dtype=float)
    seller_map = np.zeros((n_s, n_p), dtype=float)
    buyer_map[pair_buyer_idx, np.arange(n_p)] = 1.0
    seller_map[pair_seller_idx, np.arange(n_p)] = 1.0

    buy_qty = np.array([b.qty_kwh for b in buyers], dtype=float)
    sell_qty = np.array([s.qty_kwh for s in sellers], dtype=float)

    constraints: List[cp.Constraint] = [
        buyer_map @ x <= buy_qty,
        seller_map @ x <= sell_qty,
    ]

    # Welfare coefficients: (b_i - a_j) + beta * min(R_j, R_cap)
    surplus = np.array(
        [
            (b.limit_price - s.limit_price) + params.beta * min(s.reputation, params.r_cap)
            for b, s in pairs
        ],
        dtype=float,
    )
    welfare = surplus @ x

    # Proportional-share soft penalty on the long side
    buy_total = float(buy_qty.sum())
    sell_total = float(sell_qty.sum())
    penalty = 0.0
    if sdr > 1.0 and sell_total > EPS and buy_total > EPS:
        # Sellers long: target share of short (buy) total
        target = buy_total * sell_qty / sell_total
        y_sell = seller_map @ x
        penalty = cp.sum_squares(y_sell - target)
    elif sdr <= 1.0 and buy_total > EPS and sell_total > EPS:
        target = sell_total * buy_qty / buy_total
        y_buy = buyer_map @ x
        penalty = cp.sum_squares(y_buy - target)

    # Grid line constraints including residual grid import/export flows
    dt = params.dt_hours
    buyer_nodes = {b.participant_id: b.node_id for b in buyers}
    seller_nodes = {s.participant_id: s.node_id for s in sellers}
    pi = build_pi_matrix(feeder, buyer_ids, seller_ids, buyer_nodes, seller_nodes)
    root_inc = {
        n: incidence_root_to_node(feeder, n)
        for n in {*buyer_nodes.values(), *seller_nodes.values(), feeder.root}
    }

    matched_buy = buyer_map @ x  # shape (n_b,)
    matched_sell = seller_map @ x  # shape (n_s,)

    # Precompute peer-flow coefficients per line: coeff[k] = pi[line][(b,s)] for pair k
    line_ids = [line.id for line in feeder.lines]
    peer_coeff = np.zeros((len(line_ids), n_p), dtype=float)
    for k, (b, s) in enumerate(pairs):
        key = (b.participant_id, s.participant_id)
        for li, line_id in enumerate(line_ids):
            coeff = pi[line_id].get(key, 0)
            if coeff:
                peer_coeff[li, k] = float(coeff)

    # Residual grid-flow coefficients: unmatched buy flows root→buyer; sell flows seller→root
    # flow_line = peer @ x + buy_resid_coeff @ (q_b - matched_b) + sell_resid_coeff @ (q_s - matched_s)
    buy_resid_coeff = np.zeros((len(line_ids), n_b), dtype=float)
    sell_resid_coeff = np.zeros((len(line_ids), n_s), dtype=float)
    for bi, b in enumerate(buyers):
        eta = root_inc[b.node_id]
        for li, line_id in enumerate(line_ids):
            v = eta.get(line_id, 0)
            if v:
                buy_resid_coeff[li, bi] = float(v)
    for si, s in enumerate(sellers):
        eta = root_inc[s.node_id]
        for li, line_id in enumerate(line_ids):
            v = eta.get(line_id, 0)
            if v:
                sell_resid_coeff[li, si] = float(-v)  # export toward root

    peer_flow = peer_coeff @ x  # (n_lines,)
    buy_resid = buy_qty - matched_buy
    sell_resid = sell_qty - matched_sell
    grid_flow = buy_resid_coeff @ buy_resid + sell_resid_coeff @ sell_resid
    flow_kwh = peer_flow + grid_flow
    flow_kw = flow_kwh / dt

    capacities = np.array([line.capacity_kw for line in feeder.lines], dtype=float)
    constraints.append(flow_kw <= capacities)
    constraints.append(-flow_kw <= capacities)

    objective = cp.Maximize(welfare - params.match_lambda * penalty)
    problem = cp.Problem(objective, constraints)

    solved = False
    status = "unknown"
    # Prefer Clarabel; OSQP is a solid QP fallback; SCS last.
    for solver in (cp.CLARABEL, cp.OSQP, cp.SCS):
        try:
            problem.solve(solver=solver, warm_start=False, verbose=False)
            if problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) and x.value is not None:
                solved = True
                status = str(problem.status)
                break
        except Exception:
            continue

    if not solved:
        return _empty_result(buyers, sellers, feeder, f"infeasible:{problem.status}")

    x_val = np.asarray(x.value, dtype=float).reshape(-1)
    trades: List[MatchTrade] = []
    matched_b = {b.participant_id: 0.0 for b in buyers}
    matched_s = {s.participant_id: 0.0 for s in sellers}
    for k, (b, s) in enumerate(pairs):
        qty = float(x_val[k])
        if qty > TRADE_EPS:
            trades.append(
                MatchTrade(
                    buyer_id=b.participant_id,
                    seller_id=s.participant_id,
                    qty_kwh=qty,
                )
            )
            matched_b[b.participant_id] += qty
            matched_s[s.participant_id] += qty

    # Evaluate line loadings from the numeric solution (same affine form as constraints).
    matched_b_vec = np.array([matched_b[pid] for pid in buyer_ids], dtype=float)
    matched_s_vec = np.array([matched_s[pid] for pid in seller_ids], dtype=float)
    peer_num = peer_coeff @ x_val
    grid_num = buy_resid_coeff @ (buy_qty - matched_b_vec) + sell_resid_coeff @ (
        sell_qty - matched_s_vec
    )
    loadings = {
        line_id: float((peer_num[li] + grid_num[li]) / dt) for li, line_id in enumerate(line_ids)
    }

    return MatchResult(
        trades=tuple(trades),
        unmatched_buy_kwh={
            b.participant_id: max(0.0, b.qty_kwh - matched_b[b.participant_id]) for b in buyers
        },
        unmatched_sell_kwh={
            s.participant_id: max(0.0, s.qty_kwh - matched_s[s.participant_id]) for s in sellers
        },
        line_loading_kw=loadings,
        status=status,
    )
