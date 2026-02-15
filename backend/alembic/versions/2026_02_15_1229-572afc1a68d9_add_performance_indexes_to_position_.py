"""Add performance indexes to Position table

Revision ID: 572afc1a68d9
Revises: 145ede810294
Create Date: 2026-02-15 12:29:11.704751

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "572afc1a68d9"
down_revision: Union[str, Sequence[str], None] = "145ede810294"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Upgrade schema.

    Add performance indexes to Position table for faster queries:
    - status: Frequently filtered (OPEN vs CLOSED positions)
    - deal_id: Used in reconciliation and recovery lookups
    """
    # Add index on status column for faster OPEN position queries
    op.create_index(
        "ix_positions_status", "positions", ["status"], unique=False
    )

    # Add index on deal_id column for faster lookups during reconciliation
    op.create_index(
        "ix_positions_deal_id", "positions", ["deal_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes in reverse order
    op.drop_index("ix_positions_deal_id", table_name="positions")
    op.drop_index("ix_positions_status", table_name="positions")
