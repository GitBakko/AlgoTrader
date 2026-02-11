"""Tests for correlation guard module."""

import pytest

from src.risk.correlation_guard import CorrelationGuard


class TestCorrelationGuard:
    def test_no_correlation_no_positions(self):
        mult, warnings = CorrelationGuard.check_exposure("XAUUSD", "BUY", [])
        assert mult == 1.0
        assert len(warnings) == 0

    def test_no_correlation_different_assets(self):
        positions = [{"epic": "US500", "direction": "BUY"}]
        mult, warnings = CorrelationGuard.check_exposure("XAUUSD", "BUY", positions)
        assert mult == 1.0

    def test_gold_btc_same_direction(self):
        positions = [{"epic": "BTCUSD", "direction": "BUY"}]
        mult, warnings = CorrelationGuard.check_exposure("XAUUSD", "BUY", positions)
        assert mult == pytest.approx(0.50)
        assert len(warnings) == 1

    def test_gold_btc_opposite_direction(self):
        positions = [{"epic": "BTCUSD", "direction": "SELL"}]
        mult, warnings = CorrelationGuard.check_exposure("XAUUSD", "BUY", positions)
        assert mult == 1.0
        assert len(warnings) == 0

    def test_btc_sp500_same_direction(self):
        positions = [{"epic": "US500", "direction": "SELL"}]
        mult, warnings = CorrelationGuard.check_exposure("BTCUSD", "SELL", positions)
        assert mult == pytest.approx(0.70)

    def test_reverse_pair_works(self):
        """BTC checking against Gold should work the same as Gold against BTC."""
        positions = [{"epic": "XAUUSD", "direction": "SELL"}]
        mult, warnings = CorrelationGuard.check_exposure("BTCUSD", "SELL", positions)
        assert mult == pytest.approx(0.50)

    def test_uncorrelated_asset(self):
        """Asset not in any correlation pair should get no reduction."""
        positions = [{"epic": "XAUUSD", "direction": "BUY"}, {"epic": "BTCUSD", "direction": "BUY"}]
        mult, warnings = CorrelationGuard.check_exposure("EURUSD", "BUY", positions)
        assert mult == 1.0
