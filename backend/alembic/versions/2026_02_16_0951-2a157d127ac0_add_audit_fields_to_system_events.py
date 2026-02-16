"""add_audit_fields_to_system_events

Revision ID: 2a157d127ac0
Revises: 0edb33915968
Create Date: 2026-02-16 09:51:21.121383

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "2a157d127ac0"
down_revision: Union[str, Sequence[str], None] = "0edb33915968"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - Add audit fields to system_events."""
    # Add user tracking columns
    op.add_column("system_events", sa.Column("user_id", sa.BigInteger(), nullable=True))
    op.add_column("system_events", sa.Column("ip_address", sa.String(length=45), nullable=True))
    op.add_column("system_events", sa.Column("user_agent", sa.Text(), nullable=True))

    # Add HTTP request/response columns
    op.add_column("system_events", sa.Column("request_method", sa.String(length=10), nullable=True))
    op.add_column(
        "system_events", sa.Column("request_path", sa.String(length=255), nullable=True)
    )
    op.add_column("system_events", sa.Column("response_status_code", sa.Integer(), nullable=True))

    # Add foreign key for user_id (if users table exists)
    op.create_foreign_key(
        "fk_system_events_user_id",
        "system_events",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add index on user_id for faster lookups
    op.create_index(op.f("ix_system_events_user_id"), "system_events", ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema - Remove audit fields from system_events."""
    # Drop index
    op.drop_index(op.f("ix_system_events_user_id"), table_name="system_events")

    # Drop foreign key
    op.drop_constraint("fk_system_events_user_id", "system_events", type_="foreignkey")

    # Drop columns
    op.drop_column("system_events", "response_status_code")
    op.drop_column("system_events", "request_path")
    op.drop_column("system_events", "request_method")
    op.drop_column("system_events", "user_agent")
    op.drop_column("system_events", "ip_address")
    op.drop_column("system_events", "user_id")
