"""Tests for backtest metrics calculator."""

import math
from datetime import datetime, timedelta

import numpy as np
import pytest

from src.backtest.metrics import MetricsCalculator
from src.backtest.schemas import BacktestTrade, TradeDirection, TradeStatus


def _make_equity_curve(equities: list[float], start: datetime | None = None) -> list[dict]:
    """Helper: create equity curve with timestamps (one per day)."""
    if start is None:
        start = datetime(2024, 1, 1)
    return [
        {"equity": eq, "timestamp": start + timedelta(days=i)}
        for i, eq in enumerate(equities)
    ]


@pytest.fixture
def profitable_equity():
    """Equity curve with steady growth (daily points)."""
    return _make_equity_curve([10000.0 + i * 10.0 for i in range(100)])


@pytest.fixture
def losing_equity():
    """Equity curve with decline (daily points)."""
    return _make_equity_curve([10000.0 - i * 10.0 for i in range(100)])


@pytest.fixture
def sample_trades():
    """Mix of winning and losing trades."""
    return [
        BacktestTrade(
            trade_id=1, epic="XAUUSD", direction=TradeDirection.LONG,
            entry_price=2000, entry_time=datetime(2024, 1, 1),
            exit_price=2050, exit_time=datetime(2024, 1, 2),
            size=1.0, status=TradeStatus.CLOSED_TP, pnl=50.0, fees=1.0, net_pnl=49.0,
            bars_held=6,
        ),
        BacktestTrade(
            trade_id=2, epic="XAUUSD", direction=TradeDirection.LONG,
            entry_price=2050, entry_time=datetime(2024, 1, 3),
            exit_price=2030, exit_time=datetime(2024, 1, 4),
            size=1.0, status=TradeStatus.CLOSED_SL, pnl=-20.0, fees=1.0, net_pnl=-21.0,
            bars_held=4,
        ),
        BacktestTrade(
            trade_id=3, epic="XAUUSD", direction=TradeDirection.SHORT,
            entry_price=2030, entry_time=datetime(2024, 1, 5),
            exit_price=2000, exit_time=datetime(2024, 1, 6),
            size=1.0, status=TradeStatus.CLOSED_TP, pnl=30.0, fees=1.0, net_pnl=29.0,
            bars_held=8,
        ),
    ]


class TestMetricsCalculator:
    def test_empty_equity(self):
        metrics = MetricsCalculator.calculate_all([], [], 10000.0)
        assert metrics["total_return"] == 0.0
        assert metrics["total_trades"] == 0

    def test_profitable_returns(self, profitable_equity):
        metrics = MetricsCalculator.calculate_all(
            profitable_equity, [], 10000.0
        )
        assert metrics["total_return"] > 0.0
        assert metrics["end_equity"] > 10000.0

    def test_losing_returns(self, losing_equity):
        metrics = MetricsCalculator.calculate_all(
            losing_equity, [], 10000.0
        )
        assert metrics["total_return"] < 0.0

    def test_max_drawdown(self):
        equity = _make_equity_curve([10000.0, 10200.0, 9800.0, 10100.0])
        metrics = MetricsCalculator.calculate_all(equity, [], 10000.0)
        # Max DD = (10200 - 9800) / 10200 = ~3.9%
        expected_dd = (10200 - 9800) / 10200
        assert abs(metrics["max_drawdown"] - expected_dd) < 0.01

    def test_sharpe_ratio_positive(self, profitable_equity):
        metrics = MetricsCalculator.calculate_all(
            profitable_equity, [], 10000.0
        )
        assert metrics["sharpe_ratio"] > 0.0

    def test_sharpe_uses_daily_returns(self):
        """Sharpe should be based on daily returns, not per-bar.

        With hourly data (24 bars/day), using per-bar returns inflates Sharpe
        because many bars have zero return when no position is open.
        Daily resampling eliminates this bias.
        """
        np.random.seed(42)
        start = datetime(2024, 1, 1)
        hourly_equity = []
        equity = 10000.0
        # 60 days × 24 hours = 1440 bars with random walk (slight upward drift)
        for day in range(60):
            for hour in range(24):
                # Drift + noise: equity changes each hour
                equity *= 1.0 + np.random.normal(0.00005, 0.001)
                hourly_equity.append({
                    "equity": equity,
                    "timestamp": start + timedelta(days=day, hours=hour),
                })

        metrics = MetricsCalculator.calculate_all(
            hourly_equity, [], 10000.0, bars_per_day=24.0,
        )

        # Daily Sharpe should be reasonable (not inflated to hundreds/thousands)
        # A typical good strategy has Sharpe 1-3, annualized
        assert -10 < metrics["sharpe_ratio"] < 10

    def test_daily_resampling(self):
        """_resample_to_daily should take last equity per day."""
        start = datetime(2024, 1, 1)
        equity_curve = [
            {"equity": 10000.0, "timestamp": start + timedelta(hours=0)},
            {"equity": 10010.0, "timestamp": start + timedelta(hours=6)},
            {"equity": 10020.0, "timestamp": start + timedelta(hours=12)},
            {"equity": 10030.0, "timestamp": start + timedelta(hours=18)},  # EOD day 0
            {"equity": 10040.0, "timestamp": start + timedelta(days=1, hours=0)},
            {"equity": 10050.0, "timestamp": start + timedelta(days=1, hours=12)},  # EOD day 1
        ]

        daily = MetricsCalculator._resample_to_daily(equity_curve)
        assert len(daily) == 2  # 2 days
        assert daily[0] == 10030.0  # Last of day 0
        assert daily[1] == 10050.0  # Last of day 1

    def test_trade_metrics(self, sample_trades):
        equity = _make_equity_curve([10000.0 + i * 5.0 for i in range(50)])
        metrics = MetricsCalculator.calculate_all(
            equity, sample_trades, 10000.0
        )
        assert metrics["total_trades"] == 3
        assert metrics["winning_trades"] == 2
        assert metrics["losing_trades"] == 1
        assert metrics["win_rate"] == pytest.approx(2 / 3)

    def test_profit_factor(self, sample_trades):
        equity = _make_equity_curve([10000.0] * 10)
        metrics = MetricsCalculator.calculate_all(
            equity, sample_trades, 10000.0
        )
        # Wins: 49 + 29 = 78, Loss: 21
        assert metrics["profit_factor"] == pytest.approx(78 / 21, rel=0.01)

    def test_consecutive_wins_losses(self):
        trades = [
            BacktestTrade(
                trade_id=i, epic="XAUUSD", direction=TradeDirection.LONG,
                entry_price=100, entry_time=datetime(2024, 1, i + 1),
                size=1.0, status=TradeStatus.CLOSED_TP,
                pnl=10.0 if i < 3 else -5.0,
                net_pnl=10.0 if i < 3 else -5.0,
                bars_held=1,
            )
            for i in range(5)
        ]
        equity = _make_equity_curve([10000.0] * 10)
        metrics = MetricsCalculator.calculate_all(equity, trades, 10000.0)
        assert metrics["max_consecutive_wins"] == 3
        assert metrics["max_consecutive_losses"] == 2

    def test_no_timestamp_fallback(self):
        """Should fall back to per-bar returns if no timestamps in equity curve."""
        equity = [{"equity": 10000.0 + i * 10.0} for i in range(50)]
        metrics = MetricsCalculator.calculate_all(equity, [], 10000.0)
        # Should still work, just without daily resampling
        assert metrics["sharpe_ratio"] > 0.0
