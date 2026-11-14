"""interval clearing_inputs snapshot (audit re-run reproducibility)

Revision ID: d4f2b8c6e913
Revises: c1e9a7b3d210
Create Date: 2026-11-14 19:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "d4f2b8c6e913"
down_revision: Union[str, None] = "c1e9a7b3d210"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("intervals", sa.Column("clearing_inputs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("intervals", "clearing_inputs")
