"""
Tests for candlestick pattern detection.

Tests for TechnicalIndicators.add_candlestick_patterns() method.
"""

import polars as pl
import pytest

from src.features.technical import TechnicalIndicators


@pytest.mark.unit
@pytest.mark.features
class TestCandlestickPatterns:
    """Test candlestick pattern detection."""

    def test_hammer_detected(self):
        """Test hammer pattern detection."""
        # Hammer: body < 30% of range, lower wick > 2x body, upper wick < body
        # open=100, high=100.2, low=95, close=100.5
        # body = |100.5 - 100| = 0.5
        # range = 100.2 - 95 = 5.2
        # body_pct = 0.5 / 5.2 = 0.096 < 0.3 ✓
        # lower_wick = min(100, 100.5) - 95 = 5.0
        # upper_wick = 100.2 - max(100, 100.5) = 100.2 - 100.5 = -0.3 (should be 0)
        # Wait, max(100, 100.5) = 100.5, so upper_wick = 100.2 - 100.5 = -0.3
        # That's wrong. Let me recalculate.

        # Actually for a hammer, close should be near high
        # open=100, high=100.4, low=95, close=100.3
        # body = |100.3 - 100| = 0.3
        # range = 100.4 - 95 = 5.4
        # body_pct = 0.3 / 5.4 = 0.056 < 0.3 ✓
        # lower_wick = min(100, 100.3) - 95 = 100 - 95 = 5.0
        # upper_wick = 100.4 - max(100, 100.3) = 100.4 - 100.3 = 0.1
        # Conditions: lower_wick(5.0) > body(0.3) * 2 = 0.6 ✓
        #             upper_wick(0.1) < body(0.3) ✓
        df = pl.DataFrame({
            "open": [100.0],
            "high": [100.4],
            "low": [95.0],
            "close": [100.3],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert "candle_hammer" in result.columns
        assert result["candle_hammer"][0] == 1

    def test_inv_hammer_detected(self):
        """Test inverted hammer pattern detection."""
        # Inverted hammer: body < 30% of range, upper wick > 2x body, lower wick < body
        # open=100.0, high=105.0, low=99.9, close=100.3
        # body = |100.3 - 100.0| = 0.3
        # range = 105.0 - 99.9 = 5.1
        # body_pct = 0.3 / 5.1 = 0.059 < 0.3 ✓
        # upper_wick = 105.0 - max(100.0, 100.3) = 105.0 - 100.3 = 4.7
        # lower_wick = min(100.0, 100.3) - 99.9 = 100.0 - 99.9 = 0.1
        # Conditions: upper_wick(4.7) > body(0.3) * 2 = 0.6 ✓
        #             lower_wick(0.1) < body(0.3) ✓
        df = pl.DataFrame({
            "open": [100.0],
            "high": [105.0],
            "low": [99.9],
            "close": [100.3],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert "candle_inv_hammer" in result.columns
        assert result["candle_inv_hammer"][0] == 1

    def test_engulf_bull_detected(self):
        """Test bullish engulfing pattern detection."""
        # Bullish engulfing: current bullish body engulfs previous bearish body
        # Bar 0 (previous): open=102, close=100 (bearish)
        # Bar 1 (current): open=99.5, close=102.5 (bullish, engulfs previous)
        # Conditions:
        #   - current close(102.5) > current open(99.5) ✓ (bullish)
        #   - prev close(100) < prev open(102) ✓ (bearish)
        #   - current open(99.5) <= prev close(100) ✓
        #   - current close(102.5) >= prev open(102) ✓
        df = pl.DataFrame({
            "open": [102.0, 99.5],
            "high": [103.0, 103.0],
            "low": [99.0, 99.0],
            "close": [100.0, 102.5],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert "candle_engulf_bull" in result.columns
        assert result["candle_engulf_bull"][0] == 0  # First bar can't engulf
        assert result["candle_engulf_bull"][1] == 1  # Second bar engulfs

    def test_engulf_bear_detected(self):
        """Test bearish engulfing pattern detection."""
        # Bearish engulfing: current bearish body engulfs previous bullish body
        # Bar 0 (previous): open=100, close=102 (bullish)
        # Bar 1 (current): open=102.5, close=99.5 (bearish, engulfs previous)
        # Conditions:
        #   - current close(99.5) < current open(102.5) ✓ (bearish)
        #   - prev close(102) > prev open(100) ✓ (bullish)
        #   - current open(102.5) >= prev close(102) ✓
        #   - current close(99.5) <= prev open(100) ✓
        df = pl.DataFrame({
            "open": [100.0, 102.5],
            "high": [103.0, 103.0],
            "low": [99.0, 99.0],
            "close": [102.0, 99.5],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert "candle_engulf_bear" in result.columns
        assert result["candle_engulf_bear"][0] == 0  # First bar can't engulf
        assert result["candle_engulf_bear"][1] == 1  # Second bar engulfs

    def test_doji_detected(self):
        """Test doji pattern detection."""
        # Doji: body < 10% of range
        # open=100.0, high=102.0, low=98.0, close=100.1
        # body = |100.1 - 100.0| = 0.1
        # range = 102.0 - 98.0 = 4.0
        # body_pct = 0.1 / 4.0 = 0.025 < 0.1 ✓
        df = pl.DataFrame({
            "open": [100.0],
            "high": [102.0],
            "low": [98.0],
            "close": [100.1],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert "candle_doji" in result.columns
        assert result["candle_doji"][0] == 1

    def test_morning_star_detected(self):
        """Test morning star pattern detection."""
        # Morning star: bearish + small body + bullish (3-bar pattern)
        # Bar 0: open=105, close=100 (bearish)
        # Bar 1: open=99.5, close=99.7 (small body)
        # Bar 2: open=99.8, close=103 (bullish, closes above midpoint of bar 0)
        # Midpoint of bar 0 = (105 + 100) / 2 = 102.5
        # Bar 2 close (103) > 102.5 ✓
        # Bar 1 body_pct = |99.7 - 99.5| / (100 - 99) = 0.2 / 1.0 = 0.2 < 0.3 ✓
        df = pl.DataFrame({
            "open": [105.0, 99.5, 99.8],
            "high": [105.5, 100.0, 103.5],
            "low": [99.0, 99.0, 99.0],
            "close": [100.0, 99.7, 103.0],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert "candle_morning_star" in result.columns
        assert result["candle_morning_star"][0] == 0  # First bar
        assert result["candle_morning_star"][1] == 0  # Second bar
        assert result["candle_morning_star"][2] == 1  # Third bar completes pattern

    def test_evening_star_detected(self):
        """Test evening star pattern detection."""
        # Evening star: bullish + small body + bearish (3-bar pattern)
        # Bar 0: open=100, close=105 (bullish)
        # Bar 1: open=105.3, close=105.5 (small body)
        # Bar 2: open=105.2, close=101.5 (bearish, closes below midpoint of bar 0)
        # Midpoint of bar 0 = (100 + 105) / 2 = 102.5
        # Bar 2 close (101.5) < 102.5 ✓
        # Bar 1 body_pct = |105.5 - 105.3| / (106 - 105) = 0.2 / 1.0 = 0.2 < 0.3 ✓
        df = pl.DataFrame({
            "open": [100.0, 105.3, 105.2],
            "high": [105.5, 106.0, 106.0],
            "low": [99.5, 105.0, 101.0],
            "close": [105.0, 105.5, 101.5],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert "candle_evening_star" in result.columns
        assert result["candle_evening_star"][0] == 0  # First bar
        assert result["candle_evening_star"][1] == 0  # Second bar
        assert result["candle_evening_star"][2] == 1  # Third bar completes pattern

    def test_pin_bar_detected(self):
        """Test pin bar pattern detection."""
        # Pin bar: max wick > 3x body, body > 0
        # open=100.0, high=100.5, low=95.0, close=100.4
        # body = |100.4 - 100.0| = 0.4
        # upper_wick = 100.5 - max(100.0, 100.4) = 100.5 - 100.4 = 0.1
        # lower_wick = min(100.0, 100.4) - 95.0 = 100.0 - 95.0 = 5.0
        # max_wick = max(0.1, 5.0) = 5.0
        # Conditions: max_wick(5.0) > body(0.4) * 3 = 1.2 ✓
        #             body(0.4) > 0 ✓
        df = pl.DataFrame({
            "open": [100.0],
            "high": [100.5],
            "low": [95.0],
            "close": [100.4],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert "candle_pin_bar" in result.columns
        assert result["candle_pin_bar"][0] == 1

    def test_no_pattern_normal_bars(self):
        """Test that normal bars don't trigger any pattern."""
        # Normal bar with balanced proportions
        # open=100, high=101, low=99, close=100.5
        # body = 0.5, range = 2.0, body_pct = 0.25
        # This shouldn't match hammer, inv_hammer, doji, or pin_bar
        df = pl.DataFrame({
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        pattern_cols = [
            "candle_hammer",
            "candle_inv_hammer",
            "candle_doji",
            "candle_pin_bar",
        ]
        for col in pattern_cols:
            assert result[col][0] == 0, f"{col} should not be triggered"

    def test_all_columns_present(self):
        """Test that all 8 pattern columns are added."""
        df = pl.DataFrame({
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.5],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        expected_columns = [
            "candle_hammer",
            "candle_inv_hammer",
            "candle_engulf_bull",
            "candle_engulf_bear",
            "candle_doji",
            "candle_morning_star",
            "candle_evening_star",
            "candle_pin_bar",
        ]

        for col in expected_columns:
            assert col in result.columns, f"Missing column: {col}"

    def test_patterns_are_binary(self):
        """Test that all pattern values are 0 or 1."""
        df = pl.DataFrame({
            "open": [100.0, 102.0, 99.5],
            "high": [105.0, 103.0, 103.0],
            "low": [95.0, 99.0, 99.0],
            "close": [100.3, 100.0, 102.5],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        pattern_cols = [
            "candle_hammer",
            "candle_inv_hammer",
            "candle_engulf_bull",
            "candle_engulf_bear",
            "candle_doji",
            "candle_morning_star",
            "candle_evening_star",
            "candle_pin_bar",
        ]

        for col in pattern_cols:
            values = result[col].unique().sort()
            assert all(v in [0, 1] for v in values), f"{col} has non-binary values: {values}"

    def test_multiple_patterns_can_overlap(self):
        """Test that a bar can match multiple patterns simultaneously."""
        # Design a bar that is both a hammer and a pin_bar
        # Hammer: body < 30% range, lower_wick > 2x body, upper_wick < body
        # Pin bar: max_wick > 3x body, body > 0
        # open=100.0, high=100.3, low=95.0, close=100.2
        # body = |100.2 - 100.0| = 0.2
        # range = 100.3 - 95.0 = 5.3
        # body_pct = 0.2 / 5.3 = 0.038 < 0.3 ✓
        # lower_wick = min(100.0, 100.2) - 95.0 = 100.0 - 95.0 = 5.0
        # upper_wick = 100.3 - max(100.0, 100.2) = 100.3 - 100.2 = 0.1
        # Hammer: lower_wick(5.0) > body(0.2) * 2 = 0.4 ✓
        #         upper_wick(0.1) < body(0.2) ✓
        # Pin bar: max_wick(5.0) > body(0.2) * 3 = 0.6 ✓
        df = pl.DataFrame({
            "open": [100.0],
            "high": [100.3],
            "low": [95.0],
            "close": [100.2],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert result["candle_hammer"][0] == 1, "Should be detected as hammer"
        assert result["candle_pin_bar"][0] == 1, "Should be detected as pin bar"

    def test_hammer_not_detected_wrong_proportions(self):
        """Test that hammer is not detected when proportions don't match."""
        # Body too large relative to range
        # open=100.0, high=101.5, low=99.0, close=101.0
        # body = 1.0, range = 2.5, body_pct = 0.4 > 0.3 ✗
        df = pl.DataFrame({
            "open": [100.0],
            "high": [101.5],
            "low": [99.0],
            "close": [101.0],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert result["candle_hammer"][0] == 0

    def test_engulfing_requires_opposite_colors(self):
        """Test that engulfing patterns require opposite candle colors."""
        # Two consecutive bullish bars - no engulfing
        # Bar 0: open=100, close=102 (bullish)
        # Bar 1: open=99, close=103 (bullish, but doesn't engulf because previous wasn't bearish)
        df = pl.DataFrame({
            "open": [100.0, 99.0],
            "high": [103.0, 103.5],
            "low": [99.0, 98.0],
            "close": [102.0, 103.0],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert result["candle_engulf_bull"][1] == 0, "Should not detect bullish engulfing"

    def test_morning_star_requires_bearish_first_bar(self):
        """Test that morning star requires first bar to be bearish."""
        # Bar 0: open=100, close=105 (bullish - should fail)
        # Bar 1: open=99.5, close=99.7 (small body)
        # Bar 2: open=99.8, close=103 (bullish)
        df = pl.DataFrame({
            "open": [100.0, 99.5, 99.8],
            "high": [105.5, 100.0, 103.5],
            "low": [99.0, 99.0, 99.0],
            "close": [105.0, 99.7, 103.0],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert result["candle_morning_star"][2] == 0, "Should not detect morning star"

    def test_zero_range_candle(self):
        """Test handling of zero-range candles (all OHLC equal)."""
        # Zero range candle should not crash and should use safe_range=1.0
        df = pl.DataFrame({
            "open": [100.0],
            "high": [100.0],
            "low": [100.0],
            "close": [100.0],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        # Should complete without error
        assert "candle_hammer" in result.columns
        # Zero body / 1.0 safe_range = 0.0 < 0.1, so doji should be detected
        assert result["candle_doji"][0] == 1

    def test_doji_at_boundary(self):
        """Test doji detection at exactly 10% body ratio."""
        # Exactly at boundary: body_pct = 0.1
        # open=100.0, high=101.0, low=99.0, close=100.2
        # body = 0.2, range = 2.0, body_pct = 0.1
        # Condition: body_pct < 0.1, so 0.1 should NOT trigger (not strictly less than)
        df = pl.DataFrame({
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.2],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert result["candle_doji"][0] == 0, "Doji should not trigger at exactly 0.1"

    def test_doji_just_below_boundary(self):
        """Test doji detection just below 10% body ratio."""
        # Just below boundary: body_pct < 0.1
        # open=100.0, high=101.0, low=99.0, close=100.19
        # body = 0.19, range = 2.0, body_pct = 0.095 < 0.1 ✓
        df = pl.DataFrame({
            "open": [100.0],
            "high": [101.0],
            "low": [99.0],
            "close": [100.19],
        })

        result = TechnicalIndicators.add_candlestick_patterns(df)

        assert result["candle_doji"][0] == 1, "Doji should trigger just below 0.1"
