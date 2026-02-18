"""Add composite indexes for positions and signals

Revision ID: d7e9f3a2b1c0
Revises: a8f3e2b1c4d5
Create Date: 2026-02-18 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7e9f3a2b1c0"
down_revision: Union[str, Sequence[str], None] = "a8f3e2b1c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add composite indexes for common query patterns.

    - positions(epic, status): "get open positions for XAUUSD"
    - signals(epic, generated_at): "latest signals for BTCUSD"
    """
    op.create_index(
        "ix_positions_epic_status", "positions", ["epic", "status"], unique=False
    )
    op.create_index(
        "ix_signals_epic_generated_at", "signals", ["epic", "generated_at"], unique=False
    )


def downgrade() -> None:
    """Drop composite indexes."""
    op.drop_index("ix_signals_epic_generated_at", table_name="signals")
    op.drop_index("ix_positions_epic_status", table_name="positions")
