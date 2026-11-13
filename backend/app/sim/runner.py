"""Headless market simulator: runs whole markets interval by interval and writes CSVs.

Per interval:
  1. every participant builds a net position from its forecast (load, PV, battery, EV) and its bot
  2. reputation gate + volume cap (Phase 3 hand-off) when defenses are on
  3. commit/reveal: non-revealed positions are dropped and penalised as reveal misses
  4. clear with the selected mode (B0..B3); ring members' bilateral wash trades are added
  5. physical delivery from *actual* weather/load; signed meter readings are produced and verified
  6. shortfall settlement (Phase 3 shortfall.py) and grid fallback for every residual
  7. reputation update (Phase 3 score.py / tiers.py)
  8. every ``detection_every`` intervals: collusion, communities, anomaly, false-report checks
  9. fairness and market metrics (Phase 3 fairness.py)

Outputs (all deterministic for a given seed and code version):
  intervals.csv  trades.csv  reputation.csv  flags.csv  fairness.csv  participants.csv
  summary.json   config.json (includes git commit)   timing.csv (wall-clock, NOT deterministic)
"""

from __future__ import annotations

import csv
import json
import math
import subprocess
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from app.core.params import DEFAULT_PARAMS, MarketParams
from app.engine.clearing import ClearedTrade, ClearingResult, _recompute_line_loadings
from app.engine.ev import ev_buy_limit_price
from app.engine.grid import Feeder, default_13_node_feeder, with_line_capacities
from app.engine.pricing import Position
from app.reputation import fairness as F
from app.reputation.params import ReputationParams
from app.reputation.score import (
    BetaState,
    Evidence,
    delivery_ratio,
    initial_state,
    reputation,
    reveal_miss_evidence,
    update,
)
from app.reputation.shortfall import settle_shortfall
from app.reputation.sybil import (
    Flag,
    PositionRecord,
    WindowTrade,
    anomaly_flags,
    anomaly_scores,
    build_features,
    collusion_flags,
    false_report_flags,
    honesty_anomaly,
    pv_plausibility,
)
from app.reputation.tiers import Tier, classify, matching_reputation, volume_cap_kwh
from app.sim import baselines
from app.sim.bots import BOT_KINDS, Bot, Honest, SybilIdentity
from app.sim.forecast import (
    EV,
    SLOTS_PER_DAY,
    Battery,
    Weather,
    clear_sky_factor,
    ev_sessions,
    load_shape,
    pv_kwh,
)
from app.sim.meters import MeterKey, MeterReading, verify
from app.sim.scenarios import Scenario, get

ENGINE_VERSION_FILE = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class SimConfig:
    scenario: str = "honest"
    participants: int = 100
    days: int = 1
    seed: int = 42
    defenses: bool = True
    mode: str = "B3"
    q_base_kwh: float = 2.0  # volume cap base per interval (Q_base)
    detection_every: int = 12
    sign_meters: bool = True


@dataclass
class Totals:
    bill: float = 0.0  # paise paid (P2P + grid imports - compensation received)
    revenue: float = 0.0  # paise received (P2P + grid exports - compensation/penalty paid)
    grid_only_bill: float = 0.0
    grid_only_revenue: float = 0.0
    bought_p2p_wh: int = 0
    sold_p2p_wh: int = 0
    shortfall_wh: int = 0
    penalty_paise: int = 0
    active_intervals: int = 0
    reveal_misses: int = 0

    @property
    def gain(self) -> float:
        """Welfare gain vs grid-only trading (paise)."""
        return (self.grid_only_bill - self.bill) + (self.revenue - self.grid_only_revenue)


@dataclass
class Participant:
    pid: str
    ptype: str  # consumer | prosumer | ev
    node: str
    bot: Bot
    rng: np.random.Generator
    key: MeterKey
    daily_kwh: float
    pv_kw: float
    bid_frac: float
    ask_frac: float
    battery: Optional[Battery] = None
    ev: Optional[EV] = None
    idle: Tuple[int, int] = (0, 0)  # [start, end) intervals with no activity
    rep: BetaState = field(default_factory=initial_state)
    tier: Optional[Tier] = None
    a_i: float = 0.0
    c_i: float = 0.0
    totals: Totals = field(default_factory=Totals)

    def active(self, t: int) -> bool:
        return not (self.idle[0] <= t < self.idle[1])


# ─── helpers ───────────────────────────────────────────────────────────────────


def _fmt(x: Any) -> Any:
    if isinstance(x, float):
        if math.isinf(x) or math.isnan(x):
            return str(x)
        return f"{round(x, 6):.6f}".rstrip("0").rstrip(".") if x != 0 else "0"
    return x


