# ORB+FVG Strategy Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement and backtest the Opening Range Breakout + Fair Value Gap strategy on M1 data for 4 US assets over 12 months.

**Architecture:** Standalone strategy with dedicated M1 backtest runner. Data downloaded from Capital.com API, stored as Parquet. Strategy implements BaseStrategy interface for future MANTIS integration. No ML in Phase 1.

**Tech Stack:** Python 3.12, Polars, Pydantic v2, Capital.com REST API, pytest

---

### Task 1: Download M1 Historical Data

**Files:**
- Create: `backend/scripts/download_m1_data.py`

**Step 1: Write the download script**

```python
"""Download M1 historical candles from Capital.com for US assets."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import polars as pl

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.broker.client import CapitalComClient
from src.broker.models import Resolution


ASSETS = ["US500", "NAS100", "NVDA", "TSLA"]
CHUNK_SIZE = 10_000  # Max bars per request
MONTHS_BACK = 12
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "historical"


async def download_asset(client: CapitalComClient, epic: str) -> int:
    """Download M1 data for a single asset, chunked by date range."""
    total_written = 0
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=MONTHS_BACK * 30)

    # Work backwards in ~7-day chunks (10k M1 bars ~ 7 trading days)
    chunk_end = end_date
    chunk_num = 0

    while chunk_end > start_date:
        chunk_start = chunk_end - timedelta(days=8)
        if chunk_start < start_date:
            chunk_start = start_date

        chunk_num += 1
        print(f"  [{epic}] Chunk {chunk_num}: {chunk_start.date()} -> {chunk_end.date()}")

        try:
            candles = await client.get_historical_prices(
                epic=epic,
                resolution=Resolution.MINUTE,
                from_date=chunk_start,
                to_date=chunk_end,
                max_candles=CHUNK_SIZE,
            )
        except Exception as e:
            print(f"  [{epic}] Error: {e}, skipping chunk")
            chunk_end = chunk_start
            await asyncio.sleep(1)
            continue

        if not candles:
            print(f"  [{epic}] No data for this chunk")
            chunk_end = chunk_start
            continue

        # Convert to Polars DataFrame
        rows = []
        for c in candles:
            rows.append({
                "timestamp": c.timestamp,
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": float(c.last_traded_volume or 0),
            })

        df = pl.DataFrame(rows)

        # Group by month and write parquet files
        df = df.with_columns(
            pl.col("timestamp").dt.strftime("%Y-%m").alias("_month")
        )

        for month, month_df in df.group_by("_month"):
            month_str = month[0]
            out_dir = OUTPUT_DIR / epic / "1min"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"{month_str}.parquet"

            month_df = month_df.drop("_month").sort("timestamp")

            if out_path.exists():
                existing = pl.read_parquet(out_path)
                month_df = pl.concat([existing, month_df]).unique(
                    subset=["timestamp"]
                ).sort("timestamp")

            month_df.write_parquet(out_path)
            total_written += len(month_df)

        chunk_end = chunk_start
        await asyncio.sleep(0.15)  # Rate limit

    return total_written


async def main():
    client = CapitalComClient()
    await client.create_session()

    print(f"Downloading M1 data for {ASSETS} ({MONTHS_BACK} months)")
    print("=" * 60)

    for epic in ASSETS:
        print(f"\n[{epic}] Starting download...")
        count = await download_asset(client, epic)
        print(f"[{epic}] Done: {count} bars written")

    print("\n" + "=" * 60)
    print("Download complete!")

    # Summary
    for epic in ASSETS:
        data_dir = OUTPUT_DIR / epic / "1min"
        if data_dir.exists():
            files = list(data_dir.glob("*.parquet"))
            total = sum(len(pl.read_parquet(f)) for f in files)
            print(f"  {epic}: {len(files)} files, {total:,} bars")


if __name__ == "__main__":
    asyncio.run(main())
```

**Step 2: Run the download**

```bash
cd backend && .venv/Scripts/python.exe scripts/download_m1_data.py
```

Expected: Downloads ~98k bars per asset. Output shows progress per chunk.

**Step 3: Verify data**

```bash
cd backend && .venv/Scripts/python.exe -c "
import polars as pl
from pathlib import Path
for epic in ['US500', 'NAS100', 'NVDA', 'TSLA']:
    d = Path('data/historical') / epic / '1min'
    if d.exists():
        files = sorted(d.glob('*.parquet'))
        total = sum(len(pl.read_parquet(f)) for f in files)
        first = pl.read_parquet(files[0])['timestamp'].min()
        last = pl.read_parquet(files[-1])['timestamp'].max()
        print(f'{epic}: {total:>7,} bars | {first} -> {last}')
"
```

Expected: Each asset has 50k-100k bars spanning ~12 months.

**Step 4: Commit**

```bash
git add backend/scripts/download_m1_data.py
git commit -m "feat: add M1 data download script for ORB+FVG strategy"
```

---

