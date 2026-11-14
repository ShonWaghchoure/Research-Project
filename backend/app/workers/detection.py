"""Sliding-window collusion / Sybil / anomaly detection for the live market.

Runs every ``DETECTION_EVERY`` metered intervals. Writes Flag rows for the admin
queue and ReputationEvent(detection) rows so the reputation worker can feed
c_i and a_i into Evidence. Flags never auto-ban anyone.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import structlog
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.core.config_store import load_market_params
from app.db.models import (
    Flag,
    FlagSeverity,
    FlagStatus,
    Interval,
    IntervalState,
    MeterReading,
    Participant,
    Position,
    ReputationEvent,
    Trade,
)
from app.reputation.params import DEFAULT_REPUTATION_PARAMS
from app.reputation.sybil import (
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
from app.workers.pubsub import publish_flags

logger = structlog.get_logger(__name__)

DETECTION_EVERY = 12
DETECTION_EVENT = "detection"


def _severity(s: str) -> FlagSeverity:
    try:
        return FlagSeverity(s)
    except ValueError:
        return FlagSeverity.medium


def _pid_int(raw: str) -> int | None:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def should_run(interval_id: int) -> bool:
    return interval_id > 0 and interval_id % DETECTION_EVERY == 0


def latest_detection_scores(db: Session, participant_id: int) -> tuple[float, float]:
    """Return (c_i, a_i) from the most recent detection event, else (0, 0)."""
    row = (
        db.query(ReputationEvent)
        .filter(
            ReputationEvent.participant_id == participant_id,
            ReputationEvent.event_type == DETECTION_EVENT,
        )
        .order_by(desc(ReputationEvent.interval_id), desc(ReputationEvent.id))
        .first()
    )
    if row is None or not isinstance(row.payload, dict):
        return 0.0, 0.0
    return float(row.payload.get("c_i", 0.0) or 0.0), float(row.payload.get("a_i", 0.0) or 0.0)


def run(db: Session, interval: Interval) -> dict[str, Any]:
    """Run detectors over the sliding window ending at ``interval``. Idempotent per interval."""
    if not should_run(interval.id):
        return {"skipped": True, "reason": "not_cadence"}

    already = (
        db.query(ReputationEvent)
        .filter(
            ReputationEvent.interval_id == interval.id,
            ReputationEvent.event_type == DETECTION_EVENT,
        )
        .count()
    )
    if already > 0:
        logger.info("detection_skip_already_done", interval_id=interval.id)
        return {"skipped": True, "reason": "already_done"}

    rparams = DEFAULT_REPUTATION_PARAMS
    params = load_market_params(db)
    corridor = float(params.p_ret - params.p_fit)
    window_lo = max(0, interval.id - rparams.collusion_window_intervals)

    trades = (
        db.query(Trade)
        .filter(Trade.interval_id > window_lo, Trade.interval_id <= interval.id)
        .all()
    )
    window = [
        WindowTrade(
            interval=int(t.interval_id),
            buyer_id=str(t.buyer_id),
            seller_id=str(t.seller_id),
            qty_wh=int(t.qty_wh),
        )
        for t in trades
    ]

    # Position records for IsolationForest features (windowed).
    positions = (
        db.query(Position)
        .filter(
            Position.interval_id > window_lo,
            Position.interval_id <= interval.id,
            Position.revealed.is_(True),
        )
        .all()
    )
    intervals_in_window = {
        iv.id: iv
        for iv in db.query(Interval)
        .filter(Interval.id > window_lo, Interval.id <= interval.id)
        .all()
    }
    matched: dict[tuple[int, int], float] = defaultdict(float)
    for t in trades:
        matched[(t.interval_id, t.buyer_id)] += t.qty_wh / 1000.0
        matched[(t.interval_id, t.seller_id)] += t.qty_wh / 1000.0

    records: list[PositionRecord] = []
    for pos in positions:
        iv = intervals_in_window.get(pos.interval_id)
        p_ref = float(iv.p_ref_paise) if iv and iv.p_ref_paise is not None else float(params.p_fit)
        records.append(
            PositionRecord(
                participant_id=str(pos.participant_id),
                qty_kwh=pos.qty_wh / 1000.0,
                limit_price=float(pos.limit_price_paise),
                matched_kwh=matched.get((pos.interval_id, pos.participant_id), 0.0),
                p_ref=p_ref,
            )
        )

    c_scores, cflags = collusion_flags(window, rparams, seed=interval.id)
    a_scores = anomaly_scores(build_features(records, corridor), seed=interval.id)
    flags = list(cflags) + anomaly_flags(a_scores)

    # PV plausibility over the last DETECTION_EVERY intervals of meter readings.
    recent_lo = max(0, interval.id - DETECTION_EVERY)
    readings = (
        db.query(MeterReading)
        .filter(MeterReading.interval_id > recent_lo, MeterReading.interval_id <= interval.id)
        .all()
    )
    pv_by_pid: dict[str, float] = {}
    for mr in readings:
        part = db.get(Participant, mr.participant_id)
        if part is None or part.pv_capacity_w <= 0:
            continue
        rated_kw = part.pv_capacity_w / 1000.0
        # Export is treated as reported PV production for the plausibility check.
        # clear_sky_factor unknown in live path → use 1.0 (most permissive ceiling).
        reported_kwh = mr.export_wh / 1000.0
        score = pv_plausibility(reported_kwh, rated_kw, clear_sky_factor=1.0, params=rparams)
        if score > 0:
            prev = pv_by_pid.get(str(mr.participant_id), 0.0)
            pv_by_pid[str(mr.participant_id)] = max(prev, score)
    flags += false_report_flags(pv_by_pid)

    # Persist per-participant detection scores (persist until next pass).
    participant_ids = {p.id for p in db.query(Participant).filter(Participant.active.is_(True)).all()}
    all_pids = set(c_scores) | set(a_scores) | set(pv_by_pid) | {str(i) for i in participant_ids}
    written_scores = 0
    for pid_s in sorted(all_pids):
        pid = _pid_int(pid_s)
        if pid is None or pid not in participant_ids:
            continue
        c_i = float(c_scores.get(pid_s, 0.0))
        a_i = honesty_anomaly(a_scores.get(pid_s, 0.0), pv_by_pid.get(pid_s, 0.0))
        db.add(
            ReputationEvent(
                interval_id=interval.id,
                participant_id=pid,
                event_type=DETECTION_EVENT,
                payload={"c_i": c_i, "a_i": a_i},
            )
        )
        written_scores += 1

    # Persist flags (never auto-ban).
    new_flags = 0
    for fl in flags:
        detail: dict[str, Any] = dict(fl.evidence)
        detail["participant_ids"] = list(fl.participant_ids)
        primary = _pid_int(fl.participant_ids[0]) if fl.participant_ids else None
        if primary is not None and primary not in participant_ids:
            primary = None
        db.add(
            Flag(
                participant_id=primary,
                interval_id=interval.id,
                kind=fl.kind,
                severity=_severity(fl.severity),
                status=FlagStatus.open,
                detail=detail,
            )
        )
        new_flags += 1

    db.commit()
    publish_flags(
        {
            "interval_id": interval.id,
            "flags": new_flags,
            "scores": written_scores,
        }
    )
    logger.info(
        "detection_done",
        interval_id=interval.id,
        flags=new_flags,
        scores=written_scores,
        trades=len(window),
    )
    return {"skipped": False, "flags": new_flags, "scores": written_scores}


def maybe_run_after_metered(db: Session, interval: Interval) -> None:
    """Hook from the clock: only after a fully metered interval on the cadence."""
    if interval.state != IntervalState.METERED:
        return
    if not interval.delivery_root:
        return
    if not should_run(interval.id):
        return
    try:
        run(db, interval)
    except Exception:
        logger.exception("detection_failed", interval_id=interval.id)
        try:
            db.rollback()
        except Exception:
            pass
