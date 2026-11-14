"""Clear live-market rows so a fresh Hardhat deploy can open interval 1 again.

Usage: python -m app.db.reset_market

Keeps users, participants, feeder, and config. Wipes intervals and every
table keyed by interval_id, plus chain ``transactions`` (idempotency).
"""

from __future__ import annotations

from sqlalchemy import text

from app.db.session import SessionLocal

# Order matters for FKs: children before parents.
_TABLES = (
    "deliveries",
    "meter_readings",
    "reputation_events",
    "reputation_scores",
    "fairness_metrics",
    "flags",
    "trades",
    "positions",
    "transactions",
    "intervals",
)


def reset_market() -> dict[str, int]:
    db = SessionLocal()
    cleared: dict[str, int] = {}
    try:
        for table in _TABLES:
            res = db.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE"))
            # rowcount is often -1 for TRUNCATE; count afterwards if needed
            cleared[table] = res.rowcount if res.rowcount and res.rowcount > 0 else 0
        db.commit()
        return cleared
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    cleared = reset_market()
    print("market reset:", cleared)


if __name__ == "__main__":
    main()
