"""add paper_pnl_snapshots + position_pnl_snapshots tables

Revision ID: c3d8e9f0a1b2
Revises: b2c7d9e8f3a1
Create Date: 2026-04-27 13:00:00.000000

Time-series tables that store the live P&L state every 60s. Powers the
Paper Trading v2 KPI strip (P&L Open / P&L Today sparklines) and the
position-card price chart with real history instead of fabricated data.

`paper_pnl_snapshots` — one row per snapshot tick with the global figures.
`position_pnl_snapshots` — one row per snapshot tick PER open position.

Both tables are indexed on `captured_at` for cheap range scans. The
position table additionally indexes on (deal_id, captured_at) for the
per-position detail charts.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b2c7d9e8f3a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "paper_pnl_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("captured_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("pnl_open", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl_today", sa.Float(), nullable=False, server_default="0"),
        sa.Column("equity", sa.Float(), nullable=True),
        sa.Column("open_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=8), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_paper_pnl_snapshots_captured_at",
        "paper_pnl_snapshots",
        ["captured_at"],
    )

    op.create_table(
        "position_pnl_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("deal_id", sa.String(length=64), nullable=False),
        sa.Column("epic", sa.String(length=32), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("pnl", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pnl_pct", sa.Float(), nullable=False, server_default="0"),
        sa.Column("current_price", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "ix_position_pnl_snapshots_captured_at",
        "position_pnl_snapshots",
        ["captured_at"],
    )
    op.create_index(
        "ix_position_pnl_snapshots_deal_captured",
        "position_pnl_snapshots",
        ["deal_id", "captured_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_position_pnl_snapshots_deal_captured",
        table_name="position_pnl_snapshots",
    )
    op.drop_index(
        "ix_position_pnl_snapshots_captured_at",
        table_name="position_pnl_snapshots",
    )
    op.drop_table("position_pnl_snapshots")
    op.drop_index(
        "ix_paper_pnl_snapshots_captured_at",
        table_name="paper_pnl_snapshots",
    )
    op.drop_table("paper_pnl_snapshots")
