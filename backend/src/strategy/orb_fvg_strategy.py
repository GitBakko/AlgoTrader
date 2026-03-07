"""
ORB+FVG Strategy — Opening Range Breakout with Fair Value Gap confirmation.

Session state machine with 3 phases per trading day (all times EST / UTC):
  1. WAIT_FOR_ORB  (09:30-09:35 EST = 14:30-14:35 UTC): collect first 5 M1 candles
  2. SCAN_FOR_FVG  (09:35-15:30 EST = 14:35-19:30 UTC): scan for FVG on every new M1 bar
  3. IN_POSITION / END_OF_DAY

FVG Detection (3 consecutive M1 bars C1, C2, C3):
  - Bullish: C3.low > C1.high  AND  C2.close > orb_high  ->  BUY
  - Bearish: C3.high < C1.low  AND  C2.close < orb_low   ->  SELL

Entry at C4.open (bar after C3).
Stop-loss: Long = C2.low, Short = C2.high.
Take-profit: R:R = 2:1.

Constraints:
  - Max 1 trade per session per asset
  - No entries after 15:30 EST (19:30 UTC)
  - Skip session if orb_range < 0.1% of price
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

import polars as pl
from loguru import logger

from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal

# ---------------------------------------------------------------------------
# NYSE session times in US/Eastern (handles EST/EDT automatically)
# ---------------------------------------------------------------------------
_ET = ZoneInfo("America/New_York")

# NYSE local times
_NYSE_ORB_START = time(9, 30)
_NYSE_ORB_END = time(9, 35)
_NYSE_ENTRY_CUTOFF = time(15, 30)
_NYSE_SESSION_END = time(16, 0)


def _nyse_utc_minutes(date: datetime, local_time: time) -> int:
    """Convert a NYSE local time to UTC minutes-from-midnight for a given date."""
    et_dt = datetime.combine(date.date(), local_time, tzinfo=_ET)
    utc_dt = et_dt.astimezone(timezone.utc)
    return utc_dt.hour * 60 + utc_dt.minute

# Minimum ORB range as fraction of mid-price
MIN_ORB_RANGE_PCT = 0.001  # 0.1%

# Risk-reward ratio
RR_RATIO = 2.0


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class FVGSignal:
    """Result of FVG detection + ORB breakout confirmation."""

    direction: SignalDirection
    fvg_type: str           # "bullish" or "bearish"
    entry_price: float      # C4.open (filled by process_session)
    stop_loss: float
    take_profit: float
    c2_bar: dict            # the breakout candle


# ---------------------------------------------------------------------------
# Helper: extract minute-of-day from UTC timestamp
# ---------------------------------------------------------------------------
def _minutes_utc(ts: datetime) -> int:
    """Return minutes from midnight UTC for *ts*."""
    return ts.hour * 60 + ts.minute


# ---------------------------------------------------------------------------
# FVG detection on three consecutive bars
# ---------------------------------------------------------------------------
def detect_fvg(
    c1: dict,
    c2: dict,
    c3: dict,
    orb_high: float,
    orb_low: float,
) -> FVGSignal | None:
    """
    Check three consecutive M1 bars for a Fair Value Gap aligned with an
    ORB breakout.

    Returns an FVGSignal if found, else None.
    Entry price is set to c3["close"] as a placeholder; the caller should
    overwrite it with C4.open when available.
    """
    # --- Bullish FVG: gap up ---
    if c3["low"] > c1["high"] and c2["close"] > orb_high:
        entry = c3["close"]  # placeholder
        sl = c2["low"]
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + RR_RATIO * risk
        return FVGSignal(
            direction=SignalDirection.BUY,
            fvg_type="bullish",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            c2_bar=c2,
        )

    # --- Bearish FVG: gap down ---
    if c3["high"] < c1["low"] and c2["close"] < orb_low:
        entry = c3["close"]  # placeholder
        sl = c2["high"]
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - RR_RATIO * risk
        return FVGSignal(
            direction=SignalDirection.SELL,
            fvg_type="bearish",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            c2_bar=c2,
        )

    return None


# ---------------------------------------------------------------------------
# Process a full day of M1 bars
# ---------------------------------------------------------------------------
def process_session(bars: list[dict]) -> FVGSignal | None:
    """
    Walk through one day of M1 bars and return the first valid ORB+FVG signal.

    Each bar dict must have keys: timestamp (datetime), open, high, low, close.
    Bars must be sorted chronologically. Timestamps must be naive UTC.

    Returns None when no valid signal is found for this session.
    """
    if not bars:
        return None

    # Compute UTC session boundaries for this specific date (handles DST)
    session_date = bars[0]["timestamp"]
    orb_start = _nyse_utc_minutes(session_date, _NYSE_ORB_START)
    orb_end = _nyse_utc_minutes(session_date, _NYSE_ORB_END)
    entry_cutoff = _nyse_utc_minutes(session_date, _NYSE_ENTRY_CUTOFF)

    # --- Phase 1: collect ORB candles ---
    orb_bars: list[dict] = []
    scan_bars: list[dict] = []

    for bar in bars:
        m = _minutes_utc(bar["timestamp"])
        if orb_start <= m < orb_end:
            orb_bars.append(bar)
        elif orb_end <= m <= entry_cutoff:
            scan_bars.append(bar)

    if len(orb_bars) < 2:
        logger.debug("ORB: not enough candles in ORB window ({} found)", len(orb_bars))
        return None

    orb_high = max(b["high"] for b in orb_bars)
    orb_low = min(b["low"] for b in orb_bars)
    orb_range = orb_high - orb_low
    mid_price = (orb_high + orb_low) / 2

    # Skip if ORB range too tight
    if mid_price > 0 and orb_range / mid_price < MIN_ORB_RANGE_PCT:
        logger.debug(
            "ORB: range too tight ({:.5f} / {:.2f} = {:.4%})",
            orb_range, mid_price, orb_range / mid_price,
        )
        return None

    # --- Phase 2: scan for FVG ---
    for i in range(2, len(scan_bars)):
        c1 = scan_bars[i - 2]
        c2 = scan_bars[i - 1]
        c3 = scan_bars[i]

        # Respect entry cutoff
        if _minutes_utc(c3["timestamp"]) > entry_cutoff:
            break

        signal = detect_fvg(c1, c2, c3, orb_high, orb_low)
        if signal is None:
            continue

        # Use C4.open as actual entry price if available
        c4_idx = i + 1
        if c4_idx < len(scan_bars):
            entry = scan_bars[c4_idx]["open"]
            signal.entry_price = entry

            # Recalculate TP with actual entry
            if signal.direction == SignalDirection.BUY:
                risk = entry - signal.stop_loss
                if risk <= 0:
                    return None
                signal.take_profit = entry + RR_RATIO * risk
            else:
                risk = signal.stop_loss - entry
                if risk <= 0:
                    return None
                signal.take_profit = entry - RR_RATIO * risk

        return signal

    return None


# ---------------------------------------------------------------------------
# Strategy class (BaseStrategy implementation)
# ---------------------------------------------------------------------------
class OrbFvgStrategy(BaseStrategy):
    """
    Opening Range Breakout + Fair Value Gap strategy.

    Designed for US equity session (09:30-16:00 EST) on M1 bars.
    """

    @property
    def name(self) -> str:
        return "orb_fvg"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_up", "trending_down"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        """Placeholder — returns HOLD. Real-time integration is Phase 4."""
        return TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=1,
            entry_price=current_bar.get("close", 0.0),
            strategy_name=self.name,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """Placeholder — returns input DataFrame unchanged. Backtest wiring is Phase 5."""
        return ohlc_df
