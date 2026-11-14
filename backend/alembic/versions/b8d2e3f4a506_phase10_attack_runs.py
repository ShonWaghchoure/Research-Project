"""phase10_attack_runs

Revision ID: b8d2e3f4a506
Revises: a7c1d2e3f405
Create Date: 2026-11-14 12:40:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "b8d2e3f4a506"
down_revision: Union[str, None] = "a7c1d2e3f405"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "attack_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scenario", sa.String(length=64), nullable=False),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("defenses", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_attack_runs_scenario", "attack_runs", ["scenario"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_attack_runs_scenario", table_name="attack_runs")
    op.drop_table("attack_runs")
