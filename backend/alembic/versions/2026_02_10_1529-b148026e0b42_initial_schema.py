"""initial_schema

Revision ID: b148026e0b42
Revises:
Create Date: 2026-02-10 15:29:01.708499

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b148026e0b42"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - create all tables."""

    # Create strategies table (no dependencies)
    op.create_table(
        "strategies",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("timeframe", sa.String(length=10), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("model_ids", sa.ARRAY(sa.BigInteger()), nullable=True),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("risk_params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "performance_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("activated_at", sa.DateTime(), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_strategies_name"), "strategies", ["name"])
    op.create_index(op.f("ix_strategies_epic"), "strategies", ["epic"])
    op.create_index(op.f("ix_strategies_is_active"), "strategies", ["is_active"])

    # Create models table (no dependencies)
    op.create_table(
        "models",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("model_type", sa.String(length=50), nullable=False),
        sa.Column("file_path", sa.String(length=255), nullable=False),
        sa.Column(
            "hyperparameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("training_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "validation_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "feature_importance", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("trained_at", sa.DateTime(), nullable=False),
        sa.Column("train_start_date", sa.Date(), nullable=False),
        sa.Column("train_end_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", "epic"),
    )
    op.create_index(op.f("ix_models_epic"), "models", ["epic"])
    op.create_index(op.f("ix_models_is_active"), "models", ["is_active"])
    op.create_index(op.f("ix_models_trained_at"), "models", ["trained_at"], unique=False)

    # Create positions table (depends on strategies via nullable FK)
    op.create_table(
        "positions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("deal_id", sa.String(length=100), nullable=False),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("size", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("current_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("stop_loss", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("take_profit", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("profit_loss", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("opened_at", sa.DateTime(), nullable=False),
        sa.Column("closed_at", sa.DateTime(), nullable=True),
        sa.Column("close_reason", sa.String(length=50), nullable=True),
        sa.Column("strategy_id", sa.BigInteger(), nullable=True),
        sa.Column("signal_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id"),
    )
    op.create_index(op.f("ix_positions_deal_id"), "positions", ["deal_id"])
    op.create_index(op.f("ix_positions_epic"), "positions", ["epic"])
    op.create_index(op.f("ix_positions_status"), "positions", ["status"])
    op.create_index(op.f("ix_positions_opened_at"), "positions", ["opened_at"], unique=False)
    op.create_index(op.f("ix_positions_strategy_id"), "positions", ["strategy_id"])

    # Create signals table (depends on models, strategies, positions)
    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("timeframe", sa.String(length=10), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("predicted_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("stop_loss_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("take_profit_price", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("model_id", sa.BigInteger(), nullable=True),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("strategy_id", sa.BigInteger(), nullable=True),
        sa.Column("position_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["model_id"], ["models.id"]),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"]),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_signals_epic"), "signals", ["epic"])
    op.create_index(op.f("ix_signals_status"), "signals", ["status"])
    op.create_index(op.f("ix_signals_generated_at"), "signals", ["generated_at"], unique=False)
    op.create_index(op.f("ix_signals_confidence"), "signals", ["confidence"], unique=False)

    # Update positions to add FK to signals (circular dependency resolved)
    op.create_foreign_key(None, "positions", "signals", ["signal_id"], ["id"])

    # Create orders table (depends on strategies, signals)
    op.create_table(
        "orders",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("deal_id", sa.String(length=100), nullable=False),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("order_type", sa.String(length=10), nullable=False),
        sa.Column("size", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("trigger_price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("stop_loss", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("take_profit", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("good_till_date", sa.DateTime(), nullable=True),
        sa.Column("filled_at", sa.DateTime(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column("strategy_id", sa.BigInteger(), nullable=True),
        sa.Column("signal_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id"),
    )
    op.create_index(op.f("ix_orders_deal_id"), "orders", ["deal_id"])
    op.create_index(op.f("ix_orders_epic"), "orders", ["epic"])
    op.create_index(op.f("ix_orders_status"), "orders", ["status"])
    op.create_index(op.f("ix_orders_created_at"), "orders", ["created_at"], unique=False)

    # Create trades table (depends on positions)
    op.create_table(
        "trades",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("position_id", sa.BigInteger(), nullable=False),
        sa.Column("deal_reference", sa.String(length=100), nullable=True),
        sa.Column("trade_type", sa.String(length=10), nullable=False),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("direction", sa.String(length=4), nullable=False),
        sa.Column("size", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("price", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("profit_loss", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("commission", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("executed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_trades_position_id"), "trades", ["position_id"])
    op.create_index(op.f("ix_trades_executed_at"), "trades", ["executed_at"], unique=False)

    # Create accounts table (no dependencies)
    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.String(length=100), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False),
        sa.Column("balance", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("equity", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("available", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("margin_used", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("profit_loss", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), server_default="USD", nullable=False),
        sa.Column("snapshot_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_accounts_snapshot_at"), "accounts", ["snapshot_at"], unique=False)
    op.create_index(op.f("ix_accounts_account_id"), "accounts", ["account_id"])

    # Create market_data_snapshots table (no dependencies)
    op.create_table(
        "market_data_snapshots",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("timeframe", sa.String(length=10), nullable=False),
        sa.Column("open", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("high", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("low", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("close", sa.Numeric(precision=15, scale=4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("bid", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("ask", sa.Numeric(precision=15, scale=4), nullable=True),
        sa.Column("spread", sa.Numeric(precision=10, scale=4), nullable=True),
        sa.Column("client_sentiment_long", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("client_sentiment_short", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_market_data_snapshots_epic"),
        "market_data_snapshots",
        ["epic", "snapshot_at"],
    )
    op.create_index(
        op.f("ix_market_data_snapshots_snapshot_at"),
        "market_data_snapshots",
        ["snapshot_at"],
        unique=False,
    )

    # Create system_events table (depends on positions, signals)
    op.create_table(
        "system_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("component", sa.String(length=100), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("related_position_id", sa.BigInteger(), nullable=True),
        sa.Column("related_signal_id", sa.BigInteger(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["related_position_id"], ["positions.id"]),
        sa.ForeignKeyConstraint(["related_signal_id"], ["signals.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_events_event_type"), "system_events", ["event_type"])
    op.create_index(op.f("ix_system_events_severity"), "system_events", ["severity"])
    op.create_index(
        op.f("ix_system_events_occurred_at"), "system_events", ["occurred_at"], unique=False
    )
    op.create_index(op.f("ix_system_events_component"), "system_events", ["component"])

    # Create backtest_runs table (depends on strategies)
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("strategy_id", sa.BigInteger(), nullable=False),
        sa.Column("epic", sa.String(length=50), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("initial_capital", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("final_capital", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("total_trades", sa.Integer(), nullable=True),
        sa.Column("winning_trades", sa.Integer(), nullable=True),
        sa.Column("losing_trades", sa.Integer(), nullable=True),
        sa.Column("win_rate", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("sharpe_ratio", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("sortino_ratio", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("max_drawdown", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("calmar_ratio", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_backtest_runs_strategy_id"), "backtest_runs", ["strategy_id"]
    )
    op.create_index(
        op.f("ix_backtest_runs_started_at"), "backtest_runs", ["started_at"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema - drop all tables."""
    op.drop_table("backtest_runs")
    op.drop_table("system_events")
    op.drop_table("market_data_snapshots")
    op.drop_table("accounts")
    op.drop_table("trades")
    op.drop_table("orders")
    op.drop_table("signals")
    op.drop_table("positions")
    op.drop_table("models")
    op.drop_table("strategies")