class _Csv:
    def __init__(self, path: Path, header: Sequence[str]) -> None:
        self._f = path.open("w", newline="")
        self._w = csv.writer(self._f, lineterminator="\n")
        self._w.writerow(header)

    def row(self, values: Iterable[Any]) -> None:
        self._w.writerow([_fmt(v) for v in values])

    def close(self) -> None:
        self._f.close()


def git_commit() -> Dict[str, Any]:
    try:
        root = ENGINE_VERSION_FILE
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True).stdout.strip())
        return {"commit": sha, "dirty": dirty}
    except Exception:
        return {"commit": "unknown", "dirty": None}


def _wh(kwh: float) -> int:
    return max(0, int(round(kwh * 1000.0)))


def _round_kwh(x: float) -> float:
    return round(x, 3)


# ─── population ────────────────────────────────────────────────────────────────


def build_population(
    cfg: SimConfig, sc: Scenario, intervals: int, seeds: List[np.random.SeedSequence], params: MarketParams
) -> List[Participant]:
    assign_rng = np.random.default_rng(seeds[1])
    n = cfg.participants
    n_c = int(round(n * sc.mix[0]))
    n_e = int(round(n * sc.mix[2]))
    n_p = n - n_c - n_e
    types = ["consumer"] * n_c + ["prosumer"] * n_p + ["ev"] * n_e
    types = [types[i] for i in assign_rng.permutation(n)]
    nodes = [f"n{i}" for i in range(1, 13)]

    people: List[Participant] = []
    for i, ptype in enumerate(types):
        pid = f"p{i:03d}"
        rng = np.random.default_rng(seeds[3 + i])
        node = nodes[i % len(nodes)]
        if sc.isolated_node and node == "n12" and i >= len(nodes):
            node = nodes[i % (len(nodes) - 1)]  # only the first n12 participant stays isolated
        p = Participant(
            pid=pid,
            ptype=ptype,
            node=node,
            bot=Honest(),
            rng=rng,
            key=MeterKey(cfg.seed, pid),
            daily_kwh=float(rng.uniform(4.0, 10.0)) * sc.load_scale,
            pv_kw=float(rng.uniform(2.0, 5.0)) * sc.pv_scale if ptype == "prosumer" else 0.0,
            bid_frac=float(rng.uniform(0.0, 0.10)),  # near-truthful: reservation = grid price
            ask_frac=float(rng.uniform(0.0, 0.10)),
        )
        if ptype == "prosumer" and rng.random() < sc.battery_share:
            cap = float(rng.uniform(5.0, 10.0))
            p.battery = Battery(capacity_kwh=cap, soc_kwh=cap / 2)
        if ptype == "ev":
            cap = float(rng.uniform(30.0, 60.0))
            ev = EV(capacity_kwh=cap, p_max_kw=float(rng.choice([3.3, 7.2])), v2g=bool(rng.random() < sc.v2g_share))
            ev.sessions = ev_sessions(intervals, rng, cap, depart_mean_h=sc.ev_depart_mean_h, depart_sd_h=sc.ev_depart_sd_h)
            p.ev = ev
        people.append(p)

    # bots
    taken: set[str] = set()
    for spec in sc.bots:
        pool = sorted(p.pid for p in people if p.ptype in spec.eligible and p.pid not in taken)
        k = spec.count if spec.count else max(1, int(round(spec.fraction * len(pool))))
        k = min(k, len(pool))
        chosen = sorted(assign_rng.choice(pool, size=k, replace=False).tolist()) if k else []
        for pid in chosen:
            p = next(x for x in people if x.pid == pid)
            p.bot = BOT_KINDS[spec.kind](group=spec.group, **spec.params)
            if spec.pv_multiplier != 1.0:
                p.pv_kw = max(p.pv_kw, 3.0) * spec.pv_multiplier
                p.battery = None
            taken.add(pid)

    # sybil identities (extra, on top of --participants)
    for j in range(sc.sybil_count):
        pid = f"sybil{j:02d}"
        rng = np.random.default_rng(seeds[3 + n + j])
        people.append(
            Participant(
                pid=pid, ptype="consumer", node=nodes[j % len(nodes)], bot=SybilIdentity(group="sybil_farm"),
                rng=rng, key=MeterKey(cfg.seed, pid), daily_kwh=0.0, pv_kw=0.0, bid_frac=0.0, ask_frac=0.0,
            )
        )

    # long absence (edge case 10)
    frac, d0, d1 = sc.absence
    if frac > 0:
        honest = sorted(p.pid for p in people if p.bot.kind == "honest" and not p.bot.group)
        k = int(round(frac * len(honest)))
        for pid in sorted(assign_rng.choice(honest, size=k, replace=False).tolist()):
            p = next(x for x in people if x.pid == pid)
            p.idle = (d0 * SLOTS_PER_DAY, d1 * SLOTS_PER_DAY)
    return people


