"""Sybil, collusion, anomaly and false-report detection (pure functions).

Everything returns scores or ``Flag`` data records. Nothing here bans anyone: flags go to the
admin queue (Phase 10), scores feed the reputation evidence (c_i -> w_col, a_i -> r_hon).

Collusion (GEMINI.md Phase 3; adapted from wash-trading detection in crypto/NFT markets):
    V_ij = energy sold by i to j over a sliding window
    PC_i = max_j (V_ij + V_ji) / sum_k (V_ik + V_ki)          partner concentration
    RR_i = sum_j min(V_ij, V_ji) / sum_j V_ij                  round-trip ratio
    c_i  = clip(max((PC_i - 0.5) / 0.5, RR_i), 0, 1)
Communities: Louvain (networkx, fixed seed) on the volume-weighted graph; report communities
whose internal volume ratio exceeds 0.8.

Anomaly: IsolationForest (fixed random_state) on per-participant features. The Liu et al. (2008)
score s in (0, 1] is ~0.5 for normal points and -> 1 for anomalies; a_i = clip((s - 0.5)/0.5, 0, 1)
so an honest market does not automatically push its "most unusual" member to 1.

False reports: PV plausibility (reported <= rated_kw * clear_sky_factor * dt * 1.1) gives a_i;
the feeder energy-balance check cannot attribute blame to one meter, so it produces a feeder flag.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Protocol, Sequence, Tuple

from app.reputation.params import DEFAULT_REPUTATION_PARAMS, ReputationParams

Volumes = Dict[str, Dict[str, float]]  # V[seller][buyer] = Wh


class TradeLike(Protocol):
    @property
    def buyer_id(self) -> str: ...

    @property
    def seller_id(self) -> str: ...

    @property
    def qty_wh(self) -> int: ...


@dataclass(frozen=True)
class WindowTrade:
    """A cleared trade tagged with its interval, for sliding-window detection."""

    interval: int
    buyer_id: str
    seller_id: str
    qty_wh: int


@dataclass(frozen=True)
class Flag:
    kind: str  # collusion | collusion_community | anomaly | false_report | energy_imbalance
    severity: str  # low | medium | high
    participant_ids: Tuple[str, ...]
    evidence: Dict[str, Any] = field(default_factory=dict)


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


def _severity(score: float, params: ReputationParams) -> str:
    if score >= params.collusion_high_at:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


# ─── Collusion ─────────────────────────────────────────────────────────────────


def window_trades(trades: Iterable[WindowTrade], current_interval: int, window: int) -> List[WindowTrade]:
    """Trades in the last ``window`` intervals, i.e. (current - window, current]."""
    lo = current_interval - window
    return [t for t in trades if lo < t.interval <= current_interval]


def volume_matrix(trades: Iterable[TradeLike]) -> Volumes:
    v: Volumes = defaultdict(lambda: defaultdict(float))
    for t in trades:
        if t.qty_wh > 0 and t.buyer_id != t.seller_id:
            v[t.seller_id][t.buyer_id] += float(t.qty_wh)
    return {s: dict(row) for s, row in v.items()}


def _participants(v: Volumes) -> List[str]:
    ids = set(v)
    for row in v.values():
        ids.update(row)
    return sorted(ids)


def collusion_scores(trades: Iterable[TradeLike]) -> Dict[str, float]:
    """c_i for every participant appearing in ``trades``."""
    v = volume_matrix(trades)
    ids = _participants(v)

    def vol(i: str, j: str) -> float:
        return v.get(i, {}).get(j, 0.0)

    scores: Dict[str, float] = {}
    for i in ids:
        partners = [j for j in ids if j != i]
        pair = {j: vol(i, j) + vol(j, i) for j in partners}
        total = sum(pair.values())
        pc = max(pair.values()) / total if total > 0 else 0.0
        sold = sum(vol(i, j) for j in partners)
        rr = sum(min(vol(i, j), vol(j, i)) for j in partners) / sold if sold > 0 else 0.0
        scores[i] = round(_clip01(max((pc - 0.5) / 0.5, rr)), 6)
    return scores


def collusion_communities(
    trades: Iterable[TradeLike],
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
    *,
    seed: int = 0,
) -> List[Dict[str, Any]]:
    """Louvain communities (size >= 2) with internal volume ratio > threshold.

    internal ratio = volume between members / all volume touching members.
    Communities covering more than ``community_max_fraction`` of participants are ignored, since
    a small market can collapse into one community that trivially trades with itself.
    """
    import networkx as nx

    v = volume_matrix(trades)
    ids = _participants(v)
    g = nx.Graph()
    g.add_nodes_from(ids)
    for s, row in v.items():
        for b, q in row.items():
            w = g.get_edge_data(s, b, {"weight": 0.0})["weight"] + q
            g.add_edge(s, b, weight=w)
    if g.number_of_edges() == 0:
        return []

    comms = nx.community.louvain_communities(g, weight="weight", seed=seed)
    out: List[Dict[str, Any]] = []
    for c in comms:
        members = sorted(c)
        if len(members) < 2 or len(members) > params.community_max_fraction * len(ids):
            continue
        internal = 0.0
        touching = 0.0
        for a, b, d in g.edges(members, data=True):
            touching += d["weight"]
            if a in c and b in c:
                internal += d["weight"]
        ratio = internal / touching if touching > 0 else 0.0
        if ratio > params.community_internal_ratio:
            out.append({"members": members, "internal_ratio": round(ratio, 6), "volume_wh": internal})
    out.sort(key=lambda d: (-d["internal_ratio"], d["members"]))
    return out


def collusion_flags(
    trades: Sequence[TradeLike],
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
    *,
    seed: int = 0,
) -> Tuple[Dict[str, float], List[Flag]]:
    scores = collusion_scores(trades)
    flags = [
        Flag("collusion", _severity(c, params), (pid,), {"c_i": c})
        for pid, c in sorted(scores.items())
        if c >= params.collusion_flag_at
    ]
    for comm in collusion_communities(trades, params, seed=seed):
        flags.append(
            Flag("collusion_community", "medium", tuple(comm["members"]), dict(comm))
        )
    return scores, flags


# ─── Anomaly detection ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PositionRecord:
    """One submitted position and its outcome, for feature building."""

    participant_id: str
    qty_kwh: float
    limit_price: float
    matched_kwh: float
    p_ref: float


@dataclass(frozen=True)
class ParticipantFeatures:
    participant_id: str
    size_variance: float
    acceptance_rate: float
    volume_share: float
    price_offset: float


def build_features(records: Iterable[PositionRecord], corridor: float) -> List[ParticipantFeatures]:
    """Per-participant features over a window.

    size_variance   population variance of submitted qty_kwh
    acceptance_rate matched / offered
    volume_share    participant matched / market matched
    price_offset    mean (limit_price - p_ref) / corridor, corridor = p_ret - p_fit
    """
    by: Dict[str, List[PositionRecord]] = defaultdict(list)
    for r in records:
        by[r.participant_id].append(r)
    total_matched = sum(r.matched_kwh for rs in by.values() for r in rs)
    out: List[ParticipantFeatures] = []
    for pid in sorted(by):
        rs = by[pid]
        qs = [r.qty_kwh for r in rs]
        mu = sum(qs) / len(qs)
        var = sum((q - mu) ** 2 for q in qs) / len(qs)
        offered = sum(qs)
        matched = sum(r.matched_kwh for r in rs)
        offset = sum(r.limit_price - r.p_ref for r in rs) / len(rs) / corridor if corridor else 0.0
        out.append(
            ParticipantFeatures(
                participant_id=pid,
                size_variance=var,
                acceptance_rate=matched / offered if offered > 0 else 0.0,
                volume_share=matched / total_matched if total_matched > 0 else 0.0,
                price_offset=offset,
            )
        )
    return out


def anomaly_scores(features: Sequence[ParticipantFeatures], *, seed: int = 0) -> Dict[str, float]:
    """a_i in [0, 1] from IsolationForest; < 8 participants -> all 0 (too few to judge)."""
    if len(features) < 8:
        return {f.participant_id: 0.0 for f in features}
    import numpy as np
    from sklearn.ensemble import IsolationForest

    x = np.array(
        [[f.size_variance, f.acceptance_rate, f.volume_share, f.price_offset] for f in features],
        dtype=float,
    )
    model = IsolationForest(n_estimators=200, random_state=seed, n_jobs=1)
    model.fit(x)
    s = -model.score_samples(x)  # Liu et al. anomaly score in (0, 1]
    return {
        f.participant_id: round(_clip01((float(si) - 0.5) / 0.5), 6) for f, si in zip(features, s)
    }


def anomaly_flags(scores: Mapping[str, float], threshold: float = 0.5) -> List[Flag]:
    return [
        Flag("anomaly", "low" if a < 0.8 else "medium", (pid,), {"a_i": a})
        for pid, a in sorted(scores.items())
        if a >= threshold
    ]


# ─── False reports ─────────────────────────────────────────────────────────────


def pv_plausibility(
    reported_kwh: float,
    rated_kw: float,
    clear_sky_factor: float,
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
    *,
    dt_hours: float = 0.25,
) -> float:
    """a_i for one PV report: 0 if plausible, rising to 1 at double the physical maximum."""
    ceiling = max(0.0, rated_kw * _clip01(clear_sky_factor) * dt_hours * params.pv_tolerance)
    if reported_kwh <= ceiling:
        return 0.0
    if ceiling <= 0:
        return 1.0
    return round(_clip01((reported_kwh - ceiling) / ceiling), 6)


@dataclass(frozen=True)
class BalanceResult:
    ok: bool
    participants_net_kwh: float
    substation_net_kwh: float
    mismatch_ratio: float


def energy_balance(
    participant_net_kwh: Mapping[str, float],
    substation_net_kwh: float,
    params: ReputationParams = DEFAULT_REPUTATION_PARAMS,
    *,
    abs_tolerance_kwh: float = 0.1,
) -> BalanceResult:
    """Sum of participant readings on a feeder vs. the substation meter (same sign convention)."""
    total = sum(participant_net_kwh.values())
    diff = abs(total - substation_net_kwh)
    tol = max(abs_tolerance_kwh, params.balance_tolerance * abs(substation_net_kwh))
    denom = max(abs(substation_net_kwh), abs_tolerance_kwh)
    return BalanceResult(
        ok=diff <= tol,
        participants_net_kwh=round(total, 6),
        substation_net_kwh=round(substation_net_kwh, 6),
        mismatch_ratio=round(diff / denom, 6),
    )


def false_report_flags(
    pv_scores: Mapping[str, float],
    balance: BalanceResult | None = None,
    feeder_participants: Sequence[str] = (),
) -> List[Flag]:
    flags = [
        Flag("false_report", "high" if a >= 0.5 else "medium", (pid,), {"a_i": a})
        for pid, a in sorted(pv_scores.items())
        if a > 0
    ]
    if balance is not None and not balance.ok:
        flags.append(
            Flag(
                "energy_imbalance",
                "medium",
                tuple(sorted(feeder_participants)),
                {
                    "participants_net_kwh": balance.participants_net_kwh,
                    "substation_net_kwh": balance.substation_net_kwh,
                    "mismatch_ratio": balance.mismatch_ratio,
                },
            )
        )
    return flags


def honesty_anomaly(anomaly: float = 0.0, false_report: float = 0.0) -> float:
    """Combined a_i fed to reputation (r_hon = 1 - a_i): the worse of the two signals."""
    return _clip01(max(anomaly, false_report))
