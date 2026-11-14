"""Security fix: simulated under-delivery is tied to the designated demo bot's address,
never to a display name that any participant can edit."""

from __future__ import annotations

from eth_account import Account
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Participant, ParticipantType, User, UserRole
from app.workers.bots import lazy_bot_address
from app.workers.meter import _is_lazy


def _participant(db: Session, address: str, name: str) -> Participant:
    u = db.query(User).filter(User.address == address).one_or_none()
    if u is None:
        u = User(address=address, role=UserRole.participant, nonce_used=True)
        db.add(u)
        db.flush()
    existing = db.query(Participant).filter(Participant.user_id == u.id).one_or_none()
    if existing is not None:
        return existing
    p = Participant(user_id=u.id, type=ParticipantType.prosumer, feeder_node_id="n1", display_name=name)
    db.add(p)
    db.flush()
    return p


def test_user_named_lazy_is_not_treated_as_lazy(seeded_db: Session, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    impostor = _participant(seeded_db, Account.create().address, "totally-lazy-name")
    assert _is_lazy(seeded_db, impostor) is False

    bot = _participant(seeded_db, lazy_bot_address(), "demo-bot")  # type: ignore[arg-type]
    assert _is_lazy(seeded_db, bot) is True


def test_no_lazy_bot_outside_demo_mode(seeded_db: Session, monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    assert lazy_bot_address() is None
