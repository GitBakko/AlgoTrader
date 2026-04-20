"""add deal_reference to positions

Revision ID: 284b174b7dc0
Revises: a1b2c3d4e5f6
Create Date: 2026-04-20 15:28:19.243259

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "284b174b7dc0"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "positions",
        sa.Column("deal_reference", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("positions", "deal_reference")
