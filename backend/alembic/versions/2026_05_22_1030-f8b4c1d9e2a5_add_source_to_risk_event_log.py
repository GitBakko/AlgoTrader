"""add source column to risk_event_log

Revision ID: f8b4c1d9e2a5
Revises: e7a9b1c2d3f4
Create Date: 2026-05-22 10:30:00.000000

Closes schema drift between `RiskEventLog` Pydantic model (which declares a
`source` field — paper_trading / demo_trading / live_trading / api_test) and
the `risk_event_log` table (which never had that column). Before this
migration every INSERT raised UndefinedColumnError and the TradeLogger fell
back to writing `data/logs/risk_events.jsonl`, leaving the DB-backed audit
trail (used by `/monitoring/risk-events`, `recent_risk_events` view,
dashboard alert history) empty for all risk events.

NOT NULL with default 'unknown' so historical rows keep auditability without
needing a separate backfill pass.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f8b4c1d9e2a5"
down_revision: Union[str, Sequence[str], None] = "e7a9b1c2d3f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "risk_event_log",
        sa.Column(
            "source",
            sa.String(length=40),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.create_index(
        "idx_risk_event_log_source",
        "risk_event_log",
        ["source"],
    )


def downgrade() -> None:
    op.drop_index("idx_risk_event_log_source", table_name="risk_event_log")
    op.drop_column("risk_event_log", "source")
