"""
Log Analyzer - Analysis tools for trading logs.

Provides statistical analysis and performance metrics from logged trading data.
Works with both PostgreSQL tables and fallback JSONL files.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import polars as pl
from loguru import logger

from sqlalchemy import text as sa_text

from ..database.session import DatabaseManager


# ═══════════════════════════════════════════════════════════════════════════
# Analysis Result Data Classes
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class SignalStats:
    """Signal statistics."""
    total_signals: int
    executed: int
    rejected: int
    hold: int
    execution_rate_pct: float
    by_epic: dict[str, int]
    by_strategy: dict[str, int]
    by_direction: dict[str, int]


@dataclass
class ExecutionStats:
    """Execution statistics."""
    total_trades: int
    open_positions: int
    closed_trades: int
    total_pnl: float
    avg_pnl: float
    wins: int
    losses: int
    win_rate_pct: float
    avg_win: float
    avg_loss: float
    profit_factor: float  # abs(total_wins) / abs(total_losses)
    avg_duration_hours: float
    by_epic: dict[str, dict[str, Any]]  # {epic: {trades, pnl, win_rate, ...}}


@dataclass
class RiskStats:
    """Risk management statistics."""
    total_events: int
    circuit_breaker_triggers: int
    position_limit_hits: int
    drawdown_limit_hits: int
    max_drawdown_pct: float
    avg_daily_pnl: float
    by_event_type: dict[str, int]
    last_event_timestamp: datetime | None


# ═══════════════════════════════════════════════════════════════════════════
# LogAnalyzer Class
# ═══════════════════════════════════════════════════════════════════════════


class LogAnalyzer:
    """
    Analyze trading logs for performance metrics and statistics.

    Supports both PostgreSQL and JSONL file fallback sources.
    """

    def __init__(self, log_dir: Path | None = None):
        """
        Initialize log analyzer.

        Args:
            log_dir: Directory for fallback JSONL files (default: data/logs/)
        """
        self.log_dir = log_dir or Path("data/logs")

    # ───────────────────────────────────────────────────────────────────────
    # Signal Analysis
    # ───────────────────────────────────────────────────────────────────────

    async def get_signal_stats(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> SignalStats:
        """
        Get signal statistics for a date range.

        Args:
            start_date: Start date (default: 30 days ago)
            end_date: End date (default: now)

        Returns:
            Signal statistics
        """
        if start_date is None:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        try:
            # Try PostgreSQL first
            df = await self._query_signals_pg(start_date, end_date)
        except Exception as e:
            logger.warning(f"PostgreSQL query failed, using file fallback: {e}")
            df = self._read_signals_file(start_date, end_date)

        if df.is_empty():
            return SignalStats(
                total_signals=0,
                executed=0,
                rejected=0,
                hold=0,
                execution_rate_pct=0.0,
                by_epic={},
                by_strategy={},
                by_direction={},
            )

        total = len(df)
        executed = len(df.filter(pl.col("execution_status") == "executed"))
        rejected = len(df.filter(pl.col("execution_status") == "rejected"))
        hold = len(df.filter(pl.col("direction") == "HOLD"))

        # Group by epic
        by_epic = (
            df.group_by("epic")
            .agg(pl.len())
            .select(["epic", "len"])
            .to_dicts()
        )
        by_epic_dict = {row["epic"]: row["len"] for row in by_epic}

        # Group by strategy
        by_strategy = (
            df.group_by("strategy")
            .agg(pl.len())
            .select(["strategy", "len"])
            .to_dicts()
        )
        by_strategy_dict = {row["strategy"]: row["len"] for row in by_strategy}

        # Group by direction
        by_direction = (
            df.group_by("direction")
            .agg(pl.len())
            .select(["direction", "len"])
            .to_dicts()
        )
        by_direction_dict = {row["direction"]: row["len"] for row in by_direction}

        return SignalStats(
            total_signals=total,
            executed=executed,
            rejected=rejected,
            hold=hold,
            execution_rate_pct=round(executed / total * 100, 2) if total > 0 else 0.0,
            by_epic=by_epic_dict,
            by_strategy=by_strategy_dict,
            by_direction=by_direction_dict,
        )

    # ───────────────────────────────────────────────────────────────────────
    # Execution Analysis
    # ───────────────────────────────────────────────────────────────────────

    async def get_execution_stats(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> ExecutionStats:
        """
        Get execution statistics for a date range.

        Args:
            start_date: Start date (default: 30 days ago)
            end_date: End date (default: now)

        Returns:
            Execution statistics
        """
        if start_date is None:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        try:
            df = await self._query_executions_pg(start_date, end_date)
        except Exception as e:
            logger.warning(f"PostgreSQL query failed, using file fallback: {e}")
            df = self._read_executions_file(start_date, end_date)

        if df.is_empty():
            return ExecutionStats(
                total_trades=0,
                open_positions=0,
                closed_trades=0,
                total_pnl=0.0,
                avg_pnl=0.0,
                wins=0,
                losses=0,
                win_rate_pct=0.0,
                avg_win=0.0,
                avg_loss=0.0,
                profit_factor=0.0,
                avg_duration_hours=0.0,
                by_epic={},
            )

        total = len(df)
        open_pos = len(df.filter(pl.col("exit_timestamp").is_null()))
        closed = len(df.filter(pl.col("exit_timestamp").is_not_null()))

        # Analyze closed trades
        closed_df = df.filter(pl.col("exit_timestamp").is_not_null())

        if closed_df.is_empty():
            total_pnl = 0.0
            avg_pnl = 0.0
            wins = 0
            losses = 0
            win_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            profit_factor = 0.0
            avg_duration = 0.0
        else:
            total_pnl = closed_df["realized_pnl"].sum()
            avg_pnl = closed_df["realized_pnl"].mean()
            wins = len(closed_df.filter(pl.col("realized_pnl") > 0))
            losses = len(closed_df.filter(pl.col("realized_pnl") <= 0))
            win_rate = wins / closed * 100 if closed > 0 else 0.0

            wins_df = closed_df.filter(pl.col("realized_pnl") > 0)
            losses_df = closed_df.filter(pl.col("realized_pnl") <= 0)

            avg_win = wins_df["realized_pnl"].mean() if len(wins_df) > 0 else 0.0
            avg_loss = losses_df["realized_pnl"].mean() if len(losses_df) > 0 else 0.0

            total_wins_abs = wins_df["realized_pnl"].sum() if len(wins_df) > 0 else 0.0
            total_losses_abs = abs(losses_df["realized_pnl"].sum()) if len(losses_df) > 0 else 1.0
            profit_factor = total_wins_abs / total_losses_abs if total_losses_abs > 0 else 0.0

            # Calculate duration
            duration_series = (
                pl.col("exit_timestamp").cast(pl.Datetime) - pl.col("timestamp").cast(pl.Datetime)
            ).dt.total_seconds() / 3600
            avg_duration = closed_df.select(duration_series.alias("duration")).get_column("duration").mean()

        # Group by epic
        by_epic_dict = {}
        for epic in df["epic"].unique():
            epic_df = closed_df.filter(pl.col("epic") == epic)
            if not epic_df.is_empty():
                epic_trades = len(epic_df)
                epic_pnl = epic_df["realized_pnl"].sum()
                epic_wins = len(epic_df.filter(pl.col("realized_pnl") > 0))
                epic_win_rate = epic_wins / epic_trades * 100 if epic_trades > 0 else 0.0

                by_epic_dict[epic] = {
                    "trades": epic_trades,
                    "pnl": round(float(epic_pnl), 2),
                    "win_rate_pct": round(epic_win_rate, 2),
                }

        return ExecutionStats(
            total_trades=total,
            open_positions=open_pos,
            closed_trades=closed,
            total_pnl=round(float(total_pnl), 2),
            avg_pnl=round(float(avg_pnl), 2),
            wins=wins,
            losses=losses,
            win_rate_pct=round(win_rate, 2),
            avg_win=round(float(avg_win), 2),
            avg_loss=round(float(avg_loss), 2),
            profit_factor=round(profit_factor, 2),
            avg_duration_hours=round(float(avg_duration), 2),
            by_epic=by_epic_dict,
        )

    # ───────────────────────────────────────────────────────────────────────
    # Risk Analysis
    # ───────────────────────────────────────────────────────────────────────

    async def get_risk_stats(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> RiskStats:
        """
        Get risk management statistics for a date range.

        Args:
            start_date: Start date (default: 30 days ago)
            end_date: End date (default: now)

        Returns:
            Risk statistics
        """
        if start_date is None:
            start_date = datetime.now(timezone.utc) - timedelta(days=30)
        if end_date is None:
            end_date = datetime.now(timezone.utc)

        try:
            df = await self._query_risk_events_pg(start_date, end_date)
        except Exception as e:
            logger.warning(f"PostgreSQL query failed, using file fallback: {e}")
            df = self._read_risk_events_file(start_date, end_date)

        if df.is_empty():
            return RiskStats(
                total_events=0,
                circuit_breaker_triggers=0,
                position_limit_hits=0,
                drawdown_limit_hits=0,
                max_drawdown_pct=0.0,
                avg_daily_pnl=0.0,
                by_event_type={},
                last_event_timestamp=None,
            )

        total = len(df)
        cb_triggers = len(df.filter(pl.col("event_type") == "circuit_breaker"))
        pos_limit = len(df.filter(pl.col("event_type") == "position_limit"))
        dd_limit = len(df.filter(pl.col("event_type") == "drawdown_limit"))

        max_dd = df["current_drawdown_pct"].max() if "current_drawdown_pct" in df.columns else 0.0
        avg_pnl = df["daily_pnl"].mean() if "daily_pnl" in df.columns else 0.0

        # Group by event type
        by_type = (
            df.group_by("event_type")
            .agg(pl.len())
            .select(["event_type", "len"])
            .to_dicts()
        )
        by_type_dict = {row["event_type"]: row["len"] for row in by_type}

        last_event = df.select(pl.col("timestamp").max()).item()

        return RiskStats(
            total_events=total,
            circuit_breaker_triggers=cb_triggers,
            position_limit_hits=pos_limit,
            drawdown_limit_hits=dd_limit,
            max_drawdown_pct=round(float(max_dd) if max_dd else 0.0, 2),
            avg_daily_pnl=round(float(avg_pnl) if avg_pnl else 0.0, 2),
            by_event_type=by_type_dict,
            last_event_timestamp=last_event if isinstance(last_event, datetime) else None,
        )

    # ───────────────────────────────────────────────────────────────────────
    # PostgreSQL Queries
    # ───────────────────────────────────────────────────────────────────────

    async def _query_signals_pg(self, start_date: datetime, end_date: datetime) -> pl.DataFrame:
        """Query signals from PostgreSQL."""
        async with DatabaseManager.session() as session:
            query = """
                SELECT * FROM signal_log
                WHERE timestamp >= :start_date AND timestamp <= :end_date
                ORDER BY timestamp DESC
            """
            result = await session.execute(sa_text(query), {"start_date": start_date, "end_date": end_date})
            rows = result.fetchall()

            if not rows:
                return pl.DataFrame()

            # Convert to Polars DataFrame
            return pl.DataFrame([dict(row._mapping) for row in rows])

    async def _query_executions_pg(self, start_date: datetime, end_date: datetime) -> pl.DataFrame:
        """Query executions from PostgreSQL."""
        async with DatabaseManager.session() as session:
            query = """
                SELECT * FROM execution_log
                WHERE timestamp >= :start_date AND timestamp <= :end_date
                AND status = 'executed'
                ORDER BY timestamp DESC
            """
            result = await session.execute(sa_text(query), {"start_date": start_date, "end_date": end_date})
            rows = result.fetchall()

            if not rows:
                return pl.DataFrame()

            return pl.DataFrame([dict(row._mapping) for row in rows])

    async def _query_risk_events_pg(self, start_date: datetime, end_date: datetime) -> pl.DataFrame:
        """Query risk events from PostgreSQL."""
        async with DatabaseManager.session() as session:
            query = """
                SELECT * FROM risk_event_log
                WHERE timestamp >= :start_date AND timestamp <= :end_date
                ORDER BY timestamp DESC
            """
            result = await session.execute(sa_text(query), {"start_date": start_date, "end_date": end_date})
            rows = result.fetchall()

            if not rows:
                return pl.DataFrame()

            return pl.DataFrame([dict(row._mapping) for row in rows])

    # ───────────────────────────────────────────────────────────────────────
    # File Fallback Methods
    # ───────────────────────────────────────────────────────────────────────

    def _read_signals_file(self, start_date: datetime, end_date: datetime) -> pl.DataFrame:
        """Read signals from JSONL file."""
        file_path = self.log_dir / "signals.jsonl"
        if not file_path.exists() or file_path.stat().st_size == 0:
            return pl.DataFrame()

        try:
            df = pl.read_ndjson(file_path)
        except Exception as e:
            logger.warning(f"Failed to read signals file: {e}")
            return pl.DataFrame()
        df = df.with_columns(
            pl.col("timestamp").str.replace("Z$", "")
            .str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%S%.f")
            .dt.replace_time_zone("UTC")
        )
        # Ensure filter dates are timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        return df.filter(
            (pl.col("timestamp") >= start_date) & (pl.col("timestamp") <= end_date)
        )

    def _read_executions_file(self, start_date: datetime, end_date: datetime) -> pl.DataFrame:
        """Read executions from JSONL file."""
        file_path = self.log_dir / "executions.jsonl"
        if not file_path.exists():
            return pl.DataFrame()

        try:
            df = pl.read_ndjson(file_path)
        except Exception as e:
            logger.warning(f"Failed to read executions file: {e}")
            return pl.DataFrame()

        # Parse timestamp column
        if "timestamp" in df.columns:
            try:
                df = df.with_columns(
                    pl.col("timestamp").str.replace("Z$", "")
                    .str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%S%.f")
                    .dt.replace_time_zone("UTC")
                )
            except Exception:
                # Fallback: skip timestamp parsing
                pass

        # Parse exit_timestamp if present (handle null/missing values)
        if "exit_timestamp" in df.columns:
            try:
                # Cast to string first to ensure consistent type
                df = df.with_columns(pl.col("exit_timestamp").cast(pl.Utf8).alias("exit_timestamp"))
                # Then parse non-null values
                df = df.with_columns(
                    pl.when(pl.col("exit_timestamp").is_null() | (pl.col("exit_timestamp") == "null"))
                    .then(None)
                    .otherwise(
                        pl.col("exit_timestamp").str.replace("Z$", "")
                        .str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%S%.f")
                        .dt.replace_time_zone("UTC")
                    )
                    .alias("exit_timestamp")
                )
            except Exception:
                # If parsing fails, leave as is or set to None
                df = df.with_columns(pl.lit(None).alias("exit_timestamp"))

        # Filter by date and status
        filters = [pl.col("status") == "executed"]
        ts_is_datetime = "timestamp" in df.columns and str(df["timestamp"].dtype).startswith("Datetime")
        if ts_is_datetime:
            # Ensure filter dates are timezone-aware
            if start_date.tzinfo is None:
                start_date = start_date.replace(tzinfo=timezone.utc)
            if end_date.tzinfo is None:
                end_date = end_date.replace(tzinfo=timezone.utc)
            filters.extend([
                pl.col("timestamp") >= start_date,
                pl.col("timestamp") <= end_date
            ])

        return df.filter(pl.all_horizontal(filters))

    def _read_risk_events_file(self, start_date: datetime, end_date: datetime) -> pl.DataFrame:
        """Read risk events from JSONL file."""
        file_path = self.log_dir / "risk_events.jsonl"
        if not file_path.exists() or file_path.stat().st_size == 0:
            return pl.DataFrame()

        try:
            df = pl.read_ndjson(file_path)
        except Exception as e:
            logger.warning(f"Failed to read risk events file: {e}")
            return pl.DataFrame()
        df = df.with_columns(
            pl.col("timestamp").str.replace("Z$", "")
            .str.strptime(pl.Datetime, "%Y-%m-%dT%H:%M:%S%.f")
            .dt.replace_time_zone("UTC")
        )
        # Ensure filter dates are timezone-aware
        if start_date.tzinfo is None:
            start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        return df.filter(
            (pl.col("timestamp") >= start_date) & (pl.col("timestamp") <= end_date)
        )
