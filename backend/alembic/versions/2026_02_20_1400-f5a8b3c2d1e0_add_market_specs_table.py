"""add_market_specs_table

Revision ID: f5a8b3c2d1e0
Revises: e3446105ad50
Create Date: 2026-02-20 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f5a8b3c2d1e0"
down_revision: Union[str, Sequence[str], None] = "e3446105ad50"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create market_specs table for caching broker dealing rules."""
    op.create_table(
        "market_specs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("epic", sa.String(length=50), nullable=False, index=True),
        sa.Column("environment", sa.String(length=10), nullable=False),
        sa.Column("min_deal_size", sa.Numeric(precision=15, scale=6), nullable=False),
        sa.Column(
            "min_deal_size_unit",
            sa.String(length=20),
            nullable=False,
            server_default="UNITS",
        ),
        sa.Column("max_deal_size", sa.Numeric(precision=15, scale=6), nullable=True),
        sa.Column("market_name", sa.String(length=200), nullable=True),
        sa.Column("fetched_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("epic", "environment", name="uq_market_spec_epic_env"),
    )


def downgrade() -> None:
    """Drop market_specs table."""
    op.drop_table("market_specs")
