"""Tests for AssetPerformanceTracker (rolling Sharpe-based asset exclusion)."""

from datetime import datetime, timedelta, timezone

import pytest

from src.risk.asset_performance_tracker import AssetPerformanceTracker


class TestAssetPerformanceTracker:
    """Test rolling per-asset Sharpe exclusion logic."""

    def test_no_trades_not_excluded(self):
        """Asset with no trades should never be excluded."""
        tracker = AssetPerformanceTracker()
        excluded, sharpe = tracker.is_excluded("XAUUSD")
        assert excluded is False
        assert sharpe == 0.0

    def test_fewer_than_min_trades_not_excluded(self):
        """Asset with fewer than min_trades should not be excluded."""
        tracker = AssetPerformanceTracker(min_trades=5)
        now = datetime.now(timezone.utc)
        for i in range(4):
            tracker.record_trade("XAUUSD", -10.0, now - timedelta(hours=i))
        excluded, sharpe = tracker.is_excluded("XAUUSD")
        assert excluded is False

    def test_consistently_losing_asset_excluded(self):
        """Asset with strongly negative Sharpe should be excluded."""
        tracker = AssetPerformanceTracker(min_trades=5, sharpe_threshold=-0.5)
        now = datetime.now(timezone.utc)
        # 10 trades, all losses of varying amounts
        for i in range(10):
            tracker.record_trade("BTCUSD", -5.0 - i, now - timedelta(hours=i))
        excluded, sharpe = tracker.is_excluded("BTCUSD")
        assert excluded is True
        assert sharpe < -0.5

    def test_profitable_asset_not_excluded(self):
        """Asset with positive Sharpe should not be excluded."""
        tracker = AssetPerformanceTracker(min_trades=5, sharpe_threshold=-0.5)
        now = datetime.now(timezone.utc)
        for i in range(10):
            tracker.record_trade("US500", 10.0 + i * 0.5, now - timedelta(hours=i))
        excluded, sharpe = tracker.is_excluded("US500")
        assert excluded is False
        assert sharpe > 0

    def test_old_trades_excluded_from_calculation(self):
        """Trades older than lookback_days should not affect the calculation."""
        tracker = AssetPerformanceTracker(lookback_days=7, min_trades=3)
        now = datetime.now(timezone.utc)
        # Old losing trades (8+ days ago)
        for i in range(5):
            tracker.record_trade("XAUUSD", -20.0, now - timedelta(days=10 + i))
        # Recent winning trades
        for i in range(5):
            tracker.record_trade("XAUUSD", 15.0, now - timedelta(hours=i))
        excluded, sharpe = tracker.is_excluded("XAUUSD")
        assert excluded is False

    def test_get_all_sharpes(self):
        """get_all_sharpes returns Sharpe for all tracked assets with enough data."""
        tracker = AssetPerformanceTracker(min_trades=3)
        now = datetime.now(timezone.utc)
        for i in range(5):
            tracker.record_trade("XAUUSD", 10.0 + i, now - timedelta(hours=i))
            tracker.record_trade("BTCUSD", -8.0 - i, now - timedelta(hours=i))
        # Only 2 trades — should not appear
        tracker.record_trade("EURUSD", 5.0, now)
        tracker.record_trade("EURUSD", -3.0, now - timedelta(hours=1))

        sharpes = tracker.get_all_sharpes()
        assert "XAUUSD" in sharpes
        assert "BTCUSD" in sharpes
        assert "EURUSD" not in sharpes  # < min_trades

    def test_reset_clears_all_data(self):
        """reset() should clear all tracked trades."""
        tracker = AssetPerformanceTracker(min_trades=1)
        now = datetime.now(timezone.utc)
        for i in range(5):
            tracker.record_trade("XAUUSD", -10.0, now - timedelta(hours=i))
        tracker.reset()
        excluded, _ = tracker.is_excluded("XAUUSD")
        assert excluded is False
        assert tracker.get_all_sharpes() == {}
