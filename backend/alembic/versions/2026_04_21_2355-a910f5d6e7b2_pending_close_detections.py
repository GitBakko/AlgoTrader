"""add pending_close_detections table

Revision ID: a910f5d6e7b2
Revises: 284b174b7dc0
Create Date: 2026-04-21 23:55:00.000000

Persists the in-memory ``_pending_close_detections`` dict so the retry
count and first_seen timestamp survive a backend restart. Without this,
the 10-minute reconciliation timeout restarts from zero every time the
process is restarted — exactly the silent failure mode that turned
tonight's DE40 TP close into an UNRECONCILED row (restart at 22:40,
close was already pending, counter/first_seen reset, emit UNRECONCILED
at retry 2).

Column notes:
  - ``deal_id`` is the primary key — only one pending close can exist
    per Position at a time.
  - ``deal_reference`` mirrors positions.deal_reference (populated on
    post-PR#1 positions; NULL for legacy rows).
  - ``prev_pos`` is a JSON snapshot of the paper_positions entry at the
    moment close was detected; kept verbatim for audit. PostgreSQL's
    ``jsonb`` gives us efficient query + update semantics if we ever
    need to introspect.
  - ``last_activity_snapshot`` / ``last_transaction_snapshot`` store the
    raw broker payloads we last saw for this deal, so the operator has
    one place to look when investigating a hung reconciliation.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a910f5d6e7b2"
down_revision: Union[str, Sequence[str], None] = "284b174b7dc0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_close_detections",
        sa.Column("deal_id", sa.String(length=100), primary_key=True),
        sa.Column("deal_reference", sa.String(length=100), nullable=True),
        sa.Column("epic", sa.String(length=32), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("size", sa.Numeric(20, 8), nullable=False),
        sa.Column("entry_price", sa.Numeric(20, 8), nullable=False),
        sa.Column(
            "prev_pos",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "first_seen",
            sa.DateTime(timezone=False),
            nullable=False,
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "last_activity_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "last_transaction_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index(
        "ix_pending_close_detections_epic",
        "pending_close_detections",
        ["epic"],
    )
    op.create_index(
        "ix_pending_close_detections_first_seen",
        "pending_close_detections",
        ["first_seen"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_pending_close_detections_first_seen",
        table_name="pending_close_detections",
    )
    op.drop_index(
        "ix_pending_close_detections_epic",
        table_name="pending_close_detections",
    )
    op.drop_table("pending_close_detections")
