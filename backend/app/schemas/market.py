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
    commit_deadline: datetime
    reveal_deadline: datetime
    p_ref_paise: Optional[int] = None
    prev_p_ref_paise: Optional[int] = None
    sdr: Optional[float] = None
    active_participants: int
    input_root: Optional[str] = None
    result_hash: Optional[str] = None
    delivery_root: Optional[str] = None
    engine_version: Optional[str] = None


class PricePointOut(BaseModel):
    interval_id: int
    ends_at: datetime
    p_ref_paise: int
    sdr: float


class PositionCreate(BaseModel):
    interval_id: int = Field(..., gt=0)
    side: Literal["buy", "sell"]
    qty_wh: int = Field(..., gt=0, le=2**64 - 1)
    limit_price_paise: int = Field(..., ge=300, le=800)
    deadline: Optional[int] = Field(None, ge=0, le=2**64 - 1)
    salt: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")


class CommitData(BaseModel):
    position_id: int
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
    deadline: int
    salt: str
    commit_hash: Optional[str] = None
    committed_tx: Optional[str] = None
    revealed: bool
    created_at: datetime


class RevealIn(BaseModel):
    """Commit transaction hash submitted when the owner reveals."""

    tx_hash: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")


class CommitConfirmationIn(BaseModel):
    tx_hash: str = Field(..., pattern=r"^0x[0-9a-fA-F]{64}$")


class TradeOut(BaseModel):
    id: int
    interval_id: int
    side: Optional[Literal["buy", "sell"]] = None
    buyer: str
    seller: str
    qty_wh: int
    price_paise: int
    status: Literal["cleared", "settled", "delivered", "shortfall"]
    created_at: datetime


class OrderbookLevel(BaseModel):
    price_paise: int
    qty_wh: int


class OrderbookOut(BaseModel):
    interval_id: int
    supply_wh: int
    demand_wh: int
    bids: list[OrderbookLevel]
    asks: list[OrderbookLevel]


class ReputationComponents(BaseModel):
    delivery: float
    reveal: float
    honesty: float
    collusion: float


class ReputationHistoryPointOut(BaseModel):
    interval_id: int
    ends_at: datetime
    score: float
    score_bp: int
    tier: str
    evidence_count: int
    components: ReputationComponents


class ReputationOut(ReputationHistoryPointOut):
    address: str
    alpha: float
    beta: float
    intervals_to_trusted: Optional[int] = None
    volume_cap_kwh: float
    updated_at: datetime
    leaf_hash: Optional[str] = None


class ReputationHistoryOut(BaseModel):
    address: str
    history: list[ReputationHistoryPointOut]


class ReputationProofOut(BaseModel):
    address: str
    interval_id: int
    score_bp: int
    evidence_count: int
    leaf_hash: str
    proof: list[str]
    root: str


class GridLineOut(BaseModel):
    id: str
    from_node: str
    to_node: str
    capacity_kw: float
    loading_pct: float


class GridParticipantOut(BaseModel):
    address: str
    kind: str


class GridNodeOut(BaseModel):
    id: str
    label: str
    kind: str
    participants: list[GridParticipantOut]


class GridStatusOut(BaseModel):
    interval_id: int
    lines: list[GridLineOut]
    congested_line_ids: list[str]
    max_loading_pct: float
    p2p_share_pct: float
    nodes: list[GridNodeOut]


class FairnessMetricOut(BaseModel):
    interval_id: int
    ends_at: datetime
    baseline: Literal["B2", "B3"]
    jain: float
    gini: float
    hhi: float
    small_actor_parity: float
    price_impact: float
    welfare_efficiency: float


class FairnessHistoryOut(BaseModel):
    baseline: Literal["B2", "B3"]
    metrics: list[FairnessMetricOut]
