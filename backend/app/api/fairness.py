"""Fairness metric history for the fairness page."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.deps import get_db
from app.db.models import FairnessMetric, Interval
from app.schemas.market import FairnessHistoryOut, FairnessMetricOut

router = APIRouter(tags=["fairness"])


@router.get("/fairness/history", response_model=FairnessHistoryOut)
def fairness_history(
    baseline: Literal["B2", "B3"] = Query("B3"),
    limit: int = Query(96, ge=1, le=500),
    db: Session = Depends(get_db),
) -> FairnessHistoryOut:
    rows = (
        db.query(FairnessMetric, Interval)
        .join(Interval, Interval.id == FairnessMetric.interval_id)
        .order_by(FairnessMetric.interval_id.desc())
        .limit(limit)
        .all()
    )
    metrics: list[FairnessMetricOut] = []
    for row, interval in reversed(rows):
        baseline_metrics = row.metrics.get(baseline, {})
        if not isinstance(baseline_metrics, dict):
            continue
        required = (
            "jain",
            "gini",
            "hhi",
            "small_actor_parity",
            "price_impact",
            "welfare_efficiency",
        )
        if not all(key in baseline_metrics for key in required):
            continue
        metrics.append(
            FairnessMetricOut(
                interval_id=interval.id,
                ends_at=interval.ends_at,
                baseline=baseline,
                **{key: float(baseline_metrics[key]) for key in required},
            )
        )
    return FairnessHistoryOut(baseline=baseline, metrics=metrics)
