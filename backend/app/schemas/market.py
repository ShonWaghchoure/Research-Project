"""Pydantic schemas for market / interval / reputation APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class IntervalOut(BaseModel):
    id: int
    state: str
    starts_at: datetime
    ends_at: datetime
    p_ref_paise: Optional[int] = None
    sdr: Optional[float] = None
    input_root: Optional[str] = None
    result_hash: Optional[str] = None
    delivery_root: Optional[str] = None
    engine_version: Optional[str] = None


#: Hard ceiling (1 MWh, ₹1000/kWh): keeps every value inside the int32 DB columns.
MAX_POSITION_WH = 1_000_000
MAX_PRICE_PAISE = 100_000


class PositionCreate(BaseModel):
    side: Literal["buy", "sell"]
    qty_wh: int = Field(..., gt=0, le=MAX_POSITION_WH)
    limit_price_paise: int = Field(..., gt=0, le=MAX_PRICE_PAISE)
    deadline: Optional[int] = Field(None, ge=0, le=2**31 - 1)  # unix s; default interval end
    # The browser generates the salt (docs/DECISIONS.md, Phase 8 #4) so it can check the
    # commit hash itself. When omitted, the server generates one.
    salt: Optional[str] = Field(None, pattern=r"^0x[0-9a-fA-F]{64}$")


class CommitData(BaseModel):
    position_id: int
    #: Same as position_id; the frontend's Position type uses `id`.
    id: int
    interval_id: int
    commit_hash: str
    salt: str
    side: str
    qty_wh: int
    limit_price_paise: int
    deadline: int
    participant: str


class PositionOut(BaseModel):
    id: int
    interval_id: int
    side: str
    qty_wh: int
    limit_price_paise: int
    commit_hash: Optional[str] = None
    revealed: bool
    created_at: datetime


class RevealIn(BaseModel):
    """Optional salt confirmation; server already stores salt privately."""

    salt: Optional[str] = None


class TradeOut(BaseModel):
    id: int
    interval_id: int
    buyer_id: int
    seller_id: int
    qty_wh: int
    price_paise: int
    created_at: datetime


class OrderbookLevel(BaseModel):
    side: str
    total_qty_wh: int
    count: int


class OrderbookOut(BaseModel):
    interval_id: int
    levels: list[OrderbookLevel]


class ReputationOut(BaseModel):
    address: str
    interval_id: Optional[int] = None
    score_bp: int
    evidence_count: int
    alpha: float
    beta: float
    tier: str
    leaf_hash: Optional[str] = None


class ReputationHistoryOut(BaseModel):
    address: str
    history: list[ReputationOut]


class ReputationProofOut(BaseModel):
    address: str
    interval_id: int
    score_bp: int
    evidence_count: int
    leaf_hash: str
    proof: list[str]
    root: str
