from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ConfigMap(BaseModel):
    """All market config keys as a flat map."""

    values: dict[str, Any] = Field(default_factory=dict)


class ConfigUpdate(BaseModel):
    values: dict[str, Any] = Field(..., min_length=1)
