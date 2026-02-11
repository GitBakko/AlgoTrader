"""Tests for backtest engine."""

from datetime import datetime, timedelta

import numpy as np
import polars as pl
import pytest

from src.backtest.engine import BacktestEngine
from src.backtest.schemas import BacktestConfig, TradeDirection
from src.models.schemas import SignalClass


@pytest.fixture
def sample_config():
    return BacktestConfig(
        epic="XAUUSD",
        timeframe="1h",
        start_date=datetime(2024, 1, 1),
        end_date=datetime(2024, 2, 1),
        initial_capital=10000.0,
        risk_per_trade=0.02,
        atr_sl_multiplier=2.0,
        atr_tp_multiplier=3.0,
        include_costs=False,
    )


@pytest.fixture
def uptrend_data():
    """OHLC data with clear uptrend."""
    n = 100
    base = 2000.0
    timestamps = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)]

    close = [base + i * 2.0 for i in range(n)]
    high = [c + 5.0 for c in close]
    low = [c - 5.0 for c in close]
    open_price = [c - 1.0 for c in close]

    return pl.DataFrame({
        "timestamp": timestamps,
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": [1000] * n,
    })


@pytest.fixture
def buy_signals(uptrend_data):
    """All-BUY signals aligned with uptrend data."""
    timestamps = uptrend_data["timestamp"].to_list()
    return pl.DataFrame({
        "timestamp": timestamps,
        "signal": [SignalClass.BUY if i == 5 else SignalClass.HOLD for i in range(len(timestamps))],
        "atr": [10.0] * len(timestamps),
    })


class TestBacktestEngine:
    def test_basic_run(self, sample_config, uptrend_data, buy_signals):
        engine = BacktestEngine(sample_config)
        result = engine.run(uptrend_data, buy_signals)

        assert result.total_bars == len(uptrend_data)
        assert result.start_equity == 10000.0
        assert len(result.equity_curve) == len(uptrend_data)

    def test_buy_in_uptrend_profitable(self, sample_config, uptrend_data, buy_signals):
        """Buying in an uptrend should be profitable."""
        engine = BacktestEngine(sample_config)
        result = engine.run(uptrend_data, buy_signals)

        # Should have at least one trade
        assert result.total_trades >= 1
        # Should be profitable in an uptrend
        assert result.end_equity >= result.start_equity

    def test_no_signals_no_trades(self, sample_config, uptrend_data):
        """All HOLD signals should produce no trades."""
        timestamps = uptrend_data["timestamp"].to_list()
        hold_signals = pl.DataFrame({
            "timestamp": timestamps,
            "signal": [SignalClass.HOLD] * len(timestamps),
        })

        engine = BacktestEngine(sample_config)
        result = engine.run(uptrend_data, hold_signals)

        assert result.total_trades == 0
        assert result.end_equity == result.start_equity

    def test_positions_closed_at_end(self, sample_config, uptrend_data, buy_signals):
        """All positions should be closed at end of backtest."""
        engine = BacktestEngine(sample_config)
        result = engine.run(uptrend_data, buy_signals)

        # All trades should have exit prices
        for trade in result.trades:
            assert trade.exit_price is not None
            assert trade.exit_time is not None

    def test_stop_loss_triggered(self, sample_config):
        """Price dropping below SL should close position."""
        n = 20
        timestamps = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)]

        # Price starts at 2000, drops sharply after bar 5
        close = [2000.0] * 5 + [2000.0 - i * 20.0 for i in range(1, 16)]
        high = [c + 5.0 for c in close]
        low = [c - 5.0 for c in close]

        ohlc = pl.DataFrame({
            "timestamp": timestamps,
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1000] * n,
        })

        signals = pl.DataFrame({
            "timestamp": timestamps,
            "signal": [SignalClass.BUY if i == 2 else SignalClass.HOLD for i in range(n)],
            "atr": [10.0] * n,  # SL at 2.0 * 10 = 20 below entry
        })

        engine = BacktestEngine(sample_config)
        result = engine.run(ohlc, signals)

        # Should have a SL exit
        sl_trades = [t for t in result.trades if t.status == "closed_sl"]
        assert len(sl_trades) >= 1

    def test_result_has_metrics(self, sample_config, uptrend_data, buy_signals):
        engine = BacktestEngine(sample_config)
        result = engine.run(uptrend_data, buy_signals)

        assert "total_return" in result.metrics
        assert "sharpe_ratio" in result.metrics
        assert "max_drawdown" in result.metrics
        assert "win_rate" in result.metrics

    def test_empty_data_raises(self, sample_config):
        engine = BacktestEngine(sample_config)
        with pytest.raises(ValueError, match="empty"):
            engine.run(pl.DataFrame(), pl.DataFrame())

    def test_sell_signal_opens_short(self, sample_config):
        """SELL signal should open a SHORT position."""
        n = 20
        timestamps = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)]
        close = [2000.0 - i * 2.0 for i in range(n)]  # Downtrend
        high = [c + 5.0 for c in close]
        low = [c - 5.0 for c in close]

        ohlc = pl.DataFrame({
            "timestamp": timestamps,
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1000] * n,
        })

        signals = pl.DataFrame({
            "timestamp": timestamps,
            "signal": [SignalClass.SELL if i == 2 else SignalClass.HOLD for i in range(n)],
            "atr": [10.0] * n,
        })

        engine = BacktestEngine(sample_config)
        result = engine.run(ohlc, signals)

        # Should have at least one short trade
        short_trades = [t for t in result.trades if t.direction == "SHORT"]
        assert len(short_trades) >= 1
