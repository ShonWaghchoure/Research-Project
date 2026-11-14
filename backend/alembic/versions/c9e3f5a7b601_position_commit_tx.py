"""Persist the on-chain position commit transaction hash.

Revision ID: c9e3f5a7b601
Revises: b8d2e3f4a506
Create Date: 2026-11-14 09:20:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c9e3f5a7b601"
down_revision: Union[str, None] = "b8d2e3f4a506"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("positions", sa.Column("committed_tx", sa.String(length=66), nullable=True))


def downgrade() -> None:
    op.drop_column("positions", "committed_tx")
