"""Tests for ORB+FVG strategy core logic and live integration."""

from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import polars as pl
import pytest

from src.strategy.orb_fvg_strategy import (
    FVGSignal,
    OrbFvgStrategy,
    RR_RATIO,
    _minutes_utc,
    _SessionState,
    detect_fvg,
    process_session,
)
from src.strategy.schemas import SignalDirection, StrategyConfig


# ---------------------------------------------------------------------------
# Helper: build a bar dict
# ---------------------------------------------------------------------------
def _bar(
    hour: int,
    minute: int,
    o: float,
    h: float,
    l: float,
    c: float,
    vol: int = 1000,
) -> dict:
    return {
        "timestamp": datetime(2026, 1, 15, hour, minute, tzinfo=timezone.utc),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
    }


# ===================================================================
# TestMinutesUtc
# ===================================================================
class TestMinutesUtc:
    def test_midnight(self):
        ts = datetime(2026, 1, 15, 0, 0, tzinfo=timezone.utc)
        assert _minutes_utc(ts) == 0

    def test_orb_start(self):
        ts = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
        assert _minutes_utc(ts) == 14 * 60 + 30

    def test_arbitrary(self):
        ts = datetime(2026, 1, 15, 9, 45, tzinfo=timezone.utc)
        assert _minutes_utc(ts) == 9 * 60 + 45


# ===================================================================
# TestDetectFvg
# ===================================================================
class TestDetectFvg:
    def test_bullish_fvg_with_orb_breakout(self):
        """C3.low > C1.high AND C2.close > orb_high -> BUY."""
        c1 = _bar(14, 36, 100, 101, 99, 100.5)
        c2 = _bar(14, 37, 100.5, 103, 100, 102.5)  # close > orb_high (101)
        c3 = _bar(14, 38, 102, 104, 101.5, 103)     # low 101.5 > c1.high 101

        result = detect_fvg(c1, c2, c3, orb_high=101.0, orb_low=99.0)

        assert result is not None
        assert result.direction == SignalDirection.BUY
        assert result.fvg_type == "bullish"
        assert result.stop_loss == c2["low"]  # 100
        assert result.take_profit > result.entry_price

    def test_bearish_fvg_with_orb_breakout(self):
        """C3.high < C1.low AND C2.close < orb_low -> SELL."""
        c1 = _bar(14, 36, 100, 101, 99, 100)
        c2 = _bar(14, 37, 99, 99.5, 96, 98)    # close 98 < orb_low 99
        c3 = _bar(14, 38, 97, 98.5, 96.5, 97)  # high 98.5 < c1.low 99

        result = detect_fvg(c1, c2, c3, orb_high=101.0, orb_low=99.0)

        assert result is not None
        assert result.direction == SignalDirection.SELL
        assert result.fvg_type == "bearish"
        assert result.stop_loss == c2["high"]  # 99.5
        assert result.take_profit < result.entry_price

    def test_no_fvg_without_gap(self):
        """C3.low < C1.high -> no gap -> None."""
        c1 = _bar(14, 36, 100, 102, 99, 101)
        c2 = _bar(14, 37, 101, 103, 100, 102.5)
        c3 = _bar(14, 38, 102, 103, 101, 102.5)  # low 101 < c1.high 102

        result = detect_fvg(c1, c2, c3, orb_high=101.0, orb_low=99.0)
        assert result is None

    def test_fvg_without_orb_breakout_rejected(self):
        """Gap exists but C2.close does not break ORB -> None."""
        c1 = _bar(14, 36, 100, 100.5, 99.5, 100.2)
        c2 = _bar(14, 37, 100.2, 101, 99.8, 100.8)  # close 100.8 < orb_high 101
        c3 = _bar(14, 38, 101, 102, 100.6, 101.5)    # low 100.6 > c1.high 100.5

        result = detect_fvg(c1, c2, c3, orb_high=101.0, orb_low=99.0)
        assert result is None

    def test_zero_risk_rejected(self):
        """Entry == SL (zero risk) -> None."""
        # Construct so that c3.close == c2.low (entry == SL for bullish)
        c1 = _bar(14, 36, 100, 100.5, 99, 100.2)
        c2 = _bar(14, 37, 100.2, 102, 101, 101.5)  # close > orb_high, low=101
        c3 = _bar(14, 38, 101.5, 102, 100.6, 101)   # low 100.6 > c1.high 100.5
        # c3.close = 101 == c2.low = 101 -> risk = 0

        result = detect_fvg(c1, c2, c3, orb_high=100.5, orb_low=99.0)
        assert result is None


