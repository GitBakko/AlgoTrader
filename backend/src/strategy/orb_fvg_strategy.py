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

Live integration:
  - Maintains per-epic session state across calls
  - Receives M1 bars via recent_bars DataFrame
  - ML filter (XGBoost) loaded from disk if available
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
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
    utc_dt = et_dt.astimezone(UTC)
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
    fvg_type: str  # "bullish" or "bearish"
    entry_price: float  # C4.open (filled by process_session)
    stop_loss: float
    take_profit: float
    c2_bar: dict  # the breakout candle


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
            orb_range,
            mid_price,
            orb_range / mid_price,
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
# Per-epic session state for live trading
# ---------------------------------------------------------------------------
@dataclass
class _SessionState:
    """Tracks ORB+FVG state for one epic across a single NYSE trading day."""

    session_date: date | None = None
    orb_bars: list[dict] = field(default_factory=list)
    scan_bars: list[dict] = field(default_factory=list)
    orb_high: float = 0.0
    orb_low: float = 0.0
    orb_ready: bool = False
    traded_today: bool = False
    last_bar_ts: datetime | None = None

    def reset(self, new_date: date) -> None:
        self.session_date = new_date
        self.orb_bars = []
        self.scan_bars = []
        self.orb_high = 0.0
        self.orb_low = 0.0
        self.orb_ready = False
        self.traded_today = False
        self.last_bar_ts = None


# ML filter model path
_ML_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "orb_fvg"


# ---------------------------------------------------------------------------
# Strategy class (BaseStrategy implementation)
# ---------------------------------------------------------------------------
class OrbFvgStrategy(BaseStrategy):
    """
    Opening Range Breakout + Fair Value Gap strategy with ML filter.

    Designed for US equity session (09:30-16:00 EST) on M1 bars.
    Maintains per-epic session state across calls for live trading.
    """

    def __init__(self, ml_threshold: float = 0.50):
        self._sessions: dict[str, _SessionState] = {}
        self._ml_model = None
        self._ml_threshold = ml_threshold
        self._ml_load_attempted = False

    @property
    def name(self) -> str:
        return "orb_fvg"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_up", "trending_down"]

    def _load_ml_filter(self) -> None:
        """Load pre-trained XGBoost ML filter from disk (once)."""
        if self._ml_load_attempted:
            return
        self._ml_load_attempted = True

        model_path = _ML_MODEL_DIR / "filter_model.json"
        if not model_path.exists():
            logger.info("ORB+FVG: no ML filter model found, running without filter")
            return

        try:
            import xgboost as xgb

            self._ml_model = xgb.XGBClassifier()
            self._ml_model.load_model(str(model_path))
            logger.info(f"ORB+FVG: loaded ML filter from {model_path}")
        except Exception as e:
            logger.warning(f"ORB+FVG: failed to load ML filter: {e}")
            self._ml_model = None

    def _get_session(self, epic: str) -> _SessionState:
        if epic not in self._sessions:
            self._sessions[epic] = _SessionState()
        return self._sessions[epic]

    def _apply_ml_filter(self, fvg: FVGSignal, day_bars: list[dict]) -> float | None:
        """
        Run ML filter on an FVG signal. Returns predicted probability
        of win, or None if no model loaded.
        """
        self._load_ml_filter()
        if self._ml_model is None:
            return None

        from src.backtest.orb_fvg_ml_filter import extract_features

        features = extract_features(day_bars, fvg, trade_pnl=0, exit_reason="")
        X = np.array([features.to_array()])
        prob = self._ml_model.predict_proba(X)[0][1]
        return float(prob)

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        """
        Live ORB+FVG signal generation using M1 bars.

        recent_bars must be a DataFrame of M1 OHLCV bars for today's session
        (columns: timestamp, open, high, low, close). The strategy accumulates
        these bars into its internal session state and scans for FVG signals.
        """
        hold = TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=1,
            entry_price=current_bar.get("close", 0.0),
            strategy_name=self.name,
        )

        # Need M1 bars in recent_bars
        if recent_bars is None or recent_bars.is_empty():
            return hold

        required_cols = {"timestamp", "open", "high", "low", "close"}
        if not required_cols.issubset(set(recent_bars.columns)):
            logger.debug(f"ORB+FVG [{epic}]: recent_bars missing M1 columns")
            return hold

        # Convert DataFrame to list of dicts for process_session()
        m1_bars = recent_bars.sort("timestamp").to_dicts()
        if not m1_bars:
            return hold

        # Determine session date (NYSE date from first bar)
        first_ts = m1_bars[0]["timestamp"]
        if hasattr(first_ts, "date"):
            et_dt = first_ts.replace(tzinfo=UTC).astimezone(_ET)
            session_day = et_dt.date()
        else:
            return hold

        # Get/reset session state
        sess = self._get_session(epic)
        if sess.session_date != session_day:
            sess.reset(session_day)
            logger.debug(f"ORB+FVG [{epic}]: new session {session_day}")

        if sess.traded_today:
            return hold

        # Run process_session on today's M1 bars
        fvg = process_session(m1_bars)
        if fvg is None:
            return hold

        # Apply ML filter
        ml_prob = self._apply_ml_filter(fvg, m1_bars)
        if ml_prob is not None:
            if ml_prob < self._ml_threshold:
                logger.info(
                    f"ORB+FVG [{epic}]: FVG found but ML filter rejects "
                    f"(prob={ml_prob:.3f} < {self._ml_threshold})"
                )
                return hold
            logger.info(f"ORB+FVG [{epic}]: ML filter approves (prob={ml_prob:.3f})")

        # Mark as traded for today
        sess.traded_today = True

        # Confidence: base 0.60 + ML boost
        confidence = 0.60
        if ml_prob is not None:
            confidence = min(0.50 + ml_prob * 0.40, 0.90)

        signal = TradingSignal(
            epic=epic,
            direction=fvg.direction,
            confidence=confidence,
            signal_class=0 if fvg.direction == SignalDirection.BUY else 2,
            entry_price=fvg.entry_price,
            suggested_stop=fvg.stop_loss,
            suggested_tp=fvg.take_profit,
            technical_confirmation=True,
            strategy_name=self.name,
        )

        logger.info(
            f"ORB+FVG [{epic}]: {fvg.direction.value} signal "
            f"entry={fvg.entry_price:.2f} SL={fvg.stop_loss:.2f} "
            f"TP={fvg.take_profit:.2f} conf={confidence:.2f}"
        )
        return signal

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """Placeholder — use orb_fvg_runner for backtesting."""
        return ohlc_df
