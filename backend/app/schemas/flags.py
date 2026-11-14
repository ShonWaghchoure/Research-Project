from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class FlagOut(BaseModel):
    id: int
    participant_id: Optional[int] = None
    interval_id: Optional[int] = None
    kind: str
    severity: str
    status: str
    detail: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None

    model_config = {"from_attributes": True}


class FlagResolve(BaseModel):
    status: Literal["resolved", "dismissed"]
    note: Optional[str] = None
