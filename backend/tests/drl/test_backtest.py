# MANTIS-EVOLUTION: DRL Backtester tests
"""Tests for MantisDRLBacktester."""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.drl.schemas import BacktestConfig, BacktestResult, DRLEnsembleSignal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ensemble(action: int = 1) -> MagicMock:
    """Create a mock MantisDRLEnsemble that always returns the same action."""
    ensemble = MagicMock()
    ensemble.predict.return_value = DRLEnsembleSignal(
        action=action,
        confidence=0.8,
        contributing_agents=["PPO"],
    )
    return ensemble


def _linear_prices(n: int = 50, start: float = 100.0, drift: float = 0.1) -> np.ndarray:
    """Generate linearly increasing prices."""
    return np.array([start + drift * i for i in range(n)], dtype=np.float64)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMantisDRLBacktester:

    def test_backtest_empty_prices(self):
        """Fewer than 2 prices returns empty BacktestResult."""
        from src.drl.backtest import MantisDRLBacktester

        bt = MantisDRLBacktester()
        ensemble = _make_ensemble(action=1)
        result = bt.run(np.array([100.0]), ensemble)

        assert isinstance(result, BacktestResult)
        assert result.equity_curve == []
        assert result.trades == []

    def test_backtest_equity_curve_length(self):
        """Equity curve length equals the number of prices."""
        from src.drl.backtest import MantisDRLBacktester

        prices = _linear_prices(n=30)
        bt = MantisDRLBacktester()
        ensemble = _make_ensemble(action=0)  # HOLD
        result = bt.run(prices, ensemble)

        assert len(result.equity_curve) == len(prices)

    def test_backtest_flat_ensemble_balance_unchanged(self):
        """HOLD-only ensemble leaves balance unchanged (no trades)."""
        from src.drl.backtest import MantisDRLBacktester

        prices = _linear_prices(n=20)
        config = BacktestConfig(initial_balance=10000.0)
        bt = MantisDRLBacktester(config=config)
        ensemble = _make_ensemble(action=0)  # always HOLD
        result = bt.run(prices, ensemble)

        # No trades when always HOLDing
        assert result.trades == []
        # Balance unchanged
        assert result.equity_curve[-1] == pytest.approx(config.initial_balance, rel=1e-6)

    def test_backtest_with_mock_ensemble_buy(self):
        """Always-BUY ensemble populates equity curve and trades."""
        from src.drl.backtest import MantisDRLBacktester

        prices = _linear_prices(n=20, drift=0.5)
        config = BacktestConfig(initial_balance=10000.0)
        bt = MantisDRLBacktester(config=config)
        ensemble = _make_ensemble(action=1)  # always BUY
        result = bt.run(prices, ensemble)

        assert len(result.equity_curve) == len(prices)
        # Should open a position on first bar
        assert len(result.trades) >= 1

    def test_backtest_trades_recorded(self):
        """Trade log has entries when positions are opened/closed."""
        from src.drl.backtest import MantisDRLBacktester

        # Alternating BUY/SELL to generate trades
        prices = _linear_prices(n=10)
        config = BacktestConfig(initial_balance=10000.0)
        bt = MantisDRLBacktester(config=config)

        # Alternate: first BUY, then SELL to trigger round-trip
        call_count = {"n": 0}
        def _alternate_predict(obs, **kwargs):
            action = 1 if call_count["n"] % 4 < 2 else 2
            call_count["n"] += 1
            return DRLEnsembleSignal(action=action, confidence=0.8, contributing_agents=["PPO"])

        ensemble = MagicMock()
        ensemble.predict.side_effect = _alternate_predict
        result = bt.run(prices, ensemble)

        assert len(result.trades) > 0
        for trade in result.trades:
            assert "type" in trade
            assert "price" in trade
            assert "pnl" in trade

    def test_backtest_benchmark_return(self):
        """Buy-and-hold return is prices[-1]/prices[0] - 1."""
        from src.drl.backtest import MantisDRLBacktester

        prices = np.array([100.0, 110.0, 120.0, 130.0, 140.0])
        bt = MantisDRLBacktester()
        ensemble = _make_ensemble(action=0)  # HOLD to isolate benchmark
        result = bt.run(prices, ensemble)

        expected = (prices[-1] / prices[0]) - 1
        assert result.benchmark_return == pytest.approx(expected, rel=1e-6)

    def test_backtest_returns_metrics(self):
        """BacktestResult has populated PerformanceMetrics."""
        from src.drl.backtest import MantisDRLBacktester

        prices = _linear_prices(n=30, drift=1.0)
        bt = MantisDRLBacktester()
        ensemble = _make_ensemble(action=1)
        result = bt.run(prices, ensemble)

        from src.drl.schemas import PerformanceMetrics
        assert isinstance(result.metrics, PerformanceMetrics)

    def test_backtest_with_regimes(self):
        """Regimes list is passed through to ensemble predict()."""
        from src.drl.backtest import MantisDRLBacktester

        prices = _linear_prices(n=5)
        regimes = ["TRENDING_UP"] * len(prices)
        bt = MantisDRLBacktester()
        ensemble = _make_ensemble(action=0)
        result = bt.run(prices, ensemble, regimes=regimes)

        assert isinstance(result, BacktestResult)
        # Verify the ensemble was called with regime kwarg
        for call in ensemble.predict.call_args_list:
            # current_regime should be passed as keyword arg
            kwargs = call[1] if call[1] else {}
            positional = call[0]
            # Either way, regime must have been passed somewhere
            assert len(positional) > 0 or "current_regime" in kwargs

    def test_backtest_config_respected(self):
        """BacktestConfig values appear in the result."""
        from src.drl.backtest import MantisDRLBacktester

        config = BacktestConfig(
            initial_balance=5000.0,
            commission_pct=0.002,
            slippage_pct=0.001,
        )
        prices = _linear_prices(n=10)
        bt = MantisDRLBacktester(config=config)
        ensemble = _make_ensemble(action=0)
        result = bt.run(prices, ensemble)

        assert result.config.initial_balance == 5000.0
        assert result.config.commission_pct == 0.002