def build_feeder(sc: Scenario) -> Feeder:
    f = default_13_node_feeder(capacity_kw=sc.capacity_kw)
    return with_line_capacities(f, sc.line_overrides) if sc.line_overrides else f


# ─── simulation ────────────────────────────────────────────────────────────────


@dataclass
class _Plan:
    """One participant's interval plan: forecast position plus the physical outcome."""

    position: Optional[Position]
    actual_net_kwh: float  # actual physical net consumption (+ need, - surplus)
    reported_pv_kwh: float
    revealed: bool = True


def run(cfg: SimConfig, out_dir: str | Path) -> Dict[str, Any]:
    sc = get(cfg.scenario)
    if cfg.mode not in baselines.MODES:
        raise ValueError(f"mode must be one of {baselines.MODES}")
    params = replace(DEFAULT_PARAMS, **sc.params_overrides) if sc.params_overrides else DEFAULT_PARAMS
    rparams = ReputationParams.from_market(params)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    intervals = cfg.days * SLOTS_PER_DAY
    seeds = np.random.SeedSequence(cfg.seed).spawn(3 + cfg.participants + sc.sybil_count)
    weather = Weather.generate(intervals, np.random.default_rng(seeds[0]), sc.cloud_volatility)
    b1_rng = np.random.default_rng(seeds[2])
    feeder = build_feeder(sc)
    caps = {ln.id: ln.capacity_kw for ln in feeder.lines}
    people = build_population(cfg, sc, intervals, seeds, params)
    by_id = {p.pid: p for p in people}
    use_rep = cfg.defenses and cfg.mode == "B3"
    detect = cfg.mode == "B3"
    corridor = float(params.p_ret - params.p_fit)

    w_int = _Csv(out / "intervals.csv", [
        "interval", "day", "slot", "p_ref", "p_raw", "sdr", "n_positions", "supply_wh", "demand_wh",
        "matched_wh", "bilateral_wh", "unmatched_buy_wh", "unmatched_sell_wh", "max_line_util",
        "line_violations", "p2p_line_violations", "reveal_misses", "readings_verified", "readings_failed",
        "balance_mismatch_kwh", "input_root", "result_hash", "match_status",
    ])
    w_tr = _Csv(out / "trades.csv", ["interval", "buyer_id", "seller_id", "qty_wh", "price", "delivered_wh", "reported_wh", "channel"])
    w_rep = _Csv(out / "reputation.csv", ["interval", "participant_id", "alpha", "beta", "evidence_count", "reputation", "tier"])
    w_flag = _Csv(out / "flags.csv", ["interval", "kind", "severity", "participant_ids", "evidence"])
    w_fair = _Csv(out / "fairness.csv", [
        "interval", "jain", "gini_gain", "hhi", "small_actor_parity", "matching_rate", "seller_satisfaction",
        "buyer_saving_pct", "seller_uplift_pct", "buyer_surplus_share", "welfare", "welfare_optimal",
        "welfare_efficiency", "max_price_impact", "reputation_gini", "grid_trust_density",
    ])
    w_time = _Csv(out / "timing.csv", ["interval", "clear_ms"])

    prev_p_ref: Optional[float] = None
    window: List[WindowTrade] = []
    records: List[Tuple[int, PositionRecord]] = []
    pv_scores: Dict[str, List[Tuple[int, float]]] = {}
    balance_bad: List[Tuple[int, float]] = []
    backup_history: List[Tuple[Dict[str, int], Dict[str, int]]] = []
    start_rep: Dict[str, float] = {}
    flag_counts: Dict[str, int] = {}
    violations_total = 0
    p2p_violations_total = 0
    bad_readings_total = 0

    for t in range(intervals):
        slot = t % SLOTS_PER_DAY
        cloud_f, cloud_a = weather.forecast(t), weather.actual(t)

        # 1-3. positions ------------------------------------------------------
        plans: Dict[str, _Plan] = {}
        for p in people:
            if not p.active(t):
                continue
            plans[p.pid] = _plan(p, t, slot, cloud_f, cloud_a, params, rparams, cfg, use_rep, corridor)
        positions = sorted(
            (pl.position for pl in plans.values() if pl.position is not None and pl.revealed),
            key=lambda x: x.participant_id,
        )

        # 4. clear --------------------------------------------------------------
        t0 = time.perf_counter()
        if positions:
            res = baselines.clear(cfg.mode, positions, feeder, params, prev_p_ref, b1_rng)
            prev_p_ref = res.p_ref
        else:
            res = baselines.clear_b0([], feeder, params)
        clear_ms = (time.perf_counter() - t0) * 1000.0

        p_ref = res.p_ref if positions else float(params.p_ret)
        bilateral: List[Tuple[str, str, int]] = []
        if cfg.mode != "B0":
            ring = sorted(p.pid for p in people if p.bot.kind == "ring" and p.active(t))
            for pid in ring:
                for s, b, q in by_id[pid].bot.bilateral(t, ring, pid):
                    bilateral.append((s, b, _wh(q)))

        # 5-6. delivery, meters, settlement ------------------------------------
        promised: Dict[str, int] = {}
        for tr in res.trades:
            promised[tr.seller_id] = promised.get(tr.seller_id, 0) + tr.qty_wh
        delivered_phys: Dict[str, int] = {}
        delivered_rep: Dict[str, int] = {}
        for sid, q in promised.items():
            p = by_id[sid]
            avail = _wh(max(0.0, -plans[sid].actual_net_kwh))
            d = max(0, min(q, p.bot.deliver(t, q, avail)))
            delivered_phys[sid] = d
            delivered_rep[sid] = max(0, min(q, p.bot.report_delivery(t, d, q)))

        p2p_in: Dict[str, float] = {}
        p2p_out: Dict[str, float] = {}
        money_bill: Dict[str, float] = {}
        money_rev: Dict[str, float] = {}
        for trade, rep_wh, phys_wh in _split_delivery(res.trades, promised, delivered_rep, delivered_phys):
            st = settle_shortfall(trade.qty_wh, rep_wh, p_ref, params)
            money_bill[trade.buyer_id] = money_bill.get(trade.buyer_id, 0.0) + st.payment_paise - st.compensation_paise
            money_rev[trade.seller_id] = money_rev.get(trade.seller_id, 0.0) + st.payment_paise - st.compensation_paise - st.penalty_paise
            p2p_in[trade.buyer_id] = p2p_in.get(trade.buyer_id, 0.0) + phys_wh / 1000.0
            p2p_out[trade.seller_id] = p2p_out.get(trade.seller_id, 0.0) + phys_wh / 1000.0
            by_id[trade.buyer_id].totals.bought_p2p_wh += phys_wh
            by_id[trade.seller_id].totals.sold_p2p_wh += phys_wh
            by_id[trade.seller_id].totals.shortfall_wh += st.shortfall_wh
            by_id[trade.seller_id].totals.penalty_paise += st.penalty_paise
            w_tr.row([t, trade.buyer_id, trade.seller_id, trade.qty_wh, p_ref, phys_wh, rep_wh, "market"])
        for s, b, q in bilateral:
            pay = q * p_ref / 1000.0
            money_bill[b] = money_bill.get(b, 0.0) + pay
            money_rev[s] = money_rev.get(s, 0.0) + pay
            p2p_in[b] = p2p_in.get(b, 0.0) + q / 1000.0
            p2p_out[s] = p2p_out.get(s, 0.0) + q / 1000.0
            w_tr.row([t, b, s, q, p_ref, q, q, "bilateral"])

        verified = failed = 0
        overclaim_kwh = 0.0  # claimed export - physically delivered export (feeder balance gap)
        for pid, pl in plans.items():
            p = by_id[pid]
            residual = pl.actual_net_kwh - p2p_in.get(pid, 0.0) + p2p_out.get(pid, 0.0)
            g_imp, g_exp = max(0.0, residual), max(0.0, -residual)
            p.totals.bill += money_bill.get(pid, 0.0) + g_imp * params.p_ret
            p.totals.revenue += money_rev.get(pid, 0.0) + g_exp * params.p_fit
            p.totals.grid_only_bill += max(0.0, pl.actual_net_kwh) * params.p_ret
            p.totals.grid_only_revenue += max(0.0, -pl.actual_net_kwh) * params.p_fit
            p.totals.active_intervals += 1
            # meter reading: P2P export as claimed by the participant, everything else as measured
            claimed_out = (delivered_rep[pid] - delivered_phys[pid]) / 1000.0 if pid in delivered_rep else 0.0
            overclaim_kwh += claimed_out
            if cfg.sign_meters:
                reading = MeterReading(
                    participant_id=pid, interval=t,
                    export_wh=_wh(p2p_out.get(pid, 0.0) + claimed_out + g_exp),
                    import_wh=_wh(p2p_in.get(pid, 0.0) + g_imp),
                    pv_wh=_wh(pl.reported_pv_kwh),
                )
                if verify(p.key.sign(reading), p.key.address):
                    verified += 1
                else:
                    failed += 1
            if detect and p.pv_kw > 0:
                score = pv_plausibility(pl.reported_pv_kwh, p.pv_kw, clear_sky_factor(slot), rparams)
                if score > 0:
                    pv_scores.setdefault(pid, []).append((t, score))
        bad_readings_total += failed
        # Feeder energy balance: sum of meter readings vs the substation meter. The only way they
        # diverge in this simulation is exported energy that was claimed but never delivered.
        mismatch = abs(overclaim_kwh)
        if detect and mismatch > max(0.1, rparams.balance_tolerance * matched_kwh_total(res)):
            balance_bad.append((t, mismatch))
        backup_history.append((
            {pl.position.participant_id: _wh(pl.position.qty_kwh) for pl in plans.values() if pl.position is not None and pl.revealed},
            {pid: _wh(v) for pid, v in {**p2p_in, **p2p_out}.items()},
        ))

        # 7. reputation ---------------------------------------------------------
        vol: Dict[str, float] = {}
        for tr in res.trades:
            vol[tr.buyer_id] = vol.get(tr.buyer_id, 0.0) + tr.qty_wh / 1000.0
            vol[tr.seller_id] = vol.get(tr.seller_id, 0.0) + tr.qty_wh / 1000.0
        for s, b, q in bilateral:
            vol[s] = vol.get(s, 0.0) + q / 1000.0
            vol[b] = vol.get(b, 0.0) + q / 1000.0
        reveal_misses = 0
        for p in people:
            pl_opt = plans.get(p.pid)
            pv_now = 0.0
            if use_rep and pv_scores.get(p.pid) and pv_scores[p.pid][-1][0] == t:
                pv_now = pv_scores[p.pid][-1][1]
            a_i = honesty_anomaly(p.a_i, pv_now) if use_rep else 0.0
            c_i = p.c_i if use_rep else 0.0
            if pl_opt is not None and pl_opt.position is not None and not pl_opt.revealed:
                ev: Optional[Evidence] = reveal_miss_evidence(anomaly=a_i, collusion=c_i)
                reveal_misses += 1
                p.totals.reveal_misses += 1
            elif p.pid in vol:
                r_del = delivery_ratio(promised[p.pid], delivered_rep[p.pid]) if p.pid in promised else 1.0
                ev = Evidence(r_del=r_del, anomaly=a_i, collusion=c_i, volume_kwh=vol[p.pid])
            else:
                ev = None
            p.rep = update(p.rep, ev, rparams)
            p.tier = classify(p.rep, rparams, prev_tier=p.tier)
            r = reputation(p.rep, rparams)
            if t == 0:
                start_rep[p.pid] = r
            if t % 4 == 3 or t == intervals - 1:  # hourly snapshot keeps the CSV small
                w_rep.row([t, p.pid, p.rep.alpha, p.rep.beta, p.rep.evidence_count, r, p.tier.value])

        # windows for detection
        for tr in res.trades:
            window.append(WindowTrade(t, tr.buyer_id, tr.seller_id, tr.qty_wh))
        for s, b, q in bilateral:
            window.append(WindowTrade(t, b, s, q))
        matched_by: Dict[str, float] = {}
        for tr in res.trades:
            matched_by[tr.buyer_id] = matched_by.get(tr.buyer_id, 0.0) + tr.qty_wh / 1000.0
            matched_by[tr.seller_id] = matched_by.get(tr.seller_id, 0.0) + tr.qty_wh / 1000.0
        for pos in positions:
            records.append((t, PositionRecord(pos.participant_id, pos.qty_kwh, pos.limit_price, matched_by.get(pos.participant_id, 0.0), p_ref)))

        # 8. detection ----------------------------------------------------------
        if detect and (t + 1) % cfg.detection_every == 0:
            lo = t - rparams.collusion_window_intervals
            window = [w for w in window if w.interval > lo]
            records = [(i, r) for i, r in records if i > lo]
            flags: List[Flag] = []
            c_scores, cflags = collusion_flags(window, rparams, seed=cfg.seed)
            flags += cflags
            a_scores = anomaly_scores(build_features((r for _, r in records), corridor), seed=cfg.seed)
            flags += anomaly_flags(a_scores)
            since = t - cfg.detection_every
            pv_scores = {pid: [(i, s) for i, s in v if i > since] for pid, v in pv_scores.items()}
            recent_pv = {pid: max(s for _, s in v) for pid, v in pv_scores.items() if v}
            flags += false_report_flags(recent_pv)
            recent_bal = [m for i, m in balance_bad if i > t - cfg.detection_every]
            if recent_bal:
                flags.append(Flag("energy_imbalance", "medium", (), {"intervals": len(recent_bal), "max_mismatch_kwh": round(max(recent_bal), 6)}))
            for p in people:
                p.c_i = c_scores.get(p.pid, 0.0)
                # a_i persists until the next detection pass: worst of behaviour anomaly and
                # the false-report (PV plausibility) score seen in this window
                p.a_i = honesty_anomaly(a_scores.get(p.pid, 0.0), recent_pv.get(p.pid, 0.0))
            for fl in flags:
                flag_counts[fl.kind] = flag_counts.get(fl.kind, 0) + 1
                w_flag.row([t, fl.kind, fl.severity, ";".join(fl.participant_ids), json.dumps(fl.evidence, sort_keys=True)])

        # 9. metrics ------------------------------------------------------------
        util = max((abs(v) / caps[k] if caps[k] > 0 else (math.inf if abs(v) > 1e-9 else 0.0)) for k, v in res.line_loading_kw.items()) if res.line_loading_kw else 0.0
        n_viol = sum(1 for k, v in res.line_loading_kw.items() if abs(v) > caps[k] + 1e-6)
        violations_total += n_viol
        # Overloads P2P trading created or worsened, vs the same positions settled grid-only.
        # Base load alone can overload a tight feeder; that is not a market failure.
        n_p2p = 0
        if n_viol and res.trades:
            base = _recompute_line_loadings([], positions, feeder, params)
            n_p2p = sum(
                1 for k, v in res.line_loading_kw.items()
                if abs(v) > caps[k] + 1e-6 and abs(v) > abs(base.get(k, 0.0)) + 1e-6
            )
        p2p_violations_total += n_p2p
        supply_wh = sum(_wh(x.qty_kwh) for x in positions if x.side == "sell")
        demand_wh = sum(_wh(x.qty_kwh) for x in positions if x.side == "buy")
        matched_wh = sum(tr.qty_wh for tr in res.trades)
        w_int.row([
            t, t // SLOTS_PER_DAY, slot, res.p_ref, res.p_raw, res.sdr, len(positions), supply_wh, demand_wh,
            matched_wh, sum(q for _, _, q in bilateral), sum(res.unmatched_buy_wh.values()),
            sum(res.unmatched_sell_wh.values()), util, n_viol, n_p2p, reveal_misses, verified, failed,
            mismatch, res.input_root, res.result_hash, res.match_status,
        ])
        w_fair.row(_fairness_row(t, positions, res, plans, by_id, params, rparams, people))
        w_time.row([t, clear_ms])

    for w in (w_int, w_tr, w_rep, w_flag, w_fair, w_time):
        w.close()

    backup = F.grid_backup_frequency(backup_history)
    summary = _write_participants_and_summary(out, people, start_rep, rparams, cfg, flag_counts, (violations_total, p2p_violations_total), bad_readings_total, backup)
    config = {"sim": asdict(cfg), "scenario": _scenario_dict(sc), "params": asdict(params), "reputation_params": asdict(rparams), "git": git_commit()}
    (out / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True, default=str) + "\n")
    return summary


