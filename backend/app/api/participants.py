"""Participant profile endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_participant
from app.db.deps import get_db
from app.db.models import EvState, FeederNode, Participant, ParticipantType, User
from app.schemas.participants import (
    MeResponse,
    ParticipantCreate,
    ParticipantOut,
    ParticipantUpdate,
)

router = APIRouter(tags=["participants"])


def _kw_to_w(kw: float) -> int:
    return int(round(kw * 1000))


def _kwh_to_wh(kwh: float) -> int:
    return int(round(kwh * 1000))


def _w_to_kw(w: int) -> float:
    return w / 1000.0


def _wh_to_kwh(wh: int) -> float:
    return wh / 1000.0


def participant_to_out(p: Participant, user: User) -> ParticipantOut:
    return ParticipantOut(
        id=p.id,
        address=user.address,
        role=user.role.value,
        type=p.type.value,  # type: ignore[arg-type]
        display_name=p.display_name,
        feeder_node_id=p.feeder_node_id,
        pv_capacity_kw=_w_to_kw(p.pv_capacity_w),
        battery_kwh=_wh_to_kwh(p.battery_wh),
        ev_battery_kwh=_wh_to_kwh(p.ev_battery_wh) if p.ev_battery_wh is not None else None,
        ev_max_power_kw=_w_to_kw(p.ev_max_power_w) if p.ev_max_power_w is not None else None,
        ev_v2g=p.ev_v2g,
        active=p.active,
    )


@router.get("/me", response_model=MeResponse)
def get_me(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MeResponse:
    participant = (
        db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
    )
    return MeResponse(
        user_id=user.id,
        address=user.address,
        role=user.role.value,
        participant=participant_to_out(participant, user) if participant else None,
    )


@router.post("/participants", response_model=ParticipantOut, status_code=status.HTTP_201_CREATED)
def create_participant(
    body: ParticipantCreate,
    user: User = Depends(require_participant),
    db: Session = Depends(get_db),
) -> ParticipantOut:
    existing = db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="participant already exists")

    node = db.get(FeederNode, body.feeder_node_id)
    if node is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown feeder_node_id")

    p = Participant(
        user_id=user.id,
        type=ParticipantType(body.type),
        display_name=body.display_name,
        feeder_node_id=body.feeder_node_id,
        pv_capacity_w=_kw_to_w(body.pv_capacity_kw),
        battery_wh=_kwh_to_wh(body.battery_kwh),
        ev_battery_wh=_kwh_to_wh(body.ev_battery_kwh) if body.ev_battery_kwh is not None else None,
        ev_max_power_w=_kw_to_w(body.ev_max_power_kw) if body.ev_max_power_kw is not None else None,
        ev_v2g=body.ev_v2g if body.type == "ev" else False,
    )
    db.add(p)
    db.flush()
    if body.type == "ev":
        db.add(
            EvState(
                participant_id=p.id,
                soc_wh=_kwh_to_wh(body.ev_battery_kwh or 0) // 2,
                target_wh=_kwh_to_wh(body.ev_battery_kwh or 0),
            )
        )
    db.commit()
    db.refresh(p)
    return participant_to_out(p, user)


@router.patch("/participants/{participant_id}", response_model=ParticipantOut)
def update_participant(
    participant_id: int,
    body: ParticipantUpdate,
    user: User = Depends(require_participant),
    db: Session = Depends(get_db),
) -> ParticipantOut:
    p = db.get(Participant, participant_id)
    if p is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if p.user_id != user.id and user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="not your participant")

    data = body.model_dump(exclude_unset=True)
    if "feeder_node_id" in data:
        node = db.get(FeederNode, data["feeder_node_id"])
        if node is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unknown feeder_node_id"
            )
        p.feeder_node_id = data["feeder_node_id"]
    if "display_name" in data:
        p.display_name = data["display_name"]
    if "pv_capacity_kw" in data:
        if p.type == ParticipantType.consumer and data["pv_capacity_kw"] > 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="consumer cannot have pv_capacity_kw > 0",
            )
        p.pv_capacity_w = _kw_to_w(data["pv_capacity_kw"])
    if "battery_kwh" in data:
        p.battery_wh = _kwh_to_wh(data["battery_kwh"])
    if "ev_battery_kwh" in data and data["ev_battery_kwh"] is not None:
        p.ev_battery_wh = _kwh_to_wh(data["ev_battery_kwh"])
    if "ev_max_power_kw" in data and data["ev_max_power_kw"] is not None:
        p.ev_max_power_w = _kw_to_w(data["ev_max_power_kw"])
    if "ev_v2g" in data and data["ev_v2g"] is not None:
        p.ev_v2g = data["ev_v2g"]
    if "active" in data and data["active"] is not None:
        p.active = data["active"]

    db.commit()
    db.refresh(p)
    owner = db.get(User, p.user_id)
    assert owner is not None
    return participant_to_out(p, owner)
