"""Tests for slippage tracker module."""

import pytest

from src.execution.slippage_tracker import SlippageTracker


class TestSlippageTracker:
    def test_empty_stats(self):
        tracker = SlippageTracker()
        assert tracker.get_stats() == {}
        assert tracker.get_average_slippage() == 0.0

    def test_record_and_average(self):
        tracker = SlippageTracker()
        tracker.record_slippage("XAUUSD", 2000.0, 2000.5, "BUY")
        tracker.record_slippage("XAUUSD", 2000.0, 2001.0, "BUY")
        avg = tracker.get_average_slippage("XAUUSD")
        assert avg == pytest.approx(0.75)  # (0.5 + 1.0) / 2

    def test_average_by_epic(self):
        tracker = SlippageTracker()
        tracker.record_slippage("XAUUSD", 2000.0, 2000.5, "BUY")
        tracker.record_slippage("BTCUSD", 50000.0, 50010.0, "BUY")
        assert tracker.get_average_slippage("XAUUSD") == pytest.approx(0.5)
        assert tracker.get_average_slippage("BTCUSD") == pytest.approx(10.0)

    def test_stats_per_epic(self):
        tracker = SlippageTracker()
        tracker.record_slippage("XAUUSD", 2000.0, 2000.5, "BUY")
        tracker.record_slippage("XAUUSD", 2000.0, 2001.0, "BUY")
        stats = tracker.get_stats()
        assert "XAUUSD" in stats
        assert stats["XAUUSD"]["count"] == 2
        assert stats["XAUUSD"]["max_slippage"] == pytest.approx(1.0)
        assert stats["XAUUSD"]["avg_slippage"] == pytest.approx(0.75)

    def test_reset(self):
        tracker = SlippageTracker()
        tracker.record_slippage("XAUUSD", 2000.0, 2000.5, "BUY")
        tracker.reset()
        assert tracker.get_stats() == {}
        assert tracker.get_average_slippage() == 0.0
