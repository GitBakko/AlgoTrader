"""Tests for ORB+FVG strategy core logic."""

from datetime import datetime, timezone

import pytest

from src.strategy.orb_fvg_strategy import (
    FVGSignal,
    OrbFvgStrategy,
    RR_RATIO,
    _minutes_utc,
    detect_fvg,
    process_session,
)
from src.strategy.schemas import SignalDirection


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
