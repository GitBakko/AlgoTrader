"""Add state recovery tables

Revision ID: 145ede810294
Revises: b148026e0b42
Create Date: 2026-02-15 10:59:32.217033

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "145ede810294"
down_revision: Union[str, Sequence[str], None] = "b148026e0b42"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add trailing_stop_states and risk_state_snapshots tables."""
    # Create trailing_stop_states table
    op.create_table(
        "trailing_stop_states",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("deal_id", sa.String(length=100), nullable=False),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("current_stop", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("tp1_level", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("tp2_level", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("phase", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("highest_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("lowest_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("NOW()"),
            onupdate=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id"),
    )
    op.create_index(op.f("ix_trailing_stop_states_deal_id"), "trailing_stop_states", ["deal_id"], unique=False)

    # Create risk_state_snapshots table
    op.create_table(
        "risk_state_snapshots",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("peak_equity", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("daily_start_equity", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("current_equity", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("consecutive_losses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tripped_breakers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("equity_curve_points", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "snapshot_at", sa.DateTime(), nullable=False, server_default=sa.text("NOW()")
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_risk_state_snapshots_snapshot_at"), "risk_state_snapshots", ["snapshot_at"], unique=False
    )


def downgrade() -> None:
    """Remove state recovery tables."""
    op.drop_index(op.f("ix_risk_state_snapshots_snapshot_at"), table_name="risk_state_snapshots")
    op.drop_table("risk_state_snapshots")
    op.drop_index(op.f("ix_trailing_stop_states_deal_id"), table_name="trailing_stop_states")
    op.drop_table("trailing_stop_states")
