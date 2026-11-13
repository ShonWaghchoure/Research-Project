"""SQLAlchemy 2 models for the P2P energy market (Phase 6)."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class UserRole(str, enum.Enum):
    participant = "participant"
    operator = "operator"
    admin = "admin"


class ParticipantType(str, enum.Enum):
    consumer = "consumer"
    prosumer = "prosumer"
    ev = "ev"


class IntervalState(str, enum.Enum):
    OPEN = "OPEN"
    COMMIT = "COMMIT"
    REVEAL = "REVEAL"
    CLEARING = "CLEARING"
    SETTLED = "SETTLED"
    METERED = "METERED"


class PositionSide(str, enum.Enum):
    buy = "buy"
    sell = "sell"


class TxStatus(str, enum.Enum):
    pending = "pending"
    submitted = "submitted"
    confirmed = "confirmed"
    failed = "failed"


class FlagSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


class FlagStatus(str, enum.Enum):
    open = "open"
    resolved = "resolved"
    dismissed = "dismissed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        nullable=False,
        default=UserRole.participant,
    )
    nonce: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    nonce_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    participant: Mapped[Optional["Participant"]] = relationship(
        back_populates="user", uselist=False
    )


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    type: Mapped[ParticipantType] = mapped_column(
        Enum(ParticipantType, name="participant_type", native_enum=False),
        nullable=False,
    )
    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    feeder_node_id: Mapped[str] = mapped_column(
        ForeignKey("feeder_nodes.id"), nullable=False, index=True
    )
    # Capacities stored as integer base units: W and Wh (API accepts kW / kWh).
    pv_capacity_w: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    battery_wh: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ev_battery_wh: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ev_max_power_w: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ev_v2g: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="participant")
    ev_state: Mapped[Optional["EvState"]] = relationship(back_populates="participant", uselist=False)


class EvState(Base):
    __tablename__ = "ev_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(
        ForeignKey("participants.id"), unique=True, nullable=False
    )
    soc_wh: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_wh: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deadline_interval_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("intervals.id"), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    participant: Mapped[Participant] = relationship(back_populates="ev_state")


class FeederNode(Base):
    __tablename__ = "feeder_nodes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    is_root: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class FeederLine(Base):
    __tablename__ = "feeder_lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    from_node_id: Mapped[str] = mapped_column(ForeignKey("feeder_nodes.id"), nullable=False)
    to_node_id: Mapped[str] = mapped_column(ForeignKey("feeder_nodes.id"), nullable=False)
    capacity_w: Mapped[int] = mapped_column(Integer, nullable=False)  # W (= kW * 1000)


class Interval(Base):
    __tablename__ = "intervals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state: Mapped[IntervalState] = mapped_column(
        Enum(IntervalState, name="interval_state", native_enum=False),
        nullable=False,
        default=IntervalState.OPEN,
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    p_ref_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sdr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    input_root: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    result_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    delivery_root: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    engine_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint("participant_id", "interval_id", name="uq_position_participant_interval"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    interval_id: Mapped[int] = mapped_column(ForeignKey("intervals.id"), nullable=False, index=True)
    side: Mapped[PositionSide] = mapped_column(
        Enum(PositionSide, name="position_side", native_enum=False), nullable=False
    )
    qty_wh: Mapped[int] = mapped_column(Integer, nullable=False)
    limit_price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    commit_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    salt: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    revealed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Trade(Base):
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interval_id: Mapped[int] = mapped_column(ForeignKey("intervals.id"), nullable=False, index=True)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    seller_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    qty_wh: Mapped[int] = mapped_column(Integer, nullable=False)
    price_paise: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MeterReading(Base):
    __tablename__ = "meter_readings"
    __table_args__ = (
        UniqueConstraint("participant_id", "interval_id", name="uq_meter_participant_interval"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interval_id: Mapped[int] = mapped_column(ForeignKey("intervals.id"), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    import_wh: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    export_wh: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    signature: Mapped[Optional[str]] = mapped_column(String(132), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interval_id: Mapped[int] = mapped_column(ForeignKey("intervals.id"), nullable=False, index=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"), nullable=False)
    delivered_wh: Mapped[int] = mapped_column(Integer, nullable=False)
    shortfall_wh: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class ReputationEvent(Base):
    __tablename__ = "reputation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interval_id: Mapped[int] = mapped_column(ForeignKey("intervals.id"), nullable=False, index=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReputationScore(Base):
    __tablename__ = "reputation_scores"
    __table_args__ = (
        UniqueConstraint("participant_id", "interval_id", name="uq_rep_score_participant_interval"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(ForeignKey("participants.id"), nullable=False)
    interval_id: Mapped[int] = mapped_column(ForeignKey("intervals.id"), nullable=False, index=True)
    score_bp: Mapped[int] = mapped_column(Integer, nullable=False)  # basis points
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    alpha: Mapped[float] = mapped_column(Float, nullable=False)
    beta: Mapped[float] = mapped_column(Float, nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False)
    leaf_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FairnessMetric(Base):
    __tablename__ = "fairness_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    interval_id: Mapped[int] = mapped_column(
        ForeignKey("intervals.id"), unique=True, nullable=False
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Flag(Base):
    __tablename__ = "flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    participant_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("participants.id"), nullable=True
    )
    interval_id: Mapped[Optional[int]] = mapped_column(ForeignKey("intervals.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[FlagSeverity] = mapped_column(
        Enum(FlagSeverity, name="flag_severity", native_enum=False),
        nullable=False,
        default=FlagSeverity.medium,
    )
    status: Mapped[FlagStatus] = mapped_column(
        Enum(FlagStatus, name="flag_status", native_enum=False),
        nullable=False,
        default=FlagStatus.open,
    )
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class ConfigEntry(Base):
    """Key/value market configuration (seeded from core/params.py)."""

    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    before: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    after: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Transaction(Base):
    """Idempotent record of every chain write (Phase 7 uses this)."""

    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[TxStatus] = mapped_column(
        Enum(TxStatus, name="tx_status", native_enum=False),
        nullable=False,
        default=TxStatus.pending,
    )
    tx_hash: Mapped[Optional[str]] = mapped_column(String(66), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


# Keep Phase 0 smoke model
class HealthAudit(Base):
    """Simple audit model retained from Phase 0."""

    __tablename__ = "health_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