### Task 2: ORB+FVG Strategy — Core Logic

**Files:**
- Create: `backend/src/strategy/orb_fvg_strategy.py`

**Step 1: Write the strategy module**

```python
"""
Opening Range Breakout + Fair Value Gap (FVG) Strategy.

Rule-based intraday strategy for US equities/indices:
1. Capture ORB (first 5 M1 candles: 09:30-09:35 EST)
2. Scan for FVG that coincides with ORB breakout
3. Enter at C4 open with R:R 2:1, no micro-management

Reference: docs/trading/FIRST-CANDLE-STRATEGY.md
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import polars as pl

from src.strategy.schemas import SignalDirection, TradingSignal, StrategyConfig
from src.strategy.base_strategy import BaseStrategy


# --- Constants ---

# US Market hours in UTC (EST + 5)
ORB_START_UTC = 14 * 60 + 30    # 09:30 EST = 14:30 UTC (minutes from midnight)
ORB_END_UTC = 14 * 60 + 35      # 09:35 EST = 14:35 UTC
SESSION_END_UTC = 20 * 60        # 16:00 EST = 20:00 UTC
ENTRY_CUTOFF_UTC = 19 * 60 + 30  # 15:30 EST = 19:30 UTC

ORB_CANDLES = 5  # First 5 M1 candles = 5 minutes
MIN_ORB_RANGE_PCT = 0.001  # 0.1% minimum range
RR_RATIO = 2.0


class SessionPhase(str, Enum):
    WAIT_FOR_ORB = "wait_for_orb"
    SCAN_FOR_FVG = "scan_for_fvg"
    IN_POSITION = "in_position"
    END_OF_DAY = "end_of_day"


@dataclass
class FVGSignal:
    """A detected Fair Value Gap with ORB breakout."""
    direction: str  # "BUY" or "SELL"
    fvg_type: str   # "bullish" or "bearish"
    entry_price: float
    stop_loss: float
    take_profit: float
    c2_bar: dict


@dataclass
class SessionState:
    """Tracks state within a single trading day."""
    phase: SessionPhase = SessionPhase.WAIT_FOR_ORB
    orb_high: float = 0.0
    orb_low: float = 0.0
    orb_range: float = 0.0
    orb_bars: list[dict] = field(default_factory=list)
    trade_taken: bool = False


def _minutes_utc(ts) -> int:
    """Extract minutes-from-midnight in UTC from a timestamp."""
    if hasattr(ts, "hour"):
        return ts.hour * 60 + ts.minute
    return 0


def detect_fvg(
    c1: dict, c2: dict, c3: dict,
    orb_high: float, orb_low: float,
) -> FVGSignal | None:
    """
    Detect a Fair Value Gap on 3 consecutive M1 candles
    that coincides with an ORB level breakout.

    Returns FVGSignal if valid, None otherwise.
    """
    # FVG Bullish: C3.low > C1.high (gap up)
    if c3["low"] > c1["high"] and c2["close"] > orb_high:
        entry = c3["close"]  # Will enter at next bar open (approximated)
        sl = c2["low"]
        risk = entry - sl
        if risk <= 0:
            return None
        tp = entry + RR_RATIO * risk
        return FVGSignal(
            direction="BUY",
            fvg_type="bullish",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            c2_bar=c2,
        )

    # FVG Bearish: C3.high < C1.low (gap down)
    if c3["high"] < c1["low"] and c2["close"] < orb_low:
        entry = c3["close"]
        sl = c2["high"]
        risk = sl - entry
        if risk <= 0:
            return None
        tp = entry - RR_RATIO * risk
        return FVGSignal(
            direction="SELL",
            fvg_type="bearish",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            c2_bar=c2,
        )

    return None


def process_session(bars: list[dict]) -> FVGSignal | None:
    """
    Process a full day of M1 bars for one asset.
    Returns the first valid FVG signal, or None.

    bars: list of dicts with keys: timestamp, open, high, low, close, volume
          Must be sorted by timestamp, all from the same trading day.
    """
    state = SessionState()

    for i, bar in enumerate(bars):
        mins = _minutes_utc(bar["timestamp"])

        # Phase: Collect ORB bars
        if state.phase == SessionPhase.WAIT_FOR_ORB:
            if ORB_START_UTC <= mins < ORB_END_UTC:
                state.orb_bars.append(bar)

            if len(state.orb_bars) >= ORB_CANDLES:
                state.orb_high = max(b["high"] for b in state.orb_bars)
                state.orb_low = min(b["low"] for b in state.orb_bars)
                state.orb_range = state.orb_high - state.orb_low

                # Filter: range too tight
                mid_price = (state.orb_high + state.orb_low) / 2
                if mid_price > 0 and state.orb_range / mid_price < MIN_ORB_RANGE_PCT:
                    state.phase = SessionPhase.END_OF_DAY
                    return None

                state.phase = SessionPhase.SCAN_FOR_FVG
            continue

        # Phase: Scan for FVG
        if state.phase == SessionPhase.SCAN_FOR_FVG:
            # Past entry cutoff?
            if mins >= ENTRY_CUTOFF_UTC:
                state.phase = SessionPhase.END_OF_DAY
                return None

            # Need at least 3 bars to check FVG (current + 2 prior)
            if i < 2:
                continue

            c1 = bars[i - 2]
            c2 = bars[i - 1]
            c3 = bar

            fvg = detect_fvg(c1, c2, c3, state.orb_high, state.orb_low)
            if fvg is not None:
                # Entry at next bar open (C4)
                if i + 1 < len(bars):
                    fvg.entry_price = bars[i + 1]["open"]
                    # Recalculate TP with actual entry
                    if fvg.direction == "BUY":
                        risk = fvg.entry_price - fvg.stop_loss
                        if risk > 0:
                            fvg.take_profit = fvg.entry_price + RR_RATIO * risk
                        else:
                            return None
                    else:
                        risk = fvg.stop_loss - fvg.entry_price
                        if risk > 0:
                            fvg.take_profit = fvg.entry_price - RR_RATIO * risk
                        else:
                            return None
                return fvg

    return None


class OrbFvgStrategy(BaseStrategy):
    """Opening Range Breakout + Fair Value Gap strategy."""

    @property
    def name(self) -> str:
        return "orb_fvg"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_up", "trending_down", "ranging"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        """Real-time signal generation (placeholder for future integration)."""
        return TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=1,
            entry_price=current_bar.get("close", 0),
            strategy_name="orb_fvg",
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """Batch signal generation — delegates to process_session per day."""
        return ohlc_df.with_columns(
            pl.lit(1).alias("signal"),
            pl.lit(0.0).alias("confidence"),
        )
```