def matched_kwh_total(res: ClearingResult) -> float:
    return sum(tr.qty_wh for tr in res.trades) / 1000.0


def _plan(
    p: Participant, t: int, slot: int, cloud_f: float, cloud_a: float, params: MarketParams,
    rparams: ReputationParams, cfg: SimConfig, use_rep: bool, corridor: float,
) -> _Plan:
    bot = p.bot
    load_f = p.daily_kwh * load_shape(slot)
    load_a = load_f * float(p.rng.lognormal(0.0, 0.15)) if load_f > 0 else 0.0
    pv_true_f = pv_kwh(p.pv_kw, slot, cloud_f)
    pv_a = pv_kwh(p.pv_kw, slot, cloud_a)
    pv_offer_f = pv_true_f * bot.forecast_pv_multiplier(t)

    net_true = load_f - pv_true_f
    net_offer = load_f - pv_offer_f
    if p.battery is not None:
        before = net_true
        net_true = p.battery.dispatch(net_true)
        net_offer += net_true - before  # same battery action applies to the offer
    ev_buy = ev_sell = 0.0
    if p.ev is not None:
        p.ev.start_session_if_due(t)
        ev_buy = p.ev.charge_kwh(t)
        ev_sell = p.ev.v2g_sell_kwh(t) if ev_buy == 0 else 0.0
        p.ev.apply(ev_buy - ev_sell)
    net_true += ev_buy - ev_sell
    net_offer += ev_buy - ev_sell
    actual_net = net_true + (load_a - load_f) - (pv_a - pv_true_f)
    reported_pv = bot.report_pv(t, pv_a)

    position: Optional[Position] = None
    if not bot.public_market:
        return _Plan(None, actual_net, reported_pv)
    if bot.fake_demand:
        shaped = bot.shape_position(t, "buy", 0.0, float(params.p_ret), params.p_fit, params.p_ret)
        actual_net = 0.0
    else:
        side = "buy" if net_offer > 0 else "sell"
        qty = abs(net_offer)
        if side == "buy":
            limit = params.p_ret - p.bid_frac * corridor
            if ev_buy > 0 and p.ev is not None:
                limit = max(limit, ev_buy_limit_price(params.p_fit, params.p_ret, p.ev.need_kwh(), p.ev.p_max_kw, p.ev.hours_left(t)))
        else:
            limit = params.p_fit + p.ask_frac * corridor
        shaped = bot.shape_position(t, side, qty, limit, params.p_fit, params.p_ret)  # type: ignore[arg-type]
    if shaped is not None:
        side_s, qty_s, limit_s = shaped
        rep_engine = 1.0
        if use_rep:
            tier = classify(p.rep, rparams, prev_tier=p.tier)
            rep_engine = matching_reputation(p.rep, tier, rparams)
            qty_s = min(qty_s, volume_cap_kwh(cfg.q_base_kwh, reputation(p.rep, rparams), rparams))
        qty_s = _round_kwh(qty_s)
        if qty_s >= 0.001:
            position = Position(
                participant_id=p.pid, side=side_s, qty_kwh=qty_s, limit_price=float(limit_s),
                reputation=rep_engine, node_id=p.node,
            )
    revealed = bot.reveals(t, p.rng) if position is not None else True
    return _Plan(position, actual_net, reported_pv, revealed)


