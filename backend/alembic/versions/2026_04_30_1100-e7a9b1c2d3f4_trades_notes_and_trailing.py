"""trades.notes column + bump trade_type length for trailing events

Revision ID: e7a9b1c2d3f4
Revises: c3d8e9f0a1b2
Create Date: 2026-04-30 11:00:00.000000

Adds a free-form `notes` column to `trades` (max 255 chars) so the trailing-
stop manager can persist transition reasons (e.g. "BREAKEVEN: TP1 hit at
1973.37") without overloading deal_reference. Also bumps `trade_type` to
varchar(20) to fit BREAKEVEN / TP1_LOCK / TRAIL_UPD / TP1_HIT codes
without truncation. Both are nullable / additive so the migration is
backwards-compatible.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a9b1c2d3f4"
down_revision: Union[str, Sequence[str], None] = "c3d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "trades",
        sa.Column("notes", sa.String(length=255), nullable=True),
    )
    op.alter_column(
        "trades",
        "trade_type",
        existing_type=sa.String(length=10),
        type_=sa.String(length=20),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "trades",
        "trade_type",
        existing_type=sa.String(length=20),
        type_=sa.String(length=10),
        existing_nullable=False,
    )
    op.drop_column("trades", "notes")