**Step 2: Commit**

```bash
git add backend/src/strategy/orb_fvg_strategy.py
git commit -m "feat: add ORB+FVG strategy core logic"
```

---

### Task 3: ORB+FVG Strategy — Unit Tests

**Files:**
- Create: `backend/tests/strategy/test_orb_fvg.py`

**Step 1: Write the tests**

```python
"""Tests for Opening Range Breakout + Fair Value Gap strategy."""

from datetime import datetime, timezone

import pytest

from src.strategy.orb_fvg_strategy import (
    OrbFvgStrategy,
    detect_fvg,
    process_session,
    SessionState,
    SessionPhase,
    FVGSignal,
    _minutes_utc,
)


def _bar(hour: int, minute: int, o: float, h: float, l: float, c: float, vol: int = 1000) -> dict:
    """Helper to create an M1 bar dict at a specific UTC time."""
    return {
        "timestamp": datetime(2026, 1, 15, hour, minute, tzinfo=timezone.utc),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": vol,
    }


class TestMinutesUtc:
    def test_morning(self):
        ts = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
        assert _minutes_utc(ts) == 14 * 60 + 30

    def test_afternoon(self):
        ts = datetime(2026, 1, 15, 19, 45, tzinfo=timezone.utc)
        assert _minutes_utc(ts) == 19 * 60 + 45


class TestDetectFvg:
    def test_bullish_fvg_with_orb_breakout(self):
        c1 = _bar(14, 40, 100.0, 100.5, 99.5, 100.2)
        c2 = _bar(14, 41, 100.3, 101.5, 100.1, 101.2)  # Closes above orb_high=100.8
        c3 = _bar(14, 42, 101.0, 101.8, 100.6, 101.5)   # C3.low(100.6) > C1.high(100.5) = gap
        result = detect_fvg(c1, c2, c3, orb_high=100.8, orb_low=99.2)
        assert result is not None
        assert result.direction == "BUY"
        assert result.fvg_type == "bullish"
        assert result.stop_loss == c2["low"]  # 100.1

    def test_bearish_fvg_with_orb_breakout(self):
        c1 = _bar(14, 40, 100.0, 100.5, 99.5, 100.0)
        c2 = _bar(14, 41, 99.8, 99.9, 98.5, 98.8)   # Closes below orb_low=99.2
        c3 = _bar(14, 42, 98.6, 99.3, 98.2, 98.5)     # C3.high(99.3) < C1.low(99.5) = gap
        result = detect_fvg(c1, c2, c3, orb_high=100.8, orb_low=99.2)
        assert result is not None
        assert result.direction == "SELL"
        assert result.fvg_type == "bearish"
        assert result.stop_loss == c2["high"]  # 99.9

    def test_no_fvg_without_gap(self):
        c1 = _bar(14, 40, 100.0, 100.5, 99.5, 100.0)
        c2 = _bar(14, 41, 100.1, 100.6, 99.8, 100.3)
        c3 = _bar(14, 42, 100.2, 100.7, 100.0, 100.5)  # C3.low(100.0) < C1.high(100.5) = no gap
        result = detect_fvg(c1, c2, c3, orb_high=100.8, orb_low=99.2)
        assert result is None

    def test_fvg_without_orb_breakout_rejected(self):
        c1 = _bar(14, 40, 100.0, 100.2, 99.8, 100.1)
        c2 = _bar(14, 41, 100.1, 100.5, 100.0, 100.3)  # Closes 100.3, below orb_high=100.8
        c3 = _bar(14, 42, 100.4, 100.7, 100.3, 100.5)   # C3.low(100.3) > C1.high(100.2) = gap
        result = detect_fvg(c1, c2, c3, orb_high=100.8, orb_low=99.2)
        assert result is None  # Gap exists but no ORB breakout

    def test_zero_risk_rejected(self):
        c1 = _bar(14, 40, 100.0, 100.0, 99.5, 100.0)
        c2 = _bar(14, 41, 100.0, 101.5, 101.0, 101.2)  # low == entry -> zero risk
        c3 = _bar(14, 42, 101.0, 101.8, 100.1, 101.5)   # C3.low(100.1) > C1.high(100.0)
        result = detect_fvg(c1, c2, c3, orb_high=100.8, orb_low=99.2)
        # entry ~101.5, sl = c2.low = 101.0, risk = 0.5 -> valid
        if result:
            assert result.stop_loss < result.entry_price


class TestProcessSession:
    def _make_orb_bars(self, orb_high: float = 100.8, orb_low: float = 99.5) -> list[dict]:
        """Create 5 ORB M1 bars (09:30-09:34 EST = 14:30-14:34 UTC)."""
        bars = []
        for m in range(5):
            bars.append(_bar(14, 30 + m, 100.0, orb_high, orb_low, 100.2))
        return bars

    def test_valid_session_returns_signal(self):
        orb = self._make_orb_bars(orb_high=100.8, orb_low=99.5)
        # Post-ORB bars with bullish FVG breaking above orb_high
        post = [
            _bar(14, 35, 100.3, 100.5, 100.1, 100.4),  # C1
            _bar(14, 36, 100.5, 101.5, 100.2, 101.2),   # C2: close > orb_high (100.8)
            _bar(14, 37, 101.0, 101.8, 100.6, 101.5),   # C3: low(100.6) > C1.high(100.5) = FVG
            _bar(14, 38, 101.4, 101.9, 101.2, 101.7),   # C4: entry at open
        ]
        result = process_session(orb + post)
        assert result is not None
        assert result.direction == "BUY"
        assert result.entry_price == 101.4  # C4 open

    def test_tight_range_skips_session(self):
        # ORB range < 0.1% of price
        orb = self._make_orb_bars(orb_high=100.05, orb_low=100.0)  # range=0.05, 0.05%
        post = [_bar(14, 35 + i, 100.0, 100.1, 99.9, 100.0) for i in range(10)]
        result = process_session(orb + post)
        assert result is None

    def test_no_fvg_returns_none(self):
        orb = self._make_orb_bars()
        # Flat bars, no FVG
        post = [_bar(14, 35 + i, 100.0, 100.2, 99.8, 100.1) for i in range(20)]
        result = process_session(orb + post)
        assert result is None

    def test_cutoff_time_stops_scanning(self):
        orb = self._make_orb_bars()
        # FVG forms after 15:30 EST (19:30 UTC) -> should not trigger
        late_bars = [
            _bar(19, 30, 100.0, 100.5, 99.5, 100.2),
            _bar(19, 31, 100.3, 101.5, 100.1, 101.2),
            _bar(19, 32, 101.0, 101.8, 100.6, 101.5),
            _bar(19, 33, 101.4, 101.9, 101.2, 101.7),
        ]
        # Need filler bars between ORB and late_bars
        filler = [_bar(14, 35 + i, 100.0, 100.2, 99.8, 100.1) for i in range(295)]
        result = process_session(orb + filler + late_bars)
        assert result is None


class TestOrbFvgStrategy:
    def test_name(self):
        s = OrbFvgStrategy()
        assert s.name == "orb_fvg"

    def test_applicable_regimes(self):
        s = OrbFvgStrategy()
        assert "trending_up" in s.applicable_regimes

    def test_rr_ratio_is_2(self):
        c1 = _bar(14, 40, 100.0, 100.2, 99.8, 100.0)
        c2 = _bar(14, 41, 100.3, 101.5, 100.0, 101.0)
        c3 = _bar(14, 42, 101.0, 101.8, 100.3, 101.5)
        fvg = detect_fvg(c1, c2, c3, orb_high=100.8, orb_low=99.2)
        if fvg:
            risk = fvg.entry_price - fvg.stop_loss
            reward = fvg.take_profit - fvg.entry_price
            assert abs(reward / risk - 2.0) < 0.01
```

