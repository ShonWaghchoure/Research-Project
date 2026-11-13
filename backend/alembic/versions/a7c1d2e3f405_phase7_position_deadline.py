"""phase7_position_deadline

Revision ID: a7c1d2e3f405
Revises: 364439bcf300
Create Date: 2026-11-13 23:15:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "a7c1d2e3f405"
down_revision: Union[str, None] = "364439bcf300"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("positions", sa.Column("deadline", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("positions", "deadline")
