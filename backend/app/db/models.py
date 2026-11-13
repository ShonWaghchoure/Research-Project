from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class HealthAudit(Base):
    """Simple audit model to verify SQLAlchemy mapping and migrations."""

    __tablename__ = "health_audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ok")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
