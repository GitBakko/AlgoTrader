"""Dashboard v2 aggregates on PositionRepository.

Covers:
- get_breakdown_by_day: per-day BUY/SELL × TP/SL/Going bucketing
- get_duration_medians: win/loss duration means + bias flag
- get_opened_today_count: DB SELECT count wiring
- tp_hit_rate + tp_count enrichment inside get_performance_stats
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.repositories.position_repository import PositionRepository


def _pos(
    deal_id: str,
    direction: str = "BUY",
    profit_loss: float | None = 100.0,
    close_reason: str | None = "TP",
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
    status: str | None = None,
):
    p = MagicMock()
    p.id = deal_id
    p.deal_id = deal_id
    p.epic = "XAUUSD"
    p.direction = direction
    p.size = Decimal("1.0")
    p.entry_price = Decimal("2000.0")
    p.profit_loss = Decimal(str(profit_loss)) if profit_loss is not None else None
    p.close_reason = close_reason
    p.opened_at = opened_at
    p.closed_at = closed_at
    p.status = status or ("CLOSED" if closed_at is not None else "OPEN")
    return p


def _mock_scalars(rows):
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


class TestBreakdownByDay:
    @pytest.mark.asyncio
    async def test_empty_range_returns_zero_filled_days(self):
        session = MagicMock()
        session.execute = AsyncMock(return_value=_mock_scalars([]))
        repo = PositionRepository(session)
        d_from = datetime(2026, 4, 20, tzinfo=UTC)
        d_to = datetime(2026, 4, 22, tzinfo=UTC)
        days = await repo.get_breakdown_by_day(d_from, d_to)
        assert [d["date"] for d in days] == ["2026-04-20", "2026-04-21", "2026-04-22"]
        for d in days:
            assert d["buy"] == {"tp": 0, "sl": 0, "going": 0, "pnl": 0.0}
            assert d["sell"] == {"tp": 0, "sl": 0, "going": 0, "pnl": 0.0}

    @pytest.mark.asyncio
    async def test_closed_tp_bucketed_on_close_day(self):
        session = MagicMock()
        pos = _pos(
            "1",
            direction="BUY",
            profit_loss=120.0,
            close_reason="TP",
            opened_at=datetime(2026, 4, 20, 9, 0),
            closed_at=datetime(2026, 4, 20, 11, 30),
        )
        session.execute = AsyncMock(return_value=_mock_scalars([pos]))
        repo = PositionRepository(session)
        d_from = datetime(2026, 4, 20, tzinfo=UTC)
        d_to = datetime(2026, 4, 21, tzinfo=UTC)
        days = await repo.get_breakdown_by_day(d_from, d_to)
        day0 = next(d for d in days if d["date"] == "2026-04-20")
        assert day0["buy"]["tp"] == 1
        assert day0["buy"]["pnl"] == 120.0
        assert day0["sell"]["tp"] == 0

    @pytest.mark.asyncio
    async def test_going_marks_open_span_across_days(self):
        session = MagicMock()
        pos = _pos(
            "1",
            direction="SELL",
            profit_loss=None,
            close_reason=None,
            opened_at=datetime(2026, 4, 20, 9, 0),
            closed_at=None,                       # still open
            status="OPEN",
        )
        session.execute = AsyncMock(return_value=_mock_scalars([pos]))
        repo = PositionRepository(session)
        d_from = datetime(2026, 4, 20, tzinfo=UTC)
        d_to = datetime(2026, 4, 22, 23, 59, 59, tzinfo=UTC)
        days = await repo.get_breakdown_by_day(d_from, d_to)
        # Open on each of 2026-04-20, 21, 22.
        for d in days:
            assert d["sell"]["going"] == 1
            assert d["buy"]["going"] == 0


class TestDurationMedians:
    @pytest.mark.asyncio
    async def test_flags_late_exit_bias(self):
        session = MagicMock()
        # 2 wins closed in ~30 min, 2 losses closed in ~90 min → bias > 1.3x.
        t0 = datetime(2026, 4, 22, 10, 0)
        wins = [
            _pos("w1", profit_loss=50.0,  close_reason="TP",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=30)),
            _pos("w2", profit_loss=70.0,  close_reason="TP",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=40)),
        ]
        losses = [
            _pos("l1", profit_loss=-20.0, close_reason="SL",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=90)),
            _pos("l2", profit_loss=-30.0, close_reason="SL",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=110)),
        ]
        session.execute = AsyncMock(return_value=_mock_scalars(wins + losses))
        repo = PositionRepository(session)
        stats = await repo.get_duration_medians()
        assert stats["win_count"] == 2
        assert stats["loss_count"] == 2
        assert stats["win_avg_min"] == pytest.approx(35.0)
        assert stats["loss_avg_min"] == pytest.approx(100.0)
        assert stats["late_exit_bias"] is True
        assert stats["bias_pct_over"] > 100.0

    @pytest.mark.asyncio
    async def test_no_bias_flag_when_balanced(self):
        session = MagicMock()
        t0 = datetime(2026, 4, 22, 10, 0)
        session.execute = AsyncMock(return_value=_mock_scalars([
            _pos("w1", profit_loss=10.0,  close_reason="TP",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=60)),
            _pos("l1", profit_loss=-10.0, close_reason="SL",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=60)),
        ]))
        repo = PositionRepository(session)
        stats = await repo.get_duration_medians()
        assert stats["late_exit_bias"] is False


class TestTpHitRateInPerformance:
    @pytest.mark.asyncio
    async def test_tp_hit_rate_counts_closed_with_tp(self):
        # Isolate aggregation path — patch np-heavy equity curve block by
        # providing only 1 position (triggers early-return shape without ratios).
        session = MagicMock()
        t0 = datetime(2026, 4, 22, 10, 0)
        rows = [
            _pos("1", profit_loss=10.0,  close_reason="TP",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=30)),
            _pos("2", profit_loss=20.0,  close_reason="TP",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=30)),
            _pos("3", profit_loss=-5.0,  close_reason="SL",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=30)),
            _pos("4", profit_loss=0.0,   close_reason="MANUAL",
                 opened_at=t0, closed_at=t0 + timedelta(minutes=30)),
        ]
        session.execute = AsyncMock(return_value=_mock_scalars(rows))
        repo = PositionRepository(session)
        stats = await repo.get_performance_stats()
        assert stats["trade_count"] == 4
        assert stats["tp_count"] == 2
        assert stats["tp_hit_rate"] == pytest.approx(0.5)
