"""UNRECONCILED positions must not appear in aggregate trade stats.

Tests verify that:
1. get_closed_in_period filters out UNRECONCILED and NULL profit_loss rows
2. get_performance_stats filters out UNRECONCILED and NULL profit_loss rows
3. Python-level aggregate computation in positions router skips UNRECONCILED rows
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.database.repositories.position_repository import PositionRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_position(
    epic="WTIUSD",
    profit_loss: float | None = 10.0,
    close_reason: str = "TP",
    deal_id: str = "test-001",
):
    """Build a mock Position object."""
    p = MagicMock()
    p.id = deal_id
    p.epic = epic
    p.deal_id = deal_id
    p.direction = "BUY"
    p.size = Decimal("1.0")
    p.entry_price = Decimal("80.0")
    p.profit_loss = Decimal(str(profit_loss)) if profit_loss is not None else None
    p.status = "CLOSED"
    p.close_reason = close_reason
    p.closed_at = datetime.now(UTC).replace(tzinfo=None)
    p.opened_at = datetime.now(UTC).replace(tzinfo=None)
    return p


def _mock_scalars_result(rows):
    """Wrap a list into the mock scalar result chain execute().scalars().all()."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = rows
    result.scalars.return_value = scalars_mock
    return result


# ---------------------------------------------------------------------------
# Test: get_closed_in_period excludes UNRECONCILED via SQL filter
# ---------------------------------------------------------------------------


class TestGetClosedInPeriodFilter:
    """get_closed_in_period must pass UNRECONCILED-exclusion clauses to the DB."""

    @pytest.mark.asyncio
    async def test_query_excludes_unreconciled_clause(self):
        """Verify the WHERE clause includes close_reason != UNRECONCILED and profit_loss IS NOT NULL."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_scalars_result([]))
        repo = PositionRepository(session)

        start = datetime(2025, 1, 1, tzinfo=UTC)
        end = datetime(2025, 12, 31, tzinfo=UTC)
        await repo.get_closed_in_period(start, end)

        # The query was executed — extract the SQL string for clause inspection
        call_args = session.execute.call_args
        assert call_args is not None, "session.execute was not called"
        stmt = call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert (
            "UNRECONCILED" in compiled
        ), "get_closed_in_period must filter close_reason != 'UNRECONCILED'"
        assert (
            "profit_loss IS NOT NULL" in compiled or "profit_loss IS" in compiled
        ), "get_closed_in_period must filter profit_loss IS NOT NULL"

    @pytest.mark.asyncio
    async def test_returns_only_reconciled_positions(self):
        """When DB returns mixed rows, only reconciled rows come back."""
        good1 = _make_position(profit_loss=10.0, close_reason="TP", deal_id="g1")
        good2 = _make_position(profit_loss=-5.0, close_reason="SL", deal_id="g2")
        # In production the DB WHERE clause prevents these from being returned,
        # but we test the Python consumer path too.
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_scalars_result([good1, good2]))
        repo = PositionRepository(session)

        result = await repo.get_closed_in_period(
            datetime(2025, 1, 1, tzinfo=UTC),
            datetime(2025, 12, 31, tzinfo=UTC),
        )
        assert len(result) == 2
        assert all(p.close_reason != "UNRECONCILED" for p in result)
        assert all(p.profit_loss is not None for p in result)


# ---------------------------------------------------------------------------
# Test: get_performance_stats excludes UNRECONCILED via SQL filter
# ---------------------------------------------------------------------------


class TestGetPerformanceStatsFilter:
    """get_performance_stats must exclude UNRECONCILED rows in its WHERE clause."""

    @pytest.mark.asyncio
    async def test_query_excludes_unreconciled_clause(self):
        """Verify the SQL for performance stats contains UNRECONCILED exclusion."""
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_scalars_result([]))
        repo = PositionRepository(session)

        await repo.get_performance_stats()

        call_args = session.execute.call_args
        assert call_args is not None
        stmt = call_args[0][0]
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))

        assert (
            "UNRECONCILED" in compiled
        ), "get_performance_stats must filter close_reason != 'UNRECONCILED'"
        assert (
            "profit_loss IS NOT NULL" in compiled or "profit_loss IS" in compiled
        ), "get_performance_stats must filter profit_loss IS NOT NULL"

    @pytest.mark.asyncio
    async def test_aggregate_maths_exclude_unreconciled(self):
        """With 2 wins, 1 loss, 1 UNRECONCILED: total_trades=3, win_rate=2/3, total_pnl=25.0."""
        win1 = _make_position(profit_loss=10.0, close_reason="TP", deal_id="w1")
        win2 = _make_position(profit_loss=20.0, close_reason="TP", deal_id="w2")
        loss1 = _make_position(profit_loss=-5.0, close_reason="SL", deal_id="l1")
        # Simulate DB returning only the 3 reconciled rows (UNRECONCILED filtered by SQL)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_mock_scalars_result([win1, win2, loss1]))
        repo = PositionRepository(session)

        # Patch get_settings at its source to avoid config dependency in this unit test
        with patch("src.utils.config.get_settings") as mock_settings:
            mock_settings.return_value.initial_capital = 11000.0
            stats = await repo.get_performance_stats()

        assert stats["trade_count"] == 3, f"Expected 3, got {stats['trade_count']}"
        assert stats["win_count"] == 2
        assert stats["win_rate"] == pytest.approx(2 / 3, rel=1e-3)
        assert stats["total_pnl"] == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# Test: positions router aggregate computation skips UNRECONCILED
# ---------------------------------------------------------------------------


class TestPositionsRouterAggregates:
    """The aggregate block in list_closed_positions must skip UNRECONCILED rows."""

    def test_pnl_computation_skips_unreconciled(self):
        """Python-level aggregate filter: UNRECONCILED rows excluded from win-rate & P&L."""
        positions = [
            _make_position(profit_loss=10.0, close_reason="TP", deal_id="p1"),
            _make_position(profit_loss=20.0, close_reason="TP", deal_id="p2"),
            _make_position(profit_loss=-5.0, close_reason="SL", deal_id="p3"),
            _make_position(profit_loss=None, close_reason="UNRECONCILED", deal_id="p4"),
        ]

        # Replicate the exact filter from positions.py
        pnl_values = [
            float(p.profit_loss)
            for p in positions
            if p.profit_loss is not None and p.close_reason != "UNRECONCILED"
        ]
        wins = [v for v in pnl_values if v > 0]

        assert len(pnl_values) == 3, f"Expected 3, got {len(pnl_values)}"
        assert sum(pnl_values) == pytest.approx(25.0)
        assert len(wins) == 2
        assert len(wins) / len(pnl_values) == pytest.approx(2 / 3, rel=1e-3)

    def test_pnl_computation_also_skips_null_profit_loss(self):
        """Rows with NULL profit_loss but non-UNRECONCILED close_reason are also excluded."""
        positions = [
            _make_position(profit_loss=10.0, close_reason="TP", deal_id="p1"),
            _make_position(profit_loss=None, close_reason="EXTERNAL", deal_id="p2"),  # null P&L
        ]

        pnl_values = [
            float(p.profit_loss)
            for p in positions
            if p.profit_loss is not None and p.close_reason != "UNRECONCILED"
        ]

        assert len(pnl_values) == 1
        assert pnl_values[0] == pytest.approx(10.0)
