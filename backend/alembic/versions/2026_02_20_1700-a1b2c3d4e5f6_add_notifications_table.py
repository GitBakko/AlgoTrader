"""Add notifications table for in-app notification center.

Revision ID: a1b2c3d4e5f6
Revises: f5a8b3c2d1e0
Create Date: 2026-02-20 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "a1b2c3d4e5f6"
down_revision = "f5a8b3c2d1e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("alert_type", sa.String(50), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False, index=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("epic", sa.String(50), nullable=True, index=True),
        sa.Column("details", JSONB, nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.text("NOW()")),
    )
    # Composite index for "unread + recent" queries (dropdown + badge count)
    op.create_index(
        "ix_notifications_unread_recent",
        "notifications",
        ["is_read", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_unread_recent", table_name="notifications")
    op.drop_table("notifications")
