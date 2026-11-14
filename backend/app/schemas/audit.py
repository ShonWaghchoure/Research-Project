from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class AuditPosition(BaseModel):
    participant_id: int
    side: str
    qty_wh: int
    limit_price_paise: int
    revealed: bool


class AuditTrade(BaseModel):
    buyer_id: int
    seller_id: int
    qty_wh: int
    price_paise: int


class HashTriple(BaseModel):
    stored: Optional[str] = None
    recomputed: Optional[str] = None
    on_chain: Optional[str] = None
    stored_matches_recomputed: Optional[bool] = None
    stored_matches_on_chain: Optional[bool] = None
    recomputed_matches_on_chain: Optional[bool] = None


class AuditReport(BaseModel):
    interval_id: int
    state: str
    engine_version: Optional[str] = None
    p_ref_paise: Optional[int] = None
    sdr: Optional[float] = None
    positions: list[AuditPosition] = Field(default_factory=list)
    trades: list[AuditTrade] = Field(default_factory=list)
    input_root: HashTriple
    result_hash: HashTriple
    merkle_leaves: list[dict[str, Any]] = Field(default_factory=list)
    explorer: dict[str, Optional[str]] = Field(default_factory=dict)


class AuditRerunResponse(BaseModel):
    interval_id: int
    engine_version_stored: Optional[str] = None
    engine_version_now: str
    input_root: HashTriple
    result_hash: HashTriple
    match: bool
    note: str = ""