def _split_delivery(
    trades: Sequence[ClearedTrade], promised: Dict[str, int], rep: Dict[str, int], phys: Dict[str, int]
) -> List[Tuple[ClearedTrade, int, int]]:
    """Allocate each seller's delivered Wh across its trades pro rata (floor, remainder in order)."""
    out: List[Tuple[ClearedTrade, int, int]] = []
    by_seller: Dict[str, List[ClearedTrade]] = {}
    for tr in sorted(trades, key=lambda x: (x.seller_id, x.buyer_id)):
        by_seller.setdefault(tr.seller_id, []).append(tr)
    for sid, trs in by_seller.items():
        total = promised[sid]
        rep_parts = _pro_rata([t.qty_wh for t in trs], rep[sid], total)
        phys_parts = _pro_rata([t.qty_wh for t in trs], phys[sid], total)
        for tr, r, ph in zip(trs, rep_parts, phys_parts):
            out.append((tr, r, ph))
    return out


def _pro_rata(qtys: List[int], amount: int, total: int) -> List[int]:
    if total <= 0:
        return [0] * len(qtys)
    parts = [q * amount // total for q in qtys]
    rem = amount - sum(parts)
    for i in range(len(parts)):
        if rem <= 0:
            break
        if parts[i] < qtys[i]:
            parts[i] += 1
            rem -= 1
    return parts


def _fairness_row(
    t: int, positions: Sequence[Position], res: ClearingResult, plans: Dict[str, _Plan],
    by_id: Dict[str, Participant], params: MarketParams, rparams: ReputationParams, people: Sequence[Participant],
) -> List[Any]:
    offered = {p.participant_id: _wh(p.qty_kwh) for p in positions}
    matched: Dict[str, int] = {}
    sell_matched: Dict[str, int] = {}
    for tr in res.trades:
        matched[tr.buyer_id] = matched.get(tr.buyer_id, 0) + tr.qty_wh
        matched[tr.seller_id] = matched.get(tr.seller_id, 0) + tr.qty_wh
        sell_matched[tr.seller_id] = sell_matched.get(tr.seller_id, 0) + tr.qty_wh
    shares = F.matched_shares(offered, matched)
    gains = F.welfare_gains(res.trades, res.p_ref, params, participants=offered.keys())
    econ = F.market_economics(res.trades, res.unmatched_buy_wh, res.unmatched_sell_wh, res.p_ref, params)
    welfare = F.trade_welfare(res.trades, positions)
    optimal = _optimal_welfare(positions, res.p_ref, rparams.rho_min)
    sell_offered = {p.participant_id: _wh(p.qty_kwh) for p in positions if p.side == "sell"}
    total_buy = sum(v for k, v in offered.items() if k not in sell_offered)
    reps = {p.pid: reputation(p.rep, rparams) for p in people}
    tiers = {p.pid: p.tier for p in people if p.tier is not None}
    return [
        t, F.jain_index(list(shares.values())), F.gini(list(gains.values())), F.hhi(sell_matched),
        F.small_actor_parity(offered, matched), F.matching_rate(total_buy, sum(sell_offered.values()), sum(sell_matched.values())),
        F.seller_satisfaction_index(sell_offered, sell_matched), econ.buyer_saving_pct, econ.seller_uplift_pct,
        econ.buyer_surplus_share, welfare, optimal, F.welfare_efficiency(welfare, optimal),
        F.max_price_impact(positions, params) if positions else 0.0, F.reputation_gini(reps), F.grid_trust_density(tiers),
    ]


def _optimal_welfare(positions: Sequence[Position], p_ref: float, rho_min: float) -> float:
    """Unconstrained optimum among eligible positions: greedy highest bids vs lowest asks."""
    bids = sorted(((p.limit_price, p.qty_kwh) for p in positions if p.side == "buy" and p.limit_price >= p_ref and p.reputation >= rho_min), reverse=True)
    asks = sorted((p.limit_price, p.qty_kwh) for p in positions if p.side == "sell" and p.limit_price <= p_ref and p.reputation >= rho_min)
    total = 0.0
    i = j = 0
    qb = bids[0][1] if bids else 0.0
    qa = asks[0][1] if asks else 0.0
    while i < len(bids) and j < len(asks) and bids[i][0] >= asks[j][0]:
        q = min(qb, qa)
        total += (bids[i][0] - asks[j][0]) * q
        qb -= q
        qa -= q
        if qb <= 1e-12:
            i += 1
            qb = bids[i][1] if i < len(bids) else 0.0
        if qa <= 1e-12:
            j += 1
            qa = asks[j][1] if j < len(asks) else 0.0
    return total


def _scenario_dict(sc: Scenario) -> Dict[str, Any]:
    d = asdict(sc)
    d["bots"] = [asdict(b) for b in sc.bots]
    return d


def _write_participants_and_summary(
    out: Path, people: Sequence[Participant], start_rep: Dict[str, float], rparams: ReputationParams,
    cfg: SimConfig, flag_counts: Dict[str, int], violations: Tuple[int, int], bad_readings: int,
    backup: Dict[str, float],
) -> Dict[str, Any]:
    w = _Csv(out / "participants.csv", [
        "participant_id", "type", "bot", "group", "node", "address", "pv_kw", "battery_kwh", "ev_kwh", "v2g",
        "bill_paise", "revenue_paise", "grid_only_bill_paise", "grid_only_revenue_paise", "gain_paise",
        "bought_p2p_wh", "sold_p2p_wh", "shortfall_wh", "penalty_paise", "reveal_misses", "active_intervals",
        "grid_backup_frequency", "final_reputation", "final_tier",
    ])
    end_rep: Dict[str, float] = {}
    for p in people:
        r = reputation(p.rep, rparams)
        end_rep[p.pid] = r
        tt = p.totals
        w.row([
            p.pid, p.ptype, p.bot.kind, p.bot.group, p.node, p.key.address, p.pv_kw,
            p.battery.capacity_kwh if p.battery else 0.0, p.ev.capacity_kwh if p.ev else 0.0,
            int(bool(p.ev and p.ev.v2g)), tt.bill, tt.revenue, tt.grid_only_bill, tt.grid_only_revenue, tt.gain,
            tt.bought_p2p_wh, tt.sold_p2p_wh, tt.shortfall_wh, tt.penalty_paise, tt.reveal_misses, tt.active_intervals,
            backup.get(p.pid, 0.0), r, p.tier.value if p.tier else "",
        ])
    w.close()

    def agg(ps: Sequence[Participant]) -> Dict[str, float]:
        bill = sum(p.totals.bill for p in ps)
        gbill = sum(p.totals.grid_only_bill for p in ps)
        rev = sum(p.totals.revenue for p in ps)
        grev = sum(p.totals.grid_only_revenue for p in ps)
        return {
            "bill_paise": round(bill, 2), "grid_only_bill_paise": round(gbill, 2),
            "bill_saving_pct": round(100.0 * (1 - bill / gbill), 4) if gbill > 0 else 0.0,
            "revenue_paise": round(rev, 2), "grid_only_revenue_paise": round(grev, 2),
            "revenue_uplift_pct": round(100.0 * (rev / grev - 1), 4) if grev > 0 else 0.0,
            "gain_paise": round(sum(p.totals.gain for p in ps), 2),
        }

    kinds = sorted({p.bot.kind for p in people})
    groups = sorted({p.bot.group for p in people if p.bot.group})
    honest = [p for p in people if p.bot.kind == "honest" and not p.bot.group]
    summary: Dict[str, Any] = {
        "scenario": cfg.scenario, "mode": cfg.mode, "defenses": cfg.defenses, "seed": cfg.seed,
        "participants": len(people), "intervals": cfg.days * SLOTS_PER_DAY,
        "market": agg(people),
        "honest": agg(honest),
        "groups": {g: agg([p for p in people if p.bot.group == g]) for g in groups},
        "mean_final_reputation_by_bot": {
            k: round(float(np.mean([end_rep[p.pid] for p in people if p.bot.kind == k])), 6) for k in kinds
        },
        "line_violations": violations[0],
        "p2p_line_violations": violations[1],
        "meter_readings_failed": bad_readings,
        "flags": dict(sorted(flag_counts.items())),
        "reputation_mobility": F.reputation_mobility(start_rep, end_rep),
        "reputation_gini_end": F.reputation_gini(end_rep),
        "grid_backup_frequency_max": max(backup.values()) if backup else 0.0,
        "participants_always_on_grid_backup": sum(1 for v in backup.values() if v >= 1.0),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary
