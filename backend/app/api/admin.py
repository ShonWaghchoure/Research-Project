"""Admin config endpoints with audit logging."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import require_admin
from app.core.config_store import get_config_map, update_config
from app.db.deps import get_db
from app.db.models import AuditLog, User
from app.schemas.config import ConfigMap, ConfigUpdate

router = APIRouter(prefix="/admin", tags=["admin"])


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
