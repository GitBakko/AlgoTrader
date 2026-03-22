# ORB+FVG Strategy Design — Opening Range Breakout with Fair Value Gap

**Date**: 2026-03-07
**Status**: Approved
**Assets**: US500, NAS100, NVDA, TSLA (US equities/indices only)
**Timeframe**: M1 (1-minute candles)
**Session**: NYSE Regular Hours 09:30-16:00 EST (13:30-20:00 UTC)

---

## Overview

Implement the "Opening Range Breakout with Fair Value Gap" strategy as described in
`docs/trading/FIRST-CANDLE-STRATEGY.md`. This is a rule-based intraday strategy that:

1. Captures the HIGH/LOW of the first 5-minute candle (09:30-09:35 EST)
2. Monitors M1 candles for Fair Value Gaps (FVG) that coincide with ORB breakouts
3. Enters with fixed R:R 2:1, no micro-management

Two phases:
- **Phase 1**: Pure rule-based implementation + backtest (12 months)
- **Phase 2**: ML filter layer (only if Phase 1 results are positive)

---

## 1. Data Pipeline

### Script: `scripts/download_m1_data.py`

Downloads M1 candles from Capital.com demo API for 4 US assets, covering 12 months.

- Authenticates via `.env` credentials (existing `CapitalComClient`)
- Fetches in chunks of 10,000 bars (~7 trading days) iterating backward
- Rate limiting: 100ms between requests, exponential backoff on errors
- Storage: `backend/data/historical/{EPIC}/1min/YYYY-MM.parquet`
- Schema: `timestamp, open, high, low, close, volume` (same as existing timeframes)

**Estimates**:
- ~98,000 bars per asset (390 min/session x 252 days)
- ~10 chunks per asset x 4 assets = ~40 API requests
- ~20 seconds total download time

---

## 2. Core Strategy Logic

### File: `backend/src/strategy/orb_fvg_strategy.py`

Session state machine with 3 phases per trading day:

```
WAIT_FOR_ORB (09:30-09:35) -> SCAN_FOR_FVG (09:35-15:30) -> IN_POSITION / END_OF_DAY
```

### 2.1 Opening Range Identification

At 09:35:01 EST, aggregate first 5 M1 candles:
- `orb_high = max(high[09:30..09:34])`
- `orb_low = min(low[09:30..09:34])`
- `orb_range = orb_high - orb_low`

**Filter**: Skip session if `orb_range < 0.1% of price` (too tight, fake breakout risk).

### 2.2 Fair Value Gap Detection

On every new M1 bar, check the last 3 candles (C1, C2, C3):

**FVG Bullish**: `C3.low > C1.high` AND `C2.close > orb_high`
**FVG Bearish**: `C3.high < C1.low` AND `C2.close < orb_low`

The gap between C1 and C3 defines the imbalance zone.

### 2.3 Entry

Execute at the open of the next candle after C3 (i.e., C4.open).

### 2.4 Risk Management

- **Stop Loss**: Low of C2 (long) or High of C2 (short) — the candle that broke the ORB range
- **Take Profit**: R:R = 2:1 from entry relative to SL distance
  - Long: `TP = entry + 2 * (entry - SL)`
  - Short: `TP = entry - 2 * (SL - entry)`
- **No micro-management**: Once in position, wait for SL or TP. No trailing, no moving stops.

### 2.5 Constraints

- Max 1 trade per session per asset
- No new entries after 15:30 EST (30 min before close)
- Open positions at 16:00 EST closed at last M1 close (exit_reason = "EOD")

---

## 3. Backtest Runner

### File: `backend/src/backtest/orb_fvg_runner.py`

Dedicated intraday M1 backtest runner (separate from existing `BacktestEngine`).

**Flow**:
```
For each asset:
  Load M1 parquet -> Group by trading day
  For each day:
    Extract ORB (bars 0-4) -> Scan for FVG -> Execute trade -> Record result
  Calculate aggregate metrics
```

### Output Models

```python
class ORBTrade:
    date, epic, direction, orb_high, orb_low, fvg_type,
    entry_price, stop_loss, take_profit, exit_price,
    exit_reason (TP/SL/EOD), pnl, bars_in_trade

class ORBBacktestResult:
    epic, period, total_sessions, trades_taken, sessions_skipped,
    win_rate, avg_rr_achieved, total_pnl, max_consecutive_losses,
    max_drawdown_pct, sharpe_ratio, profit_factor,
    trades: list[ORBTrade], daily_equity: list[float]
```

### EOD Handling

Positions still open at 16:00 EST are closed at last M1 close price.
This prevents overnight risk exposure.

---

## 4. Integration with MANTIS (Phase 2, conditional)

### Success Criteria for Phase 1

Proceed to Phase 2 only if backtest shows:
- Win Rate > 50%
- Profit Factor > 1.5
- Sharpe Ratio > 1.0
- Max Drawdown < 10%

### Coexistence with ScalpScore

ORB+FVG does NOT replace ScalpScore. They coexist:
- **ScalpScore**: 20 assets, M15, 24/7, confluence voting
- **ORB+FVG**: 4 US assets, M1, NYSE session only, rule-based

During NYSE session for US assets, ORB+FVG takes priority.
Outside that window, ScalpScore handles those assets normally.

### ML Filter (Phase 2b)

Binary XGBoost classifier (TRADE / NO_TRADE) trained on Phase 1 trade outcomes.

Features:
- orb_range_pct, orb_body_ratio, fvg_gap_size, c2_volume_ratio
- time_since_open, vwap_distance, pre_market_gap, atr_14

Goal: filter weak setups to improve win rate without over-reducing trade count.

---

## 5. File Structure

```
backend/
  scripts/download_m1_data.py          # Data download script
  src/strategy/orb_fvg_strategy.py     # Core strategy logic
  src/backtest/orb_fvg_runner.py       # Dedicated M1 backtest runner
  tests/strategy/test_orb_fvg.py       # Strategy unit tests
  tests/backtest/test_orb_fvg_runner.py # Runner tests
  data/historical/{EPIC}/1min/         # M1 parquet files
  data/backtest_results/               # JSON backtest outputs
```

---

## 6. Implementation Order

1. Download M1 data (script)
2. Implement ORB+FVG strategy (core logic + tests)
3. Implement backtest runner (runner + tests)
4. Run 12-month backtest on 4 assets
5. Analyze results and present report
6. If positive: integrate into MANTIS paper loop
7. If very positive: add ML filter layer