# ===================================================================
# TestProcessSession
# ===================================================================
class TestProcessSession:
    @staticmethod
    def _make_orb_bars(base: float = 100.0) -> list[dict]:
        """Create 5 ORB candles (14:30-14:34 UTC) with a decent range."""
        bars = []
        for i in range(5):
            bars.append(
                _bar(14, 30 + i, base, base + 1.0, base - 1.0, base + 0.5)
            )
        return bars

    def test_valid_session_returns_signal(self):
        """5 ORB bars + bullish FVG after ORB -> signal returned."""
        bars = self._make_orb_bars(100.0)
        # orb_high = 101, orb_low = 99

        # Add scan bars that form a bullish FVG
        bars.append(_bar(14, 35, 100, 100.5, 99.5, 100.2))  # scan C1
        bars.append(_bar(14, 36, 100.5, 103, 100, 102))      # scan C2: close > 101
        bars.append(_bar(14, 37, 102, 104, 101, 103))         # scan C3: low 101 > C1.high 100.5
        bars.append(_bar(14, 38, 103, 104, 102, 103.5))       # C4: entry = open 103

        result = process_session(bars)
        assert result is not None
        assert result.direction == SignalDirection.BUY
        assert result.entry_price == 103.0  # C4.open
        assert result.stop_loss == 100.0    # C2.low

    def test_tight_range_skips_session(self):
        """ORB range < 0.1% of mid-price -> None."""
        # Price ~100, range 0.05 -> 0.05% < 0.1%
        bars = []
        for i in range(5):
            bars.append(
                _bar(14, 30 + i, 100.0, 100.025, 99.975, 100.0)
            )
        # Even with a perfect FVG after, session should be skipped
        bars.append(_bar(14, 35, 100, 100.5, 99.5, 100.2))
        bars.append(_bar(14, 36, 100.5, 103, 100, 102))
        bars.append(_bar(14, 37, 102, 104, 101, 103))

        result = process_session(bars)
        assert result is None

    def test_no_fvg_returns_none(self):
        """Flat bars with no gap -> None."""
        bars = self._make_orb_bars(100.0)
        # Add flat scan bars (no gaps)
        for i in range(10):
            bars.append(_bar(14, 35 + i, 100, 100.5, 99.5, 100.2))

        result = process_session(bars)
        assert result is None

    def test_cutoff_time_stops_scanning(self):
        """FVG occurring after 20:30 UTC (15:30 EST on Jan 15) -> ignored."""
        bars = self._make_orb_bars(100.0)

        # Add scan bars before cutoff that are flat (no FVG)
        for i in range(10):
            bars.append(_bar(14, 35 + i, 100, 100.5, 99.5, 100.2))

        # Add FVG bars right at / after 20:30 UTC cutoff (15:30 EST in winter)
        bars.append(_bar(20, 29, 100, 100.5, 99.5, 100.2))   # C1 at 20:29
        bars.append(_bar(20, 30, 100.5, 103, 100, 102))       # C2 at 20:30
        bars.append(_bar(20, 31, 102, 104, 101, 103))         # C3 at 20:31 > cutoff

        result = process_session(bars)
        assert result is None


# ===================================================================
# TestOrbFvgStrategy
# ===================================================================
class TestOrbFvgStrategy:
    def test_name(self):
        strategy = OrbFvgStrategy()
        assert strategy.name == "orb_fvg"

    def test_applicable_regimes(self):
        strategy = OrbFvgStrategy()
        assert "trending_up" in strategy.applicable_regimes
        assert "trending_down" in strategy.applicable_regimes

    def test_rr_ratio_is_2(self):
        """TP = entry + 2 * risk for a long signal."""
        c1 = _bar(14, 36, 100, 100.5, 99, 100.2)
        c2 = _bar(14, 37, 100.5, 103, 100, 102)    # close > orb_high, low=100
        c3 = _bar(14, 38, 102, 104, 101, 103)       # low 101 > c1.high 100.5

        result = detect_fvg(c1, c2, c3, orb_high=101.0, orb_low=99.0)
        assert result is not None

        entry = result.entry_price
        sl = result.stop_loss
        tp = result.take_profit
        risk = entry - sl
        reward = tp - entry

        assert risk > 0
        assert abs(reward / risk - RR_RATIO) < 1e-9


