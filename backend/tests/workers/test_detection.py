from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import (
    Interval,
    IntervalState,
    Participant,
    ParticipantType,
    Position,
    PositionSide,
    ReputationEvent,
    Trade,
    User,
    UserRole,
)
from app.workers import detection


def _setup_window(db: Session, n_intervals: int = 12) -> Interval:
    users = []
    parts = []
    for i in range(4):
        u = User(
            address="0x" + f"{i + 1:02x}" * 20,
            role=UserRole.participant,
            nonce_used=True,
        )
        users.append(u)
    db.add_all(users)
    db.flush()
    for i, u in enumerate(users):
        p = Participant(
            user_id=u.id,
            type=ParticipantType.prosumer if i % 2 else ParticipantType.consumer,
            feeder_node_id="n1",
            pv_capacity_w=3000 if i % 2 else 0,
        )
        parts.append(p)
    db.add_all(parts)
    db.flush()

    last = None
    for t in range(1, n_intervals + 1):
        iv = Interval(
            state=IntervalState.METERED,
            starts_at=datetime.now(timezone.utc),
            ends_at=datetime.now(timezone.utc),
            p_ref_paise=550,
            delivery_root="0x" + "aa" * 32,
            result_hash="0x" + "bb" * 32,
            input_root="0x" + "cc" * 32,
        )
        db.add(iv)
        db.flush()
        # Force id sequence alignment for cadence checks when autoincrement drifts.
        # SQLite/Postgres autoincrement should give 1..n on empty tables in tests.
        last = iv
        a, b = parts[0], parts[1]
        db.add(
            Trade(
                interval_id=iv.id,
                buyer_id=a.id,
                seller_id=b.id,
                qty_wh=1000,
                price_paise=550,
            )
        )
        db.add(
            Trade(
                interval_id=iv.id,
                buyer_id=b.id,
                seller_id=a.id,
                qty_wh=1000,
                price_paise=550,
            )
        )
        for p in parts[:2]:
            db.add(
                Position(
                    participant_id=p.id,
                    interval_id=iv.id,
                    side=PositionSide.buy if p.id == a.id else PositionSide.sell,
                    qty_wh=1000,
                    limit_price_paise=550,
                    revealed=True,
                )
            )
    db.flush()
    assert last is not None
    return last


def test_detection_writes_scores_and_flags(seeded_db: Session):
    iv = _setup_window(seeded_db, n_intervals=12)
    # Ensure cadence: detection runs when interval.id % 12 == 0.
    # If autoincrement did not start at 1, force by running only when should_run.
    if not detection.should_run(iv.id):
        # Nudge: create intervals until cadence hits.
        while not detection.should_run(iv.id):
            nxt = Interval(
                state=IntervalState.METERED,
                starts_at=datetime.now(timezone.utc),
                ends_at=datetime.now(timezone.utc),
                delivery_root="0x" + "aa" * 32,
                result_hash="0x" + "bb" * 32,
                p_ref_paise=550,
            )
            seeded_db.add(nxt)
            seeded_db.flush()
            iv = nxt

    result = detection.run(seeded_db, iv)
    assert result["skipped"] is False
    assert result["scores"] >= 1

    events = (
        seeded_db.query(ReputationEvent)
        .filter(
            ReputationEvent.interval_id == iv.id,
            ReputationEvent.event_type == detection.DETECTION_EVENT,
        )
        .all()
    )
    assert len(events) >= 1
    c_i, a_i = detection.latest_detection_scores(seeded_db, events[0].participant_id)
    assert 0.0 <= c_i <= 1.0
    assert 0.0 <= a_i <= 1.0

    # Idempotent
    again = detection.run(seeded_db, iv)
    assert again["skipped"] is True
