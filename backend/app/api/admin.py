"""Admin endpoints: config, flags, attacks, simulation control, audit log."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api import attacks_service
from app.api.deps import require_admin
from app.core.config_store import (
    PARAM_KEYS,
    default_config_map,
    get_config_map,
    update_config,
    validate_config,
)
from app.db.deps import get_db
from app.db.models import (
    AttackRun,
    AuditLog,
    Flag,
    FlagStatus,
    User,
)
from app.schemas.attacks import AttackRunRequest, AttackRunResult, AttackSeriesPoint
from app.schemas.config import ConfigMap, ConfigUpdate
from app.schemas.flags import FlagOut, FlagResolve
from app.workers import sim_control

router = APIRouter(prefix="/admin", tags=["admin"])


# ── Config ────────────────────────────────────────────────────────────────────


@router.get("/config", response_model=ConfigMap)
def get_config(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConfigMap:
    return ConfigMap(values=get_config_map(db))


@router.put("/config", response_model=ConfigMap)
def put_config(
    body: ConfigUpdate,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ConfigMap:
    current = {k: v for k, v in get_config_map(db).items() if k in PARAM_KEYS}
    merged = {**default_config_map(), **current, **body.values}
    problems = validate_config(merged)
    if problems:
        raise HTTPException(status_code=422, detail=problems)
    before, after = update_config(db, body.values, updated_by=user.id)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="config.update",
            resource_type="config",
            resource_id=",".join(sorted(after.keys())),
            before=before,
            after=after,
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    return ConfigMap(values=get_config_map(db))


# ── Flags ─────────────────────────────────────────────────────────────────────


@router.get("/flags", response_model=list[FlagOut])
def list_flags(
    status: Optional[str] = Query("open"),
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[FlagOut]:
    q = db.query(Flag).order_by(desc(Flag.id))
    if status:
        try:
            st = FlagStatus(status)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"invalid status: {status}") from exc
        q = q.filter(Flag.status == st)
    rows = q.limit(limit).all()
    return [FlagOut.model_validate(r) for r in rows]


@router.post("/flags/{flag_id}/resolve", response_model=FlagOut)
def resolve_flag(
    flag_id: int,
    body: FlagResolve,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> FlagOut:
    flag = db.get(Flag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="flag not found")
    if flag.status != FlagStatus.open:
        raise HTTPException(status_code=400, detail="flag already resolved")

    before = {"status": flag.status.value}
    flag.status = FlagStatus(body.status)
    flag.resolved_at = datetime.now(timezone.utc)
    flag.resolved_by = user.id
    if body.note:
        detail = dict(flag.detail or {})
        detail["resolve_note"] = body.note
        flag.detail = detail

    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="flag.resolve",
            resource_type="flag",
            resource_id=str(flag.id),
            before=before,
            after={"status": flag.status.value, "note": body.note},
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    db.refresh(flag)
    return FlagOut.model_validate(flag)


# ── Attack lab ────────────────────────────────────────────────────────────────


@router.post("/attacks/run", response_model=AttackRunResult)
def run_attack(
    body: AttackRunRequest,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AttackRunResult:
    defenses = body.defenses == "on"
    try:
        payload = attacks_service.run_attack(body.scenario, body.params, defenses)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"attack run failed: {exc}") from exc

    row = AttackRun(
        scenario=body.scenario,
        params=payload["params_resolved"],
        defenses=defenses,
        status="completed",
        result={
            "summary": payload["summary"],
            "series": payload["series"],
            "attacker_profit_paise": payload["attacker_profit_paise"],
            "plain_summary": payload["plain_summary"],
        },
        created_by=user.id,
    )
    db.add(row)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="attack.run",
            resource_type="attack_run",
            resource_id=body.scenario,
            before=None,
            after={"scenario": body.scenario, "defenses": defenses, "params": payload["params_resolved"]},
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    db.refresh(row)

    return AttackRunResult(
        id=row.id,
        scenario=row.scenario,
        defenses=row.defenses,
        params=row.params,
        status=row.status,
        summary=payload["summary"],
        series=[AttackSeriesPoint.model_validate(p) for p in payload["series"]],
        attacker_profit_paise=payload["attacker_profit_paise"],
        plain_summary=payload["plain_summary"],
        created_at=row.created_at,
    )


# ── Simulation control ────────────────────────────────────────────────────────


class SimSpeedUpdate(BaseModel):
    interval_seconds: int = Field(..., ge=5, le=3600)


@router.get("/simulation")
def get_simulation(
    _: User = Depends(require_admin),
) -> dict:
    return sim_control.get_state()


@router.post("/simulation/start")
def start_simulation(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    state = sim_control.start()
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="simulation.start",
            resource_type="simulation",
            resource_id="live",
            before=None,
            after=state,
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    return state


@router.post("/simulation/stop")
def stop_simulation(
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    state = sim_control.stop()
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="simulation.stop",
            resource_type="simulation",
            resource_id="live",
            before=None,
            after=state,
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    return state


@router.put("/simulation/speed")
def set_simulation_speed(
    body: SimSpeedUpdate,
    request: Request,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> dict:
    before = sim_control.get_state()
    try:
        state = sim_control.set_speed(body.interval_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="simulation.speed",
            resource_type="simulation",
            resource_id="live",
            before=before,
            after=state,
            ip=request.client.host if request.client else None,
        )
    )
    db.commit()
    return state


# ── Audit log table ───────────────────────────────────────────────────────────


class AuditLogOut(BaseModel):
    id: int
    actor_user_id: Optional[int] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    before: Optional[dict] = None
    after: Optional[dict] = None
    ip: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/audit-log", response_model=list[AuditLogOut])
def list_audit_log(
    limit: int = Query(100, ge=1, le=500),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AuditLogOut]:
    rows = db.query(AuditLog).order_by(desc(AuditLog.id)).limit(limit).all()
    return [AuditLogOut.model_validate(r) for r in rows]