# ===================================================================
# TestOrbFvgStrategyLive — generate_signal with M1 DataFrame
# ===================================================================
class TestOrbFvgStrategyLive:
    """Tests for the live generate_signal() with session state machine."""

    @staticmethod
    def _make_m1_df(bars: list[dict]) -> pl.DataFrame:
        """Convert bar dicts to a Polars DataFrame matching M1 schema."""
        return pl.DataFrame(bars)

    @staticmethod
    def _make_session_bars(base: float = 5000.0) -> list[dict]:
        """Build a full ORB + bullish FVG session for US500-like prices."""
        bars = []
        # ORB bars (14:30-14:34 UTC) — Jan 15, 2026 (winter, EST = UTC-5)
        for i in range(5):
            bars.append(_bar(14, 30 + i, base, base + 10, base - 10, base + 5))
        # orb_high = base+10, orb_low = base-10

        # Scan bars forming bullish FVG
        bars.append(_bar(14, 35, base, base + 5, base - 5, base + 2))    # C1
        bars.append(_bar(14, 36, base + 5, base + 30, base, base + 25))  # C2: close > orb_high
        bars.append(_bar(14, 37, base + 25, base + 35, base + 11, base + 30))  # C3: low > C1.high
        bars.append(_bar(14, 38, base + 30, base + 35, base + 28, base + 32))  # C4: entry
        return bars

    def test_generate_signal_with_valid_fvg(self):
        """Strategy returns BUY when M1 bars contain a valid ORB+FVG."""
        strategy = OrbFvgStrategy(ml_threshold=0.50)
        bars = self._make_session_bars(5000.0)
        df = self._make_m1_df(bars)
        config = StrategyConfig(epic="US500")

        signal = strategy.generate_signal(
            "US500", {"close": 5030.0}, df, config
        )

        assert signal.direction == SignalDirection.BUY
        assert signal.strategy_name == "orb_fvg"
        assert signal.confidence > 0
        assert signal.suggested_stop is not None
        assert signal.suggested_tp is not None

    def test_generate_signal_hold_when_no_fvg(self):
        """Strategy returns HOLD when M1 bars have no FVG."""
        strategy = OrbFvgStrategy()
        # Only flat ORB bars, no FVG pattern
        bars = []
        for i in range(10):
            bars.append(_bar(14, 30 + i, 5000, 5001, 4999, 5000))
        df = self._make_m1_df(bars)
        config = StrategyConfig(epic="US500")

        signal = strategy.generate_signal("US500", {"close": 5000.0}, df, config)
        assert signal.direction == SignalDirection.HOLD

    def test_generate_signal_hold_when_empty_df(self):
        """Strategy returns HOLD when recent_bars is empty."""
        strategy = OrbFvgStrategy()
        df = pl.DataFrame({"timestamp": [], "open": [], "high": [], "low": [], "close": []})
        config = StrategyConfig(epic="US500")

        signal = strategy.generate_signal("US500", {"close": 5000.0}, df, config)
        assert signal.direction == SignalDirection.HOLD

    def test_one_trade_per_session(self):
        """Strategy returns HOLD on second call for same session day."""
        strategy = OrbFvgStrategy(ml_threshold=0.50)
        bars = self._make_session_bars(5000.0)
        df = self._make_m1_df(bars)
        config = StrategyConfig(epic="US500")

        # First call: should signal
        signal1 = strategy.generate_signal("US500", {"close": 5030.0}, df, config)
        assert signal1.direction == SignalDirection.BUY

        # Second call same day: should HOLD (already traded)
        signal2 = strategy.generate_signal("US500", {"close": 5030.0}, df, config)
        assert signal2.direction == SignalDirection.HOLD

    def test_new_session_resets_state(self):
        """Strategy resets when bars are from a different date."""
        strategy = OrbFvgStrategy(ml_threshold=0.50)

        # Day 1 — trades
        bars1 = self._make_session_bars(5000.0)
        df1 = self._make_m1_df(bars1)
        config = StrategyConfig(epic="US500")
        signal1 = strategy.generate_signal("US500", {"close": 5030.0}, df1, config)
        assert signal1.direction == SignalDirection.BUY

        # Day 2 — different date, should be able to trade again
        bars2 = []
        for i in range(5):
            bars2.append({
                "timestamp": datetime(2026, 1, 16, 14, 30 + i, tzinfo=timezone.utc),
                "open": 5100.0, "high": 5110.0, "low": 5090.0, "close": 5105.0, "volume": 1000,
            })
        bars2.append({
            "timestamp": datetime(2026, 1, 16, 14, 35, tzinfo=timezone.utc),
            "open": 5100, "high": 5105, "low": 5095, "close": 5102, "volume": 1000,
        })
        bars2.append({
            "timestamp": datetime(2026, 1, 16, 14, 36, tzinfo=timezone.utc),
            "open": 5105, "high": 5130, "low": 5100, "close": 5125, "volume": 1000,
        })
        bars2.append({
            "timestamp": datetime(2026, 1, 16, 14, 37, tzinfo=timezone.utc),
            "open": 5125, "high": 5135, "low": 5111, "close": 5130, "volume": 1000,
        })
        bars2.append({
            "timestamp": datetime(2026, 1, 16, 14, 38, tzinfo=timezone.utc),
            "open": 5130, "high": 5135, "low": 5128, "close": 5132, "volume": 1000,
        })
        df2 = self._make_m1_df(bars2)
        signal2 = strategy.generate_signal("US500", {"close": 5130.0}, df2, config)

        # Session state should have been reset (different day)
        sess = strategy._get_session("US500")
        assert sess.session_date == datetime(2026, 1, 16).date()

    def test_ml_filter_rejects_low_probability(self):
        """Strategy returns HOLD when ML filter probability is below threshold."""
        strategy = OrbFvgStrategy(ml_threshold=0.80)
        bars = self._make_session_bars(5000.0)
        df = self._make_m1_df(bars)
        config = StrategyConfig(epic="US500")

        # Mock ML model to return low probability
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = [[0.60, 0.40]]  # prob=0.40 < 0.80
        strategy._ml_model = mock_model
        strategy._ml_load_attempted = True

        signal = strategy.generate_signal("US500", {"close": 5030.0}, df, config)
        assert signal.direction == SignalDirection.HOLD

    def test_ml_filter_approves_high_probability(self):
        """Strategy returns signal when ML filter probability is above threshold."""
        strategy = OrbFvgStrategy(ml_threshold=0.50)
        bars = self._make_session_bars(5000.0)
        df = self._make_m1_df(bars)
        config = StrategyConfig(epic="US500")

        # Mock ML model to return high probability
        mock_model = MagicMock()
        mock_model.predict_proba.return_value = [[0.30, 0.70]]  # prob=0.70 > 0.50
        strategy._ml_model = mock_model
        strategy._ml_load_attempted = True

        signal = strategy.generate_signal("US500", {"close": 5030.0}, df, config)
        assert signal.direction == SignalDirection.BUY
        # Confidence should be boosted by ML probability
        assert signal.confidence > 0.60

    def test_no_ml_model_still_signals(self):
        """Strategy works without ML model (no filter applied)."""
        strategy = OrbFvgStrategy()
        strategy._ml_load_attempted = True  # Skip model loading
        strategy._ml_model = None

        bars = self._make_session_bars(5000.0)
        df = self._make_m1_df(bars)
        config = StrategyConfig(epic="US500")

        signal = strategy.generate_signal("US500", {"close": 5030.0}, df, config)
        assert signal.direction == SignalDirection.BUY
        assert signal.confidence == 0.60  # Base confidence without ML


