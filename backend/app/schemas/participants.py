from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

ParticipantTypeLiteral = Literal["consumer", "prosumer", "ev"]


class ParticipantCreate(BaseModel):
    type: ParticipantTypeLiteral
    feeder_node_id: str = Field(..., min_length=1, max_length=32)
    display_name: Optional[str] = Field(None, max_length=120)
    pv_capacity_kw: float = Field(0, ge=0, le=1000)
    battery_kwh: float = Field(0, ge=0, le=5000)
    ev_battery_kwh: Optional[float] = Field(None, ge=0, le=500)
    ev_max_power_kw: Optional[float] = Field(None, ge=0, le=500)
    ev_v2g: bool = False

    @field_validator("feeder_node_id")
    @classmethod
    def node_id_format(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def ev_fields_required(self) -> ParticipantCreate:
        if self.type == "ev":
            if self.ev_battery_kwh is None or self.ev_max_power_kw is None:
                raise ValueError("ev_battery_kwh and ev_max_power_kw are required for type=ev")
        if self.type == "consumer" and self.pv_capacity_kw > 0:
            raise ValueError("consumer cannot have pv_capacity_kw > 0")
        return self


class ParticipantUpdate(BaseModel):
    display_name: Optional[str] = Field(None, max_length=120)
    feeder_node_id: Optional[str] = Field(None, min_length=1, max_length=32)
    pv_capacity_kw: Optional[float] = Field(None, ge=0, le=1000)
    battery_kwh: Optional[float] = Field(None, ge=0, le=5000)
    ev_battery_kwh: Optional[float] = Field(None, ge=0, le=500)
    ev_max_power_kw: Optional[float] = Field(None, ge=0, le=500)
    ev_v2g: Optional[bool] = None
    active: Optional[bool] = None


class ParticipantOut(BaseModel):
    id: int
    address: str
    role: str
    type: ParticipantTypeLiteral
    display_name: Optional[str]
    feeder_node_id: str
    pv_capacity_kw: float
    battery_kwh: float
    ev_battery_kwh: Optional[float]
    ev_max_power_kw: Optional[float]
    ev_v2g: bool
    active: bool

    model_config = {"from_attributes": True}


class MeResponse(BaseModel):
    user_id: int
    address: str
    role: str
    participant: Optional[ParticipantOut] = None
