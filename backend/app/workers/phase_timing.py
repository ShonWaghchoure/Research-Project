"""Map wall-clock position within an interval to IntervalState."""

from __future__ import annotations

from datetime import datetime, timezone

from app.db.models import IntervalState

# Inclusive-exclusive fractions within [starts_at, ends_at).
PHASE_BOUNDS: tuple[tuple[IntervalState, float, float], ...] = (
    (IntervalState.OPEN, 0.00, 0.25),
    (IntervalState.COMMIT, 0.25, 0.45),
    (IntervalState.REVEAL, 0.45, 0.60),
    (IntervalState.CLEARING, 0.60, 0.72),
    (IntervalState.SETTLED, 0.72, 0.88),
    (IntervalState.METERED, 0.88, 1.0),
)

STATE_ORDER: tuple[IntervalState, ...] = tuple(s for s, _, _ in PHASE_BOUNDS)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def fraction_elapsed(starts_at: datetime, ends_at: datetime, now: datetime) -> float:
    start = _ensure_aware(starts_at)
    end = _ensure_aware(ends_at)
    n = _ensure_aware(now)
    dur = (end - start).total_seconds()
    if dur <= 0:
        return 1.0
    return (n - start).total_seconds() / dur


def expected_state(starts_at: datetime, ends_at: datetime, now: datetime) -> IntervalState:
    """Return the phase the interval should be in at ``now``.

    At or after ``ends_at``, returns METERED (terminal for this interval).
    """
    frac = fraction_elapsed(starts_at, ends_at, now)
    if frac < 0:
        return IntervalState.OPEN
    if frac >= 1.0:
        return IntervalState.METERED
    for state, lo, hi in PHASE_BOUNDS:
        if lo <= frac < hi:
            return state
    return IntervalState.METERED


def commit_deadline_ts(starts_at: datetime, ends_at: datetime) -> int:
    """Unix time when commits close (end of COMMIT = 0.45)."""
    start = _ensure_aware(starts_at)
    end = _ensure_aware(ends_at)
    dur = (end - start).total_seconds()
    return int((start.timestamp() + 0.45 * dur))


def reveal_deadline_ts(starts_at: datetime, ends_at: datetime) -> int:
    """Unix time when reveal closes (end of REVEAL = 0.60)."""
    start = _ensure_aware(starts_at)
    end = _ensure_aware(ends_at)
    dur = (end - start).total_seconds()
    return int((start.timestamp() + 0.60 * dur))


def next_state(current: IntervalState) -> IntervalState | None:
    try:
        idx = STATE_ORDER.index(current)
    except ValueError:
        return None
    if idx + 1 >= len(STATE_ORDER):
        return None
    return STATE_ORDER[idx + 1]