# ===================================================================
# TestStrategyManagerOrbFvg — routing integration
# ===================================================================
class TestStrategyManagerOrbFvg:
    """Test that StrategyManager routes US500 to ORB+FVG."""

    def test_orb_fvg_epics_default(self):
        from src.strategy.strategy_manager import StrategyManager
        sm = StrategyManager(scalp_mode=True)
        assert "US500" in sm.orb_fvg_epics
        assert sm._orb_fvg_strategy is not None

    def test_orb_fvg_routes_with_m1_bars(self):
        """US500 with m1_bars in market_data routes to ORB+FVG."""
        from src.strategy.strategy_manager import StrategyManager
        from src.models.schemas import PredictionResult, SignalClass

        sm = StrategyManager(scalp_mode=True)
        # Bypass ML filter for test
        sm._orb_fvg_strategy._ml_load_attempted = True
        sm._orb_fvg_strategy._ml_model = None

        bars = TestOrbFvgStrategyLive._make_session_bars(5000.0)
        m1_df = pl.DataFrame(bars)

        prediction = PredictionResult(
            signal_class=SignalClass.BUY,
            signal_name="BUY",
            confidence=0.60,
            probabilities={"BUY": 0.60, "HOLD": 0.30, "SELL": 0.10},
        )
        market_data = {
            "current_price": 5030.0,
            "atr": 15.0,
            "m1_bars": m1_df,
        }

        signal = sm.process_prediction(prediction, "US500", market_data)
        assert signal.strategy_name == "orb_fvg"

    def test_non_orb_epic_routes_to_scalp(self):
        """XAUUSD (not in orb_fvg_epics) routes to ScalpScore."""
        from src.strategy.strategy_manager import StrategyManager
        from src.models.schemas import PredictionResult, SignalClass

        sm = StrategyManager(scalp_mode=True)

        prediction = PredictionResult(
            signal_class=SignalClass.BUY,
            signal_name="BUY",
            confidence=0.60,
            probabilities={"BUY": 0.60, "HOLD": 0.30, "SELL": 0.10},
        )
        market_data = {
            "current_price": 2050.0,
            "atr": 5.0,
            "rsi": 50,
            "adx": 25,
            "ema_9": 2048, "ema_21": 2045,
            "macd": 1.0, "macd_signal": 0.5, "macd_histogram": 0.5,
            "volume": 1000, "volume_sma_20": 800,
            "bb_upper": 2060, "bb_lower": 2040, "bb_middle": 2050,
            "keltner_upper": 2058, "keltner_lower": 2042,
            "vwap": 2048,
            "htf_bias": None,
        }

        signal = sm.process_prediction(prediction, "XAUUSD", market_data)
        # Should use scalp_score, not orb_fvg
        assert signal.strategy_name != "orb_fvg"
