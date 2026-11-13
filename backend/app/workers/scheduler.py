"""APScheduler entrypoint for market workers."""

from __future__ import annotations

import structlog
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.workers import bots, clock, listener

logger = structlog.get_logger(__name__)

_scheduler: BackgroundScheduler | None = None


def _job() -> None:
    clock.tick()
    bots.tick()
    listener.tick()


def start_scheduler() -> BackgroundScheduler | None:
    global _scheduler
    if settings.testing:
        logger.info("scheduler_skipped_testing")
        return None
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    sched = BackgroundScheduler(timezone="UTC")
    sched.add_job(_job, "interval", seconds=2, id="market_tick", max_instances=1, coalesce=True)
    sched.start()
    _scheduler = sched
    logger.info("scheduler_started", demo_mode=settings.DEMO_MODE)
    return sched


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        try:
            _scheduler.shutdown(wait=False)
        except Exception as exc:
            logger.warning("scheduler_stop_failed", error=str(exc))
        _scheduler = None
        logger.info("scheduler_stopped")