**Step 2: Run tests to verify they pass**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_orb_fvg.py -v --no-cov
```

Expected: All tests PASS.

**Step 3: Commit**

```bash
git add backend/tests/strategy/test_orb_fvg.py
git commit -m "test: add ORB+FVG strategy unit tests"
```

---

### Task 4: Backtest Runner

**Files:**
- Create: `backend/src/backtest/orb_fvg_runner.py`

**Step 1: Write the backtest runner**

```python
"""
Dedicated intraday M1 backtest runner for the ORB+FVG strategy.

Groups M1 bars by trading day, runs process_session() for each,
simulates trade execution with SL/TP, and computes aggregate metrics.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

from src.strategy.orb_fvg_strategy import (
    process_session,
    FVGSignal,
    SESSION_END_UTC,
    _minutes_utc,
)


@dataclass
class ORBTrade:
    date: str
    epic: str
    direction: str
    orb_high: float
    orb_low: float
    fvg_type: str
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float = 0.0
    exit_reason: str = ""  # TP, SL, EOD
    pnl: float = 0.0
    bars_in_trade: int = 0


@dataclass
class ORBBacktestResult:
    epic: str
    period: str
    total_sessions: int = 0
    trades_taken: int = 0
    sessions_skipped: int = 0
    win_rate: float = 0.0
    avg_rr_achieved: float = 0.0
    total_pnl: float = 0.0
    max_consecutive_losses: int = 0
    max_drawdown_pct: float = 0.0
    sharpe_ratio: float = 0.0
    profit_factor: float = 0.0
    trades: list[ORBTrade] = field(default_factory=list)
    daily_equity: list[float] = field(default_factory=list)


def _simulate_trade(
    fvg: FVGSignal,
    bars_after_entry: list[dict],
    epic: str,
    date_str: str,
) -> ORBTrade:
    """
    Simulate a single trade by walking through M1 bars after entry.
    Exit at SL, TP, or EOD (16:00 EST = 20:00 UTC).
    """
    trade = ORBTrade(
        date=date_str,
        epic=epic,
        direction=fvg.direction,
        orb_high=0.0,  # Filled by caller
        orb_low=0.0,
        fvg_type=fvg.fvg_type,
        entry_price=fvg.entry_price,
        stop_loss=fvg.stop_loss,
        take_profit=fvg.take_profit,
    )

    for i, bar in enumerate(bars_after_entry):
        mins = _minutes_utc(bar["timestamp"])

        if fvg.direction == "BUY":
            # Check SL hit (low touches SL)
            if bar["low"] <= fvg.stop_loss:
                trade.exit_price = fvg.stop_loss
                trade.exit_reason = "SL"
                trade.bars_in_trade = i + 1
                trade.pnl = fvg.stop_loss - fvg.entry_price
                return trade
            # Check TP hit (high touches TP)
            if bar["high"] >= fvg.take_profit:
                trade.exit_price = fvg.take_profit
                trade.exit_reason = "TP"
                trade.bars_in_trade = i + 1
                trade.pnl = fvg.take_profit - fvg.entry_price
                return trade
        else:  # SELL
            # Check SL hit (high touches SL)
            if bar["high"] >= fvg.stop_loss:
                trade.exit_price = fvg.stop_loss
                trade.exit_reason = "SL"
                trade.bars_in_trade = i + 1
                trade.pnl = fvg.entry_price - fvg.stop_loss
                return trade
            # Check TP hit (low touches TP)
            if bar["low"] <= fvg.take_profit:
                trade.exit_price = fvg.take_profit
                trade.exit_reason = "TP"
                trade.bars_in_trade = i + 1
                trade.pnl = fvg.entry_price - fvg.take_profit
                return trade

        # EOD check
        if mins >= SESSION_END_UTC:
            trade.exit_price = bar["close"]
            trade.exit_reason = "EOD"
            trade.bars_in_trade = i + 1
            if fvg.direction == "BUY":
                trade.pnl = bar["close"] - fvg.entry_price
            else:
                trade.pnl = fvg.entry_price - bar["close"]
            return trade

    # Ran out of bars (shouldn't happen with full day data)
    if bars_after_entry:
        last = bars_after_entry[-1]
        trade.exit_price = last["close"]
        trade.exit_reason = "EOD"
        trade.bars_in_trade = len(bars_after_entry)
        if fvg.direction == "BUY":
            trade.pnl = last["close"] - fvg.entry_price
        else:
            trade.pnl = fvg.entry_price - last["close"]
    return trade


def run_backtest(
    epic: str,
    data_dir: Path | str = "data/historical",
    initial_capital: float = 10_000.0,
    risk_per_trade: float = 0.02,
) -> ORBBacktestResult:
    """
    Run ORB+FVG backtest on M1 data for a single asset.

    Args:
        epic: Asset code (US500, NAS100, NVDA, TSLA)
        data_dir: Base directory for historical data
        initial_capital: Starting capital in USD
        risk_per_trade: Fraction of capital risked per trade

    Returns:
        ORBBacktestResult with all trades and metrics
    """
    data_path = Path(data_dir) / epic / "1min"
    if not data_path.exists():
        raise FileNotFoundError(f"No M1 data found at {data_path}")

    # Load all M1 parquet files
    files = sorted(data_path.glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"No parquet files in {data_path}")

    df = pl.concat([pl.read_parquet(f) for f in files]).sort("timestamp")

    # Add date column for grouping by trading day
    df = df.with_columns(pl.col("timestamp").dt.date().alias("_date"))

    dates = df["_date"].unique().sort().to_list()
    first_date = str(dates[0])
    last_date = str(dates[-1])

    result = ORBBacktestResult(epic=epic, period=f"{first_date} -> {last_date}")
    equity = initial_capital

    for date in dates:
        day_df = df.filter(pl.col("_date") == date).sort("timestamp")
        day_bars = day_df.drop("_date").to_dicts()

        if len(day_bars) < 10:  # Need at least ORB + some scan bars
            result.sessions_skipped += 1
            continue

        result.total_sessions += 1
        fvg = process_session(day_bars)

        if fvg is None:
            result.sessions_skipped += 1
            result.daily_equity.append(equity)
            continue

        # Find the bar index where entry happens (C4)
        entry_idx = None
        for i, bar in enumerate(day_bars):
            if bar["close"] == fvg.entry_price or (
                i > 0 and bar["open"] == fvg.entry_price
            ):
                entry_idx = i
                break

        if entry_idx is None:
            # Fallback: find first bar after ORB where price matches
            for i, bar in enumerate(day_bars):
                if bar["open"] == fvg.entry_price:
                    entry_idx = i
                    break

        if entry_idx is None:
            # Use approximate: find bar closest to entry time
            entry_idx = min(len(day_bars) - 1, 8)  # ORB(5) + FVG(3) = bar 8

        bars_after = day_bars[entry_idx:]

        # Position sizing: risk_per_trade % of equity
        risk_distance = abs(fvg.entry_price - fvg.stop_loss)
        if risk_distance <= 0:
            result.sessions_skipped += 1
            result.daily_equity.append(equity)
            continue

        risk_amount = equity * risk_per_trade
        position_size = risk_amount / risk_distance

        trade = _simulate_trade(fvg, bars_after, epic, str(date))
        trade.orb_high = max(b["high"] for b in day_bars[:5]) if len(day_bars) >= 5 else 0
        trade.orb_low = min(b["low"] for b in day_bars[:5]) if len(day_bars) >= 5 else 0

        # Scale P&L by position size
        trade.pnl = trade.pnl * position_size

        equity += trade.pnl
        result.trades.append(trade)
        result.trades_taken += 1
        result.daily_equity.append(equity)

    # Calculate aggregate metrics
    _calculate_metrics(result, initial_capital)
    return result


def _calculate_metrics(result: ORBBacktestResult, initial_capital: float) -> None:
    """Compute win rate, drawdown, Sharpe, profit factor from trades."""
    if not result.trades:
        return

    wins = [t for t in result.trades if t.pnl > 0]
    losses = [t for t in result.trades if t.pnl <= 0]

    result.win_rate = len(wins) / len(result.trades) if result.trades else 0

    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    result.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    result.total_pnl = sum(t.pnl for t in result.trades)

    # Average R:R achieved
    rrs = []
    for t in result.trades:
        risk = abs(t.entry_price - t.stop_loss)
        if risk > 0:
            rrs.append(t.pnl / (risk * (t.pnl / abs(t.pnl) if t.pnl != 0 else 1)))
    result.avg_rr_achieved = sum(rrs) / len(rrs) if rrs else 0

    # Max consecutive losses
    max_consec = 0
    current_consec = 0
    for t in result.trades:
        if t.pnl <= 0:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0
    result.max_consecutive_losses = max_consec

    # Max drawdown
    peak = initial_capital
    max_dd = 0
    equity = initial_capital
    for t in result.trades:
        equity += t.pnl
        peak = max(peak, equity)
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)
    result.max_drawdown_pct = max_dd

    # Sharpe ratio (annualized, using daily P&L)
    daily_pnls = [t.pnl for t in result.trades]
    if len(daily_pnls) > 1:
        import statistics
        mean_pnl = statistics.mean(daily_pnls)
        std_pnl = statistics.stdev(daily_pnls)
        if std_pnl > 0:
            result.sharpe_ratio = (mean_pnl / std_pnl) * (252 ** 0.5)


def save_result(result: ORBBacktestResult, output_dir: str = "data/backtest_results") -> Path:
    """Save backtest result to JSON."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"orb_fvg_{result.epic}_{ts}.json"
    out_path = out_dir / filename

    data = asdict(result)
    with open(out_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    return out_path


def print_summary(result: ORBBacktestResult) -> None:
    """Print a formatted summary of backtest results."""
    print(f"\n{'=' * 55}")
    print(f" ORB+FVG Backtest Results: {result.epic}")
    print(f"{'=' * 55}")
    print(f" Period:        {result.period}")
    print(f" Sessions:      {result.total_sessions}")
    print(f" Trades:        {result.trades_taken} (skipped: {result.sessions_skipped})")
    print(f" Win Rate:      {result.win_rate:.1%}")
    print(f" Profit Factor: {result.profit_factor:.2f}")
    print(f" Total P&L:     ${result.total_pnl:,.2f}")
    print(f" Max Drawdown:  {result.max_drawdown_pct:.1%}")
    print(f" Sharpe Ratio:  {result.sharpe_ratio:.2f}")
    print(f" Max Consec L:  {result.max_consecutive_losses}")

    # Exit reason breakdown
    tp_count = sum(1 for t in result.trades if t.exit_reason == "TP")
    sl_count = sum(1 for t in result.trades if t.exit_reason == "SL")
    eod_count = sum(1 for t in result.trades if t.exit_reason == "EOD")
    print(f" Exits:         TP={tp_count} SL={sl_count} EOD={eod_count}")
    print(f"{'=' * 55}\n")
```

**Step 2: Commit**

```bash
git add backend/src/backtest/orb_fvg_runner.py
git commit -m "feat: add dedicated ORB+FVG M1 backtest runner"
```

---

### Task 5: Backtest Runner Tests

**Files:**
- Create: `backend/tests/backtest/test_orb_fvg_runner.py`

**Step 1: Write the runner tests**

```python
"""Tests for ORB+FVG backtest runner."""

from datetime import datetime, timezone

import pytest

from src.backtest.orb_fvg_runner import (
    _simulate_trade,
    _calculate_metrics,
    ORBTrade,
    ORBBacktestResult,
)
from src.strategy.orb_fvg_strategy import FVGSignal


def _bar(hour: int, minute: int, o: float, h: float, l: float, c: float) -> dict:
    return {
        "timestamp": datetime(2026, 1, 15, hour, minute, tzinfo=timezone.utc),
        "open": o, "high": h, "low": l, "close": c, "volume": 1000,
    }


class TestSimulateTrade:
    def test_buy_hits_tp(self):
        fvg = FVGSignal(
            direction="BUY", fvg_type="bullish",
            entry_price=100.0, stop_loss=99.0, take_profit=102.0,
            c2_bar={},
        )
        bars = [
            _bar(14, 40, 100.0, 100.5, 99.5, 100.3),
            _bar(14, 41, 100.3, 102.5, 100.1, 102.0),  # High hits TP
        ]
        trade = _simulate_trade(fvg, bars, "US500", "2026-01-15")
        assert trade.exit_reason == "TP"
        assert trade.pnl == 2.0  # 102 - 100

    def test_buy_hits_sl(self):
        fvg = FVGSignal(
            direction="BUY", fvg_type="bullish",
            entry_price=100.0, stop_loss=99.0, take_profit=102.0,
            c2_bar={},
        )
        bars = [
            _bar(14, 40, 100.0, 100.2, 98.5, 99.5),  # Low hits SL
        ]
        trade = _simulate_trade(fvg, bars, "US500", "2026-01-15")
        assert trade.exit_reason == "SL"
        assert trade.pnl == -1.0  # 99 - 100

    def test_sell_hits_tp(self):
        fvg = FVGSignal(
            direction="SELL", fvg_type="bearish",
            entry_price=100.0, stop_loss=101.0, take_profit=98.0,
            c2_bar={},
        )
        bars = [
            _bar(14, 40, 100.0, 100.3, 97.5, 98.0),  # Low hits TP
        ]
        trade = _simulate_trade(fvg, bars, "US500", "2026-01-15")
        assert trade.exit_reason == "TP"
        assert trade.pnl == 2.0  # 100 - 98

    def test_eod_exit(self):
        fvg = FVGSignal(
            direction="BUY", fvg_type="bullish",
            entry_price=100.0, stop_loss=99.0, take_profit=102.0,
            c2_bar={},
        )
        bars = [
            _bar(19, 59, 100.0, 100.3, 99.5, 100.2),  # Before EOD
            _bar(20, 0, 100.2, 100.4, 100.0, 100.3),   # At 20:00 UTC = EOD
        ]
        trade = _simulate_trade(fvg, bars, "US500", "2026-01-15")
        assert trade.exit_reason == "EOD"
        assert trade.pnl == pytest.approx(0.3, abs=0.01)


class TestCalculateMetrics:
    def test_win_rate(self):
        result = ORBBacktestResult(epic="US500", period="test")
        result.trades = [
            ORBTrade(date="", epic="", direction="BUY", orb_high=0, orb_low=0,
                     fvg_type="", entry_price=100, stop_loss=99, take_profit=102,
                     exit_price=102, exit_reason="TP", pnl=50.0, bars_in_trade=10),
            ORBTrade(date="", epic="", direction="BUY", orb_high=0, orb_low=0,
                     fvg_type="", entry_price=100, stop_loss=99, take_profit=102,
                     exit_price=99, exit_reason="SL", pnl=-25.0, bars_in_trade=5),
        ]
        _calculate_metrics(result, 10000.0)
        assert result.win_rate == 0.5
        assert result.profit_factor == 2.0
        assert result.total_pnl == 25.0

    def test_empty_trades(self):
        result = ORBBacktestResult(epic="US500", period="test")
        _calculate_metrics(result, 10000.0)
        assert result.win_rate == 0
```

**Step 2: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/backtest/test_orb_fvg_runner.py -v --no-cov
```

Expected: All PASS.

**Step 3: Commit**

```bash
git add backend/tests/backtest/test_orb_fvg_runner.py
git commit -m "test: add ORB+FVG backtest runner tests"
```

---

### Task 6: Run Script — Execute 12-Month Backtest

**Files:**
- Create: `backend/scripts/run_orb_fvg_backtest.py`

**Step 1: Write the run script**

```python
"""Run ORB+FVG backtest on all 4 US assets and print results."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.backtest.orb_fvg_runner import run_backtest, print_summary, save_result

ASSETS = ["US500", "NAS100", "NVDA", "TSLA"]
DATA_DIR = Path(__file__).parent.parent / "data" / "historical"


def main():
    print("=" * 60)
    print(" ORB+FVG Strategy — 12-Month Backtest")
    print("=" * 60)

    all_results = []

    for epic in ASSETS:
        data_path = DATA_DIR / epic / "1min"
        if not data_path.exists():
            print(f"\n[{epic}] No M1 data found, skipping")
            continue

        print(f"\n[{epic}] Running backtest...")
        result = run_backtest(
            epic=epic,
            data_dir=str(DATA_DIR),
            initial_capital=10_000.0,
            risk_per_trade=0.02,
        )
        print_summary(result)
        path = save_result(result)
        print(f"  Saved to: {path}")
        all_results.append(result)

    # Combined summary
    if all_results:
        print("\n" + "=" * 60)
        print(" COMBINED SUMMARY")
        print("=" * 60)
        total_trades = sum(r.trades_taken for r in all_results)
        total_pnl = sum(r.total_pnl for r in all_results)
        avg_wr = sum(r.win_rate for r in all_results) / len(all_results)
        avg_pf = sum(r.profit_factor for r in all_results) / len(all_results)
        avg_sharpe = sum(r.sharpe_ratio for r in all_results) / len(all_results)
        max_dd = max(r.max_drawdown_pct for r in all_results)

        print(f" Assets:        {len(all_results)}")
        print(f" Total Trades:  {total_trades}")
        print(f" Combined P&L:  ${total_pnl:,.2f}")
        print(f" Avg Win Rate:  {avg_wr:.1%}")
        print(f" Avg PF:        {avg_pf:.2f}")
        print(f" Avg Sharpe:    {avg_sharpe:.2f}")
        print(f" Worst DD:      {max_dd:.1%}")

        # Integration recommendation
        print(f"\n{'─' * 60}")
        if avg_wr > 0.50 and avg_pf > 1.5 and avg_sharpe > 1.0:
            print(" RECOMMENDATION: INTEGRATE into MANTIS (Phase 2)")
        elif avg_wr > 0.45 and avg_pf > 1.2:
            print(" RECOMMENDATION: PROMISING — add ML filter (Phase 2b)")
        else:
            print(" RECOMMENDATION: NOT VIABLE — needs redesign")
        print(f"{'─' * 60}")


if __name__ == "__main__":
    main()
```

**Step 2: Run the backtest**

```bash
cd backend && .venv/Scripts/python.exe scripts/run_orb_fvg_backtest.py
```

Expected: Results for each asset + combined summary + integration recommendation.

**Step 3: Commit results**

```bash
git add backend/scripts/run_orb_fvg_backtest.py
git commit -m "feat: add ORB+FVG backtest runner script with combined analysis"
```

---

### Task 7: Analyze Results and Report

**No new files — analysis task.**

After running the backtest, evaluate against Phase 2 criteria:

| Metric | Target | Action if met |
|--------|--------|---------------|
| Win Rate > 50% | Integrate as-is | |
| Profit Factor > 1.5 | Add to MANTIS paper loop | |
| Sharpe > 1.0 | Run alongside ScalpScore | |
| Max DD < 10% | Safe for capital | |
| WR 45-50%, PF 1.2-1.5 | Add ML filter | Train XGBoost on trade features |
| Below thresholds | Redesign or discard | |

Report findings to user with exact numbers and recommendation.

---

## Execution Order Summary

| Task | Description | Dependencies |
|------|-------------|--------------|
| 1 | Download M1 data | None (needs broker credentials) |
| 2 | Core strategy logic | None |
| 3 | Strategy unit tests | Task 2 |
| 4 | Backtest runner | Task 2 |
| 5 | Runner tests | Task 4 |
| 6 | Run backtest script | Tasks 1, 4 |
| 7 | Analyze results | Task 6 |

Tasks 2-3 and 4-5 can run in parallel with Task 1 (data download).
