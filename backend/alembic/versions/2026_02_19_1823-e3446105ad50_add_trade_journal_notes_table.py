"""add_trade_journal_notes_table

Revision ID: e3446105ad50
Revises: d7e9f3a2b1c0
Create Date: 2026-02-19 18:23:20.004501

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e3446105ad50"
down_revision: Union[str, Sequence[str], None] = "d7e9f3a2b1c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create trade_journal_notes table."""
    op.create_table(
        "trade_journal_notes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("epic", sa.String(length=50), nullable=False, index=True),
        sa.Column("signal_timestamp", sa.String(length=50), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
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
        sa.UniqueConstraint("epic", "signal_timestamp", name="uq_journal_note_epic_ts"),
    )


def downgrade() -> None:
    """Drop trade_journal_notes table."""
    op.drop_table("trade_journal_notes")
