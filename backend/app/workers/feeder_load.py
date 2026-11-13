"""Load engine Feeder from DB feeder_nodes / feeder_lines."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import FeederLine as DbLine
from app.db.models import FeederNode
from app.engine.grid import Feeder, FeederLine, default_13_node_feeder


def load_feeder(db: Session) -> Feeder:
    nodes = db.query(FeederNode).all()
    lines = db.query(DbLine).all()
    if not nodes or not lines:
        return default_13_node_feeder()
    root = next((n.id for n in nodes if n.is_root), "n0")
    eng_lines = tuple(
        FeederLine(
            id=ln.id,
            from_node=ln.from_node_id,
            to_node=ln.to_node_id,
            capacity_kw=ln.capacity_w / 1000.0,
        )
        for ln in lines
    )
    return Feeder(root=root, lines=eng_lines)
