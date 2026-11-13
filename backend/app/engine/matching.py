"""QP matching with reputation, fairness soft-share, and feeder limits (pure I/O)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

import cvxpy as cp

from app.core.params import MarketParams
from app.engine.grid import Feeder, build_pi_matrix, incidence_root_to_node
from app.engine.pricing import Position

EPS = 1e-9


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
        if not (b.limit_price + EPS >= p_ref):
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
        return MatchResult(
            trades=(),
            unmatched_buy_kwh={b.participant_id: b.qty_kwh for b in buyers},
            unmatched_sell_kwh={s.participant_id: s.qty_kwh for s in sellers},
            line_loading_kw={line.id: 0.0 for line in feeder.lines},
            status="no_counterparties",
        )

    pairs = _eligible_pairs(buyers, sellers, p_ref, params)
    buyer_ids = [b.participant_id for b in buyers]
    seller_ids = [s.participant_id for s in sellers]
    buyer_by_id = {b.participant_id: b for b in buyers}
    seller_by_id = {s.participant_id: s for s in sellers}

    if not pairs:
        return MatchResult(
            trades=(),
            unmatched_buy_kwh={b.participant_id: b.qty_kwh for b in buyers},
            unmatched_sell_kwh={s.participant_id: s.qty_kwh for s in sellers},
            line_loading_kw={line.id: 0.0 for line in feeder.lines},
            status="no_eligible_pairs",
        )

    # Decision vars x[(b,s)]
    x_vars: Dict[Tuple[str, str], cp.Variable] = {
        (b.participant_id, s.participant_id): cp.Variable(nonneg=True) for b, s in pairs
    }

    # Quantity constraints
    constraints: List[cp.Constraint] = []
    for b in buyers:
        terms = [x_vars[(b.participant_id, s.participant_id)] for s in sellers if (b.participant_id, s.participant_id) in x_vars]
        if terms:
            constraints.append(cp.sum(terms) <= b.qty_kwh)
    for s in sellers:
        terms = [x_vars[(b.participant_id, s.participant_id)] for b in buyers if (b.participant_id, s.participant_id) in x_vars]
        if terms:
            constraints.append(cp.sum(terms) <= s.qty_kwh)

    # Welfare objective terms
    welfare_terms = []
    for (bid, sid), var in x_vars.items():
        b = buyer_by_id[bid]
        s = seller_by_id[sid]
        surplus = (b.limit_price - s.limit_price) + params.beta * min(s.reputation, params.r_cap)
        welfare_terms.append(surplus * var)

    # Proportional-share soft penalty on the long side
    buy_total = sum(b.qty_kwh for b in buyers)
    sell_total = sum(s.qty_kwh for s in sellers)
    long_is_sellers = sdr > 1.0
    penalty_terms = []
    if long_is_sellers and sell_total > EPS and buy_total > EPS:
        short_total = buy_total
        long_total = sell_total
        for s in sellers:
            y = cp.sum(
                [x_vars[(b.participant_id, s.participant_id)] for b in buyers if (b.participant_id, s.participant_id) in x_vars]
                or [0.0]
            )
            share = short_total * s.qty_kwh / long_total
            penalty_terms.append(cp.square(y - share))
    elif (not long_is_sellers) and buy_total > EPS and sell_total > EPS:
        short_total = sell_total
        long_total = buy_total
        for b in buyers:
            y = cp.sum(
                [x_vars[(b.participant_id, s.participant_id)] for s in sellers if (b.participant_id, s.participant_id) in x_vars]
                or [0.0]
            )
            share = short_total * b.qty_kwh / long_total
            penalty_terms.append(cp.square(y - share))

    # Grid line constraints including residual grid import/export flows
    dt = params.dt_hours
    buyer_nodes = {b.participant_id: b.node_id for b in buyers}
    seller_nodes = {s.participant_id: s.node_id for s in sellers}
    pi = build_pi_matrix(feeder, buyer_ids, seller_ids, buyer_nodes, seller_nodes)
    root_inc = {n: incidence_root_to_node(feeder, n) for n in {*buyer_nodes.values(), *seller_nodes.values(), feeder.root}}

    # Matched volume per participant
    matched_buy = {
        b.participant_id: cp.sum(
            [x_vars[(b.participant_id, s.participant_id)] for s in sellers if (b.participant_id, s.participant_id) in x_vars]
            or [0.0]
        )
        for b in buyers
    }
    matched_sell = {
        s.participant_id: cp.sum(
            [x_vars[(b.participant_id, s.participant_id)] for b in buyers if (b.participant_id, s.participant_id) in x_vars]
            or [0.0]
        )
        for s in sellers
    }

    line_expr: Dict[str, cp.Expression] = {}
    for line in feeder.lines:
        peer_flow = 0
        for (bid, sid), var in x_vars.items():
            coeff = pi[line.id].get((bid, sid), 0)
            if coeff != 0:
                peer_flow += coeff * var

        # Residual imports (buyers) flow root → buyer; exports (sellers) flow seller → root
        grid_flow = 0
        for b in buyers:
            residual = b.qty_kwh - matched_buy[b.participant_id]
            eta = root_inc[b.node_id].get(line.id, 0)
            if eta != 0:
                grid_flow += eta * residual
        for s in sellers:
            residual = s.qty_kwh - matched_sell[s.participant_id]
            eta = root_inc[s.node_id].get(line.id, 0)
            if eta != 0:
                # export toward root = opposite of root→node
                grid_flow += (-eta) * residual

        flow_kw = (peer_flow + grid_flow) / dt
        line_expr[line.id] = flow_kw
        constraints.append(flow_kw <= line.capacity_kw)
        constraints.append(-flow_kw <= line.capacity_kw)

    objective = cp.Maximize(
        cp.sum(welfare_terms)
        - params.match_lambda * (cp.sum(penalty_terms) if penalty_terms else 0.0)
    )
    problem = cp.Problem(objective, constraints)
    # Clarabel first; fall back to OSQP / SCS
    solved = False
    status = "unknown"
    for solver in (cp.CLARABEL, cp.OSQP, cp.SCS):
        try:
            problem.solve(solver=solver, warm_start=False, verbose=False)
            if problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) and problem.value is not None:
                solved = True
                status = str(problem.status)
                break
        except Exception:
            continue

    if not solved:
        return MatchResult(
            trades=(),
            unmatched_buy_kwh={b.participant_id: b.qty_kwh for b in buyers},
            unmatched_sell_kwh={s.participant_id: s.qty_kwh for s in sellers},
            line_loading_kw={line.id: 0.0 for line in feeder.lines},
            status=f"infeasible:{problem.status}",
        )

    trades: List[MatchTrade] = []
    for (bid, sid), var in x_vars.items():
        qty = float(var.value) if var.value is not None else 0.0
        if qty > 1e-8:
            trades.append(MatchTrade(buyer_id=bid, seller_id=sid, qty_kwh=qty))

    matched_b = {b.participant_id: 0.0 for b in buyers}
    matched_s = {s.participant_id: 0.0 for s in sellers}
    for t in trades:
        matched_b[t.buyer_id] += t.qty_kwh
        matched_s[t.seller_id] += t.qty_kwh

    loadings: Dict[str, float] = {}
    for line_id, expr in line_expr.items():
        loadings[line_id] = float(expr.value) if expr.value is not None else 0.0

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
