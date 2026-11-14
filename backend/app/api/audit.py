"""Public audit endpoints: published inputs/results and deterministic re-run."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api import audit_service
from app.api.deps import require_operator
from app.db.deps import get_db
from app.db.models import Interval, User
from app.schemas.audit import AuditReport, AuditRerunResponse

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/{interval_id}", response_model=AuditReport)
def get_audit_report(
    interval_id: int,
    db: Session = Depends(get_db),
) -> AuditReport:
    iv = db.get(Interval, interval_id)
    if iv is None:
        raise HTTPException(status_code=404, detail="interval not found")
    return AuditReport.model_validate(audit_service.get_audit(db, iv))


@router.post("/{interval_id}/rerun", response_model=AuditRerunResponse)
def rerun_audit(
    interval_id: int,
    _: User = Depends(require_operator),
    db: Session = Depends(get_db),
) -> AuditRerunResponse:
    iv = db.get(Interval, interval_id)
    if iv is None:
        raise HTTPException(status_code=404, detail="interval not found")
    try:
        data = audit_service.rerun_audit(db, iv)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuditRerunResponse.model_validate(data)
