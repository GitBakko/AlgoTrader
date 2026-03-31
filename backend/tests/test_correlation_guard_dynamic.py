"""Tests for dynamic CorrelationGuard."""

import numpy as np

from src.risk.correlation_guard import CorrelationGuard


class TestDynamicCorrelationGuard:
    def test_static_fallback_when_no_matrix(self):
        """Without a dynamic matrix, falls back to hardcoded pairs."""
        multiplier, warnings = CorrelationGuard.check_exposure(
            epic="XAGUSD",
            direction="BUY",
            open_positions=[{"epic": "XAUUSD", "direction": "BUY"}],
        )
        assert multiplier < 0.20

    def test_dynamic_matrix_overrides_static(self):
        """When a correlation matrix is provided, it overrides hardcoded pairs."""
        epics = ["XAGUSD", "XAUUSD"]
        matrix = np.array([[1.0, 0.3], [0.3, 1.0]])
        guard = CorrelationGuard()
        guard.update_matrix(epics, matrix)
        multiplier, warnings = guard.check_exposure_dynamic(
            epic="XAGUSD",
            direction="BUY",
            open_positions=[{"epic": "XAUUSD", "direction": "BUY"}],
        )
        assert 0.65 <= multiplier <= 0.75

    def test_high_dynamic_correlation_reduces_more(self):
        epics = ["BTCUSD", "ETHUSD"]
        matrix = np.array([[1.0, 0.95], [0.95, 1.0]])
        guard = CorrelationGuard()
        guard.update_matrix(epics, matrix)
        multiplier, _ = guard.check_exposure_dynamic(
            epic="ETHUSD",
            direction="BUY",
            open_positions=[{"epic": "BTCUSD", "direction": "BUY"}],
        )
        assert multiplier < 0.15

    def test_opposite_directions_no_penalty(self):
        epics = ["BTCUSD", "ETHUSD"]
        matrix = np.array([[1.0, 0.90], [0.90, 1.0]])
        guard = CorrelationGuard()
        guard.update_matrix(epics, matrix)
        multiplier, _ = guard.check_exposure_dynamic(
            epic="ETHUSD",
            direction="SELL",
            open_positions=[{"epic": "BTCUSD", "direction": "BUY"}],
        )
        assert multiplier == 1.0

    def test_multiple_correlated_positions(self):
        epics = ["BTCUSD", "ETHUSD", "SOLUSD"]
        matrix = np.array(
            [
                [1.0, 0.85, 0.80],
                [0.85, 1.0, 0.75],
                [0.80, 0.75, 1.0],
            ]
        )
        guard = CorrelationGuard()
        guard.update_matrix(epics, matrix)
        multiplier, _ = guard.check_exposure_dynamic(
            epic="SOLUSD",
            direction="BUY",
            open_positions=[
                {"epic": "BTCUSD", "direction": "BUY"},
                {"epic": "ETHUSD", "direction": "BUY"},
            ],
        )
        assert multiplier < 0.25
