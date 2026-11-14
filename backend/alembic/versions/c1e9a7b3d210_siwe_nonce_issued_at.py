"""siwe nonce issued_at (security fix: bind sign-in to the exact issued message)

Revision ID: c1e9a7b3d210
Revises: b8d2e3f4a506
Create Date: 2026-11-14 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "c1e9a7b3d210"
down_revision: Union[str, None] = "b8d2e3f4a506"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("nonce_issued_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "nonce_issued_at")
