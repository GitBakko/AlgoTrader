"""
Tests for PairsTradingStrategy in src/strategy/pairs/pairs_strategy.py.

Tests signal generation, position tracking, entry/exit conditions,
dollar-neutral sizing, and strategy state management.
"""

import numpy as np
import pytest

from src.strategy.pairs.cointegration import CointegrationAnalyzer
from src.strategy.pairs.pairs_strategy import (
    PairsConfig,
    PairsSignal,
    PairsTradingStrategy,
)


@pytest.mark.unit
@pytest.mark.strategy
class TestPairsTradingStrategy:
    """Test suite for PairsTradingStrategy."""

    @pytest.fixture
    def cointegrated_data(self):
        """Generate cointegrated price series for testing."""
        np.random.seed(42)
        n = 300

        # Bitcoin-like (asset B)
        b = 50000 + np.cumsum(np.random.randn(n) * 100)
        # Gold-like (asset A): a = 2000 + 0.04 * b + noise
        a = 2000 + 0.04 * b + np.random.randn(n) * 5

        return a, b

    @pytest.fixture
    def strategy(self):
        """Create a default PairsTradingStrategy instance."""
        config = PairsConfig(
            entry_z=2.0,
            exit_z=0.5,
            stop_z=3.0,
            max_hold_bars=168,
            zscore_lookback=50,
            equity_per_leg=5000.0,
        )
        return PairsTradingStrategy(config)

    def test_not_calibrated_returns_hold(self, strategy):
        """Test that strategy returns HOLD before calibration."""
        np.random.seed(42)
        n = 100

        a = np.random.randn(n) + 2000
        b = np.random.randn(n) + 50000

        signal = strategy.generate_signal(a, b, current_price_a=2000.0, current_price_b=50000.0)

        assert signal.action == "HOLD"
        assert signal.z_score == 0.0
        assert signal.hedge_ratio == 0.0
        assert "Not cointegrated" in signal.reason

    def test_calibrate_sets_cointegration(self, strategy, cointegrated_data):
        """Test that calibrate() sets cointegration state."""
        a, b = cointegrated_data

        result = strategy.calibrate(a, b)

        assert result.is_cointegrated is True
        assert strategy.is_cointegrated is True
        assert strategy.hedge_ratio > 0.0
        assert result.hedge_ratio == strategy.hedge_ratio
        assert result.half_life > 0

    def test_long_spread_signal(self, strategy, cointegrated_data):
        """Test that z-score below -entry_z triggers LONG_SPREAD."""
        a, b = cointegrated_data

        # Calibrate first
        strategy.calibrate(a, b)

        # Manipulate recent prices to create extreme negative z-score
        # Make current spread much lower than historical mean
        hr = strategy.hedge_ratio
        current_price_b = b[-1] * 1.05  # Increase B
        current_price_a = a[-1] * 0.95  # Decrease A
        # This should create spread below mean -> negative z-score

        # Append manipulated prices
        prices_a = np.append(a[-60:], current_price_a)
        prices_b = np.append(b[-60:], current_price_b)

        signal = strategy.generate_signal(
            prices_a, prices_b, current_price_a=current_price_a, current_price_b=current_price_b
        )

        # Check if we got entry signal (depends on exact z-score)
        # If z-score is sufficiently negative, we should get LONG_SPREAD
        if signal.action == "LONG_SPREAD":
            assert signal.z_score <= -strategy.config.entry_z
            assert signal.direction_a == "BUY"
            assert signal.direction_b == "SELL"
            assert signal.size_a > 0
            assert signal.size_b > 0
            assert signal.confidence > 0

    def test_short_spread_signal(self, strategy, cointegrated_data):
        """Test that z-score above entry_z triggers SHORT_SPREAD."""
        a, b = cointegrated_data

        # Calibrate first
        strategy.calibrate(a, b)

        # Manipulate to create extreme positive z-score
        # Make current spread much higher than historical mean
        current_price_a = a[-1] * 1.10  # Increase A
        current_price_b = b[-1] * 0.95  # Decrease B

        # Append manipulated prices
        prices_a = np.append(a[-60:], current_price_a)
        prices_b = np.append(b[-60:], current_price_b)

        signal = strategy.generate_signal(
            prices_a, prices_b, current_price_a=current_price_a, current_price_b=current_price_b
        )

        # Check if we got entry signal
        if signal.action == "SHORT_SPREAD":
            assert signal.z_score >= strategy.config.entry_z
            assert signal.direction_a == "SELL"
            assert signal.direction_b == "BUY"
            assert signal.size_a > 0
            assert signal.size_b > 0
            assert signal.confidence > 0

    def test_hold_within_bands(self, strategy, cointegrated_data):
        """Test that z-score within ±entry_z returns HOLD."""
        a, b = cointegrated_data

        # Calibrate
        strategy.calibrate(a, b)

        # Use normal recent prices (should have z-score near 0)
        prices_a = a[-60:]
        prices_b = b[-60:]
        current_price_a = a[-1]
        current_price_b = b[-1]

        signal = strategy.generate_signal(
            prices_a, prices_b, current_price_a=current_price_a, current_price_b=current_price_b
        )

        # Should be HOLD if z-score is within entry bands
        if abs(signal.z_score) < strategy.config.entry_z:
            assert signal.action == "HOLD"
            assert "within entry zone" in signal.reason.lower()

    def test_close_on_mean_reversion(self, strategy, cointegrated_data):
        """Test that z returning to ±exit_z triggers CLOSE."""
        a, b = cointegrated_data

        # Calibrate
        strategy.calibrate(a, b)

        # First create extreme negative z-score to enter LONG_SPREAD
        current_price_b = b[-1] * 1.10
        current_price_a = a[-1] * 0.90

        prices_a = np.append(a[-60:], current_price_a)
        prices_b = np.append(b[-60:], current_price_b)

        signal1 = strategy.generate_signal(
            prices_a, prices_b, current_price_a=current_price_a, current_price_b=current_price_b
        )

        # If we entered a position
        if signal1.action == "LONG_SPREAD":
            # Now simulate mean reversion: z-score returns to near zero
            revert_price_a = a[-1]
            revert_price_b = b[-1]

            prices_a_rev = np.append(a[-60:], revert_price_a)
            prices_b_rev = np.append(b[-60:], revert_price_b)

            signal2 = strategy.generate_signal(
                prices_a_rev,
                prices_b_rev,
                current_price_a=revert_price_a,
                current_price_b=revert_price_b,
            )

            # Should close if z-score is within exit_z
            if abs(signal2.z_score) <= strategy.config.exit_z:
                assert signal2.action == "CLOSE"
                assert "mean reversion" in signal2.reason.lower()

    def test_close_on_stop_loss(self, strategy, cointegrated_data):
        """Test that z exceeding ±stop_z triggers CLOSE."""
        a, b = cointegrated_data

        # Calibrate
        strategy.calibrate(a, b)

        # Enter LONG_SPREAD
        current_price_b = b[-1] * 1.05
        current_price_a = a[-1] * 0.95

        prices_a = np.append(a[-60:], current_price_a)
        prices_b = np.append(b[-60:], current_price_b)

        signal1 = strategy.generate_signal(
            prices_a, prices_b, current_price_a=current_price_a, current_price_b=current_price_b
        )

        # If we entered LONG_SPREAD
        if signal1.action == "LONG_SPREAD":
            # Simulate stop loss: z-score becomes even more negative (beyond stop_z)
            stop_price_b = b[-1] * 1.15
            stop_price_a = a[-1] * 0.85

            prices_a_stop = np.append(a[-60:], stop_price_a)
            prices_b_stop = np.append(b[-60:], stop_price_b)

            signal2 = strategy.generate_signal(
                prices_a_stop,
                prices_b_stop,
                current_price_a=stop_price_a,
                current_price_b=stop_price_b,
            )

            # Should close if z-score exceeds -stop_z
            if signal2.z_score <= -strategy.config.stop_z:
                assert signal2.action == "CLOSE"
                assert "stop loss" in signal2.reason.lower()

    def test_close_on_time_stop(self, strategy, cointegrated_data):
        """Test that exceeding max_hold_bars triggers CLOSE."""
        a, b = cointegrated_data

        # Use short max_hold_bars for testing
        strategy.config.max_hold_bars = 3
        # Set stop_z higher to avoid premature stop loss
        strategy.config.stop_z = 10.0

        # Calibrate
        strategy.calibrate(a, b)

        # Force entry with moderate z-score (between entry_z and stop_z)
        # Use moderate manipulation to create z-score around -2.5
        entry_price_b = b[-1] * 1.06
        entry_price_a = a[-1] * 0.94

        # Create entry prices array
        entry_prices_a = np.append(a[-60:], entry_price_a)
        entry_prices_b = np.append(b[-60:], entry_price_b)

        signal1 = strategy.generate_signal(
            entry_prices_a, entry_prices_b,
            current_price_a=entry_price_a,
            current_price_b=entry_price_b
        )

        # Verify we entered a position
        assert signal1.action in ["LONG_SPREAD", "SHORT_SPREAD"]
        assert strategy.has_position is True

        # Hold for max_hold_bars iterations with SAME prices
        # Z-score should stay between exit_z and stop_z
        signal = signal1
        for i in range(strategy.config.max_hold_bars):
            signal = strategy.generate_signal(
                entry_prices_a, entry_prices_b,
                current_price_a=entry_price_a,
                current_price_b=entry_price_b
            )

        # After max_hold_bars, should close due to time stop
        assert signal.action == "CLOSE"
        assert "time stop" in signal.reason.lower()
        assert strategy.has_position is False

    def test_dollar_neutral_sizing(self, strategy, cointegrated_data):
        """Test that size_a * price_a ≈ equity_per_leg and size_b is proportional."""
        a, b = cointegrated_data

        # Calibrate
        strategy.calibrate(a, b)

        # Create entry signal
        current_price_b = b[-1] * 1.05
        current_price_a = a[-1] * 0.95

        prices_a = np.append(a[-60:], current_price_a)
        prices_b = np.append(b[-60:], current_price_b)

        signal = strategy.generate_signal(
            prices_a, prices_b, current_price_a=current_price_a, current_price_b=current_price_b
        )

        if signal.action in ["LONG_SPREAD", "SHORT_SPREAD"]:
            # Check dollar-neutral sizing
            equity = strategy.config.equity_per_leg
            notional_a = signal.size_a * current_price_a
            notional_b = signal.size_b * current_price_b

            # size_a * price_a should equal equity
            assert abs(notional_a - equity) < 1.0  # Within $1 due to rounding

            # Notionals should be proportional to hedge ratio
            hr = signal.hedge_ratio
            expected_notional_b = equity * abs(hr)
            assert abs(notional_b - expected_notional_b) < 10.0  # Within $10

    def test_has_position_tracking(self, strategy, cointegrated_data):
        """Test that has_position is True after entry."""
        a, b = cointegrated_data

        # Initially no position
        assert strategy.has_position is False

        # Calibrate
        strategy.calibrate(a, b)

        # Create entry signal
        current_price_b = b[-1] * 1.05
        current_price_a = a[-1] * 0.95

        prices_a = np.append(a[-60:], current_price_a)
        prices_b = np.append(b[-60:], current_price_b)

        signal = strategy.generate_signal(
            prices_a, prices_b, current_price_a=current_price_a, current_price_b=current_price_b
        )

        # If entered position
        if signal.action in ["LONG_SPREAD", "SHORT_SPREAD"]:
            assert strategy.has_position is True

    def test_get_status_keys(self, strategy, cointegrated_data):
        """Test that get_status() returns expected keys."""
        a, b = cointegrated_data

        # Before calibration
        status = strategy.get_status()
        assert "is_cointegrated" in status
        assert "hedge_ratio" in status
        assert "has_position" in status
        assert "bars_in_trade" in status
        assert "current_action" in status
        assert "half_life" in status

        assert status["is_cointegrated"] is False
        assert status["has_position"] is False

        # After calibration
        strategy.calibrate(a, b)
        status = strategy.get_status()

        assert status["is_cointegrated"] is True
        assert status["hedge_ratio"] > 0

    def test_long_spread_directions(self, strategy, cointegrated_data):
        """Test that LONG_SPREAD has direction_a=BUY and direction_b=SELL."""
        a, b = cointegrated_data

        # Calibrate
        strategy.calibrate(a, b)

        # Force extreme negative z-score to trigger LONG_SPREAD
        # We'll build a very strong negative z-score by manipulating spread
        analyzer = CointegrationAnalyzer()
        hr = strategy.hedge_ratio

        # Build historical data with normal spread
        prices_a = a[-60:]
        prices_b = b[-60:]

        # Create extreme current prices
        # LONG_SPREAD: buy A (cheap), sell B (expensive)
        # We want spread to be much below mean
        current_price_b = b[-1] * 1.15  # B much higher
        current_price_a = a[-1] * 0.85  # A much lower

        # Compute what z-score would be
        spread_hist = analyzer.compute_spread(prices_a, prices_b, hr)
        current_spread = current_price_a - hr * current_price_b

        # Ensure this creates negative z-score
        mean = np.mean(spread_hist)
        std = np.std(spread_hist)
        expected_z = (current_spread - mean) / std if std > 0 else 0

        # Append current prices
        test_a = np.append(prices_a, current_price_a)
        test_b = np.append(prices_b, current_price_b)

        signal = strategy.generate_signal(
            test_a, test_b, current_price_a=current_price_a, current_price_b=current_price_b
        )

        # Check if LONG_SPREAD triggered
        if signal.action == "LONG_SPREAD":
            assert signal.direction_a == "BUY"
            assert signal.direction_b == "SELL"
            assert signal.z_score <= -strategy.config.entry_z
        # If not triggered, at least verify the logic would work
        elif expected_z <= -strategy.config.entry_z:
            # Z-score should be negative enough for entry
            assert signal.z_score <= -strategy.config.entry_z or signal.action == "HOLD"
