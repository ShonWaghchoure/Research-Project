"""Seed feeder topology, default config, and 20 Hardhat participants.

Usage: python -m app.db.seed
"""

from __future__ import annotations

import sys

from eth_utils import to_checksum_address
from sqlalchemy.orm import Session

from app.core.config_store import seed_config
from app.db.hardhat_accounts import HARDHAT_ACCOUNTS
from app.db.models import (
    EvState,
    FeederLine,
    FeederNode,
    Participant,
    ParticipantType,
    User,
    UserRole,
)
from app.db.session import SessionLocal
from app.engine.grid import default_13_node_feeder

# Cycle node assignment across leaf-ish buses (skip root for realism).
_NODE_CYCLE = ["n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9", "n10", "n11", "n12"]


def seed_feeder(db: Session, capacity_kw: float = 100.0) -> None:
    feeder = default_13_node_feeder(capacity_kw=capacity_kw)
    for node_id in feeder.nodes():
        if db.get(FeederNode, node_id) is None:
            db.add(
                FeederNode(
                    id=node_id,
                    name=node_id,
                    is_root=(node_id == feeder.root),
                )
            )
    db.flush()
    for line in feeder.lines:
        if db.get(FeederLine, line.id) is None:
            db.add(
                FeederLine(
                    id=line.id,
                    from_node_id=line.from_node,
                    to_node_id=line.to_node,
                    capacity_w=int(round(line.capacity_kw * 1000)),
                )
            )
    db.flush()


def _role_for_index(i: int) -> UserRole:
    if i == 0:
        return UserRole.admin
    if i == 1:
        return UserRole.operator
    return UserRole.participant


def _type_for_index(i: int) -> ParticipantType:
    # Mix: consumers, prosumers, a few EVs
    if i % 5 == 0:
        return ParticipantType.ev
    if i % 3 == 0:
        return ParticipantType.consumer
    return ParticipantType.prosumer


def seed_participants(db: Session) -> int:
    created = 0
    for acct in HARDHAT_ACCOUNTS:
        address = to_checksum_address(acct.address)
        user = db.query(User).filter(User.address == address).one_or_none()
        if user is None:
            user = User(address=address, role=_role_for_index(acct.index), nonce_used=True)
            db.add(user)
            db.flush()
        else:
            user.role = _role_for_index(acct.index)

        existing = db.query(Participant).filter(Participant.user_id == user.id).one_or_none()
        if existing is not None:
            continue

        ptype = _type_for_index(acct.index)
        node_id = _NODE_CYCLE[acct.index % len(_NODE_CYCLE)]
        pv_w = 0 if ptype == ParticipantType.consumer else 3000 + (acct.index % 5) * 1000
        battery_wh = 0 if ptype == ParticipantType.consumer else 5000 + (acct.index % 3) * 2000
        ev_battery_wh = 40000 if ptype == ParticipantType.ev else None
        ev_max_power_w = 7000 if ptype == ParticipantType.ev else None

        p = Participant(
            user_id=user.id,
            type=ptype,
            display_name=f"demo-{acct.index:02d}",
            feeder_node_id=node_id,
            pv_capacity_w=pv_w,
            battery_wh=battery_wh,
            ev_battery_wh=ev_battery_wh,
            ev_max_power_w=ev_max_power_w,
            ev_v2g=(ptype == ParticipantType.ev and acct.index % 2 == 0),
        )
        db.add(p)
        db.flush()
        if ptype == ParticipantType.ev and ev_battery_wh is not None:
            db.add(
                EvState(
                    participant_id=p.id,
                    soc_wh=ev_battery_wh // 2,
                    target_wh=ev_battery_wh,
                )
            )
        created += 1
    db.flush()
    return created


def run_seed(db: Session | None = None) -> dict[str, int]:
    own = db is None
    session = db or SessionLocal()
    try:
        seed_feeder(session)
        seed_config(session)
        n_part = seed_participants(session)
        session.commit()
        n_nodes = session.query(FeederNode).count()
        n_lines = session.query(FeederLine).count()
        n_users = session.query(User).count()
        n_participants = session.query(Participant).count()
        return {
            "feeder_nodes": n_nodes,
            "feeder_lines": n_lines,
            "users": n_users,
            "participants": n_participants,
            "participants_created": n_part,
        }
    except Exception:
        session.rollback()
        raise
    finally:
        if own:
            session.close()


def main() -> None:
    stats = run_seed()
    print("seed complete:", stats)
    if stats["participants"] < 20:
        print("warning: expected 20 participants", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
