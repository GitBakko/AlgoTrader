"""
Tests for equity curve filter.
"""

import pytest

from src.risk.equity_curve_filter import EquityCurveConfig, EquityCurveFilter


@pytest.mark.unit
@pytest.mark.risk
class TestEquityCurveFilter:
    """Tests for EquityCurveFilter."""

    def test_no_data_returns_1(self):
        """No trade data -> multiplier = 1.0."""
        f = EquityCurveFilter()
        assert f.get_size_multiplier() == 1.0
        assert f.is_below_sma is False

    def test_insufficient_trades(self):
        """Below min_trades_to_activate -> multiplier = 1.0."""
        f = EquityCurveFilter(EquityCurveConfig(min_trades_to_activate=10))
        for i in range(9):
            f.record_trade_close(10000 - i * 100)
        assert f.get_size_multiplier() == 1.0

    def test_equity_above_sma(self):
        """Equity above SMA -> multiplier = 1.0."""
        f = EquityCurveFilter(EquityCurveConfig(sma_window=5, min_trades_to_activate=5))
        for v in [10000, 10100, 10200, 10300, 10400]:
            f.record_trade_close(v)
        # Rising equity, current > SMA
        assert f.get_size_multiplier() == 1.0
        assert f.is_below_sma is False

    def test_equity_below_sma_reduces(self):
        """Equity below SMA -> multiplier = reduction_factor."""
        cfg = EquityCurveConfig(sma_window=5, min_trades_to_activate=5, reduction_factor=0.5)
        f = EquityCurveFilter(cfg)
        # Rising then falling
        for v in [10000, 10200, 10400, 10300, 9800]:
            f.record_trade_close(v)
        # SMA of [10000,10200,10400,10300,9800] = 10140
        # Current 9800 < 10140 -> should reduce
        assert f.get_size_multiplier() == 0.5
        assert f.is_below_sma is True

    def test_sma_value(self):
        """SMA computation is correct."""
        cfg = EquityCurveConfig(sma_window=5, min_trades_to_activate=5)
        f = EquityCurveFilter(cfg)
        for v in [100, 200, 300, 400, 500]:
            f.record_trade_close(v)
        assert f.sma_value == pytest.approx(300.0)

    def test_sma_none_when_insufficient(self):
        """SMA is None when fewer points than window."""
        cfg = EquityCurveConfig(sma_window=20)
        f = EquityCurveFilter(cfg)
        f.record_trade_close(100)
        assert f.sma_value is None

    def test_trade_count(self):
        """trade_count tracks recorded closes."""
        f = EquityCurveFilter()
        assert f.trade_count == 0
        f.record_trade_close(100)
        f.record_trade_close(200)
        assert f.trade_count == 2

    def test_get_status(self):
        """get_status returns expected keys."""
        f = EquityCurveFilter()
        status = f.get_status()
        assert "trade_count" in status
        assert "sma_value" in status
        assert "is_below_sma" in status
        assert "size_multiplier" in status

    def test_recovery_above_sma(self):
        """After recovering above SMA, multiplier returns to 1.0."""
        cfg = EquityCurveConfig(sma_window=5, min_trades_to_activate=5, reduction_factor=0.5)
        f = EquityCurveFilter(cfg)
        # Start below
        for v in [10000, 10200, 10400, 10300, 9800]:
            f.record_trade_close(v)
        assert f.get_size_multiplier() == 0.5

        # Now recover
        f.record_trade_close(10500)
        f.record_trade_close(10600)
        # Should be above SMA now
        assert f.get_size_multiplier() == 1.0

    def test_custom_reduction_factor(self):
        """Custom reduction factor is applied."""
        cfg = EquityCurveConfig(sma_window=5, min_trades_to_activate=5, reduction_factor=0.3)
        f = EquityCurveFilter(cfg)
        for v in [100, 100, 100, 100, 50]:
            f.record_trade_close(v)
        # SMA of [100,100,100,100,50] = 90, current 50 < 90 -> should reduce
        assert f.get_size_multiplier() == 0.3
