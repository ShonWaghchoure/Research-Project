from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

ATTACK_SCENARIOS = (
    "sybil_farm",
    "collusion_ring",
    "price_manipulation",
    "false_reports",
    "defect_after_trust",
)


class AttackRunRequest(BaseModel):
    scenario: Literal[
        "sybil_farm",
        "collusion_ring",
        "price_manipulation",
        "false_reports",
        "defect_after_trust",
    ]
    params: dict[str, Any] = Field(default_factory=dict)
    defenses: Literal["on", "off"] = "on"


class AttackSeriesPoint(BaseModel):
    interval: int
    p_ref: Optional[float] = None
    sdr: Optional[float] = None
    jain: Optional[float] = None
    gini: Optional[float] = None
    hhi: Optional[float] = None
    mean_reputation: Optional[float] = None


class AttackRunResult(BaseModel):
    id: int
    scenario: str
    defenses: bool
    params: dict[str, Any]
    status: str
    summary: dict[str, Any]
    series: list[AttackSeriesPoint] = Field(default_factory=list)
    attacker_profit_paise: float = 0.0
    plain_summary: str = ""
    created_at: datetime
