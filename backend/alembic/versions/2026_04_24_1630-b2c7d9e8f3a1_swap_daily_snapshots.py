"""add swap_daily_snapshots table

Revision ID: b2c7d9e8f3a1
Revises: a910f5d6e7b2
Create Date: 2026-04-24 16:30:00.000000

Daily snapshot of overnight-swap rate + notional per epic. Enables
Dashboard v2 /swap-accum to surface real historical swap exposure
instead of extrapolating today's rate across N past days.

Upsert key: (epic, snapshot_date). Scheduler writes one row per epic
once daily after the Capital.com rollover window.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c7d9e8f3a1"
down_revision: Union[str, Sequence[str], None] = "a910f5d6e7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "swap_daily_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("epic", sa.String(length=32), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("long_rate_pct", sa.Float(), nullable=True),
        sa.Column("short_rate_pct", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("notional", sa.Float(), nullable=False, server_default="0"),
        sa.Column("swap_realized", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "epic", "snapshot_date", name="uq_swap_daily_epic_date"
        ),
    )
    op.create_index(
        "ix_swap_daily_snapshots_epic",
        "swap_daily_snapshots",
        ["epic"],
    )
    op.create_index(
        "ix_swap_daily_snapshots_snapshot_date",
        "swap_daily_snapshots",
        ["snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_swap_daily_snapshots_snapshot_date",
        table_name="swap_daily_snapshots",
    )
    op.drop_index(
        "ix_swap_daily_snapshots_epic",
        table_name="swap_daily_snapshots",
    )
    op.drop_table("swap_daily_snapshots")
