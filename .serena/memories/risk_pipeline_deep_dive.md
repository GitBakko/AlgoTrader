# Risk Management & Trade Execution Pipeline — Deep Dive (2026-02-25)

## Overview
This is a comprehensive analysis of how trades flow through the risk and execution pipeline. The system is well-architected but has CRITICAL PERFORMANCE BOTTLENECKS causing the 27% win rate.

---

## 1. RISK MANAGER ORCHESTRATION (`risk_manager.py` lines 21-273)

### Pipeline Order (Critical!)
1. **Circuit Breaker Checks** (line 90)
2. **Max Positions / Exposure Caps** (lines 107-135)
3. **Drawdown Limits** (lines 146-155)
4. **Stop-Loss Calculation** (lines 157-185)
5. **Take-Profit Calculation** (lines 187-198)
6. **Correlation Checks** (lines 200-206)
7. **Position Sizing** (lines 208-233)
8. **Equity Curve Filter** (lines 235-241)
9. **Multi-Target TP1/TP2** (lines 249-256)

### Key Parameters & Thresholds

| Component | Parameter | Default Value | Impact |
|-----------|-----------|---------------|--------|
| **Stop-Loss** | Base Multiplier | **3.0 ATR** | CRITICAL |
| | Dynamic Range | [2.0, 5.0] ATR | Scales with vol |
| | Formula | `base * (0.5 + 0.5 * ratio)` | Vol-adjusted |
| **Take-Profit** | Risk:Reward Ratio | **1.5x** | Line 193 |
| | TP1 Distance | **1.0x risk** | Line 252 |
| | TP2 Distance | **2.0x risk** | Line 253 |
| **Position Sizing** | Max Risk/Trade | **2%** | Line 224 |
| | Max Position % | **5%** of equity | Default |
| | Confidence Mult | 0.5 to 1.5x | Line 168 |
| **Correlation** | Guard Mult | < 1.0 if corr | Line 232 |
| **Equity Curve** | SMA Window | **20 trades** | Line 16 (equity_curve_filter.py) |
| | Reduction Factor | **50%** if below SMA | Line 17 |

### Decision Chain (Line 59-273)

```
Signal arrives:
  ↓
1. Validate ATR > 0 (line 77)
  ↓
2. Circuit breakers.check_all() (line 90)
   ├─ Daily loss > -3% → REJECT
   ├─ Consecutive losses ≥ 8 → REJECT
   ├─ Open positions ≥ 20 → REJECT
   ├─ ATR spike > 5.0x baseline → REJECT
   ├─ Heartbeat timeout > 30s → REJECT
   └─ Slippage avg > 0.5% (5-trade window) → REJECT
  ↓
3. Max positions check (line 109)
   └─ If open >= max_total → REJECT
  ↓
4. Total exposure cap check (line 120)
   └─ If notional/equity >= limit → REJECT
  ↓
5. Drawdown check (line 148)
   └─ If peak_dd > 12% OR daily_dd > 5% → REJECT (or activate CB)
  ↓
6. Calculate SL with dynamic multiplier (lines 160-174)
   └─ SL = entry ± (atr * dynamic_mult)
   └─ dynamic_mult = 3.0 * (0.5 + 0.5 * atr_ratio), clamped [2.0, 5.0]
  ↓
7. Use signal's suggested_stop if tighter (line 180)
  ↓
8. Calculate TP with 1.5x RR (lines 188-194)
   └─ TP = entry ± (atr * multiplier * 1.5)
  ↓
9. Correlation guard (line 201)
   └─ Check if corr > threshold → reduce size
  ↓
10. Size position with Kelly or fixed-fractional (lines 210-229)
    ├─ If Kelly available & trade_hist > 30 → Kelly sizing
    │  └─ Negative Kelly → 50% fixed-fractional fallback
    └─ Else → fixed-fractional (risk_per_trade=2%, conf_mult=0.5-1.5x)
  ↓
11. Apply correlation multiplier (line 232)
  ↓
12. Apply equity curve filter (line 236)
    └─ If equity < SMA(20) → size *= 0.50
  ↓
13. Calculate TP1/TP2 (lines 249-256)
    └─ TP1 = entry ± 1.0x risk
    └─ TP2 = entry ± 2.0x risk
  ↓
APPROVED ✓
```

---

## 2. CIRCUIT BREAKERS (`circuit_breakers.py` lines 26-301)

### 6 Independent Breakers

| Breaker Type | Default Threshold | Auto-Reset | Thread-Safe |
|--------------|------------------|-----------|------------|
| **DAILY_LOSS** | -3% daily | Manual reset | Yes (Lock) |
| **CONSECUTIVE_LOSSES** | ≥ 8 losses | Auto on win | Yes |
| **MAX_POSITIONS** | ≥ 20 open | Auto reset | Yes |
| **VOLATILITY_SPIKE** | ATR ≥ 5.0x baseline | 60min cooldown | Yes |
| **HEARTBEAT_TIMEOUT** | > 30s since last call | Auto on heartbeat() | Yes |
| **SLIPPAGE_ANOMALY** | avg > 0.5% (5-trade window) | Manual/60min | Yes |

### Key Methods

| Method | Purpose | Impact |
|--------|---------|--------|
| `check_all()` | Runs all 6 checks per trade | Rejects if ANY triggered |
| `record_trade_result(is_win)` | Updates consecutive losses | CRITICAL for feedback loop |
| `update_baseline_atr(epic, atr)` | Tracks baseline volatility | Used for vol spike detection |
| `heartbeat()` | Called at loop start per-epic | Resets heartbeat timeout |
| `auto_reset_after_minutes` | Cooldown period | Default 60min |

### CRITICAL STATE MANAGEMENT

**State Variables** (lines 54-60):
- `_tripped`: dict[CircuitBreakerType, str] — Type → reason
- `_tripped_at`: dict[CircuitBreakerType, float] — Timestamp  
- `_consecutive_losses`: int — Counter
- `_slippage_history`: list[float] — Last 15 trades
- `_baseline_atr`: dict[str, float] — Per-epic

**Thread Safety**: Using `threading.Lock()` — NOT `asyncio.Lock` — for compatibility with sync+async code.

---

## 3. STOP MANAGER (`stop_manager.py` lines 6-110)

### Static Methods

#### `dynamic_multiplier()` (lines 10-35)
```python
Formula: scaled = base * (0.5 + 0.5 * ratio)
Clamped: [min_multiplier=2.0, max_multiplier=5.0]

Examples (base=3.0):
  ratio=1.0 (normal vol) → 3.0x
  ratio=2.0 (high vol) → 4.5x (wider SL to avoid whips)
  ratio=0.5 (low vol) → 2.25x (tighter SL for better RR)
```

**Key Guard** (line 30): Returns base unchanged if baseline is invalid — no exception.

#### `calculate_stop_loss()` (lines 38-59)
For BUY: SL = entry - (atr * multiplier)
For SELL: SL = entry + (atr * multiplier)

#### `calculate_take_profit()` (lines 62-85)
tp_distance = atr * multiplier * risk_reward (default RR=1.5)
For BUY: TP = entry + tp_distance
For SELL: TP = entry - tp_distance

#### `calculate_trailing_stop()` (lines 88-109)
trail_distance = atr * multiplier
For BUY: TS = current - trail_distance
For SELL: TS = current + trail_distance

---

## 4. KELLY SIZER (`kelly_sizer.py` lines 24-203)

### Configuration
| Param | Default | Purpose |
|-------|---------|---------|
| `min_trades` | **30** | Minimum trades before Kelly activates |
| `lookback_trades` | **100** | Recent trades window |
| `max_kelly` | **0.25** (25%) | Safety cap |
| `use_half_kelly` | **True** | Use kelly/2 for safety |

### Calculation Pipeline (lines 112-185)

Calculate size logic:
1. Validate inputs (equity > 0, entry > 0, stop_distance > 0)
2. If history < 30 trades → return fixed_fractional
3. Else compute: WR, avg_win, avg_loss, kelly = WR - (1-WR)/payoff_ratio
4. **CRITICAL**: If kelly ≤ 0 → 50% fixed_fractional fallback (NOT zero/block) — prevents deadlock
5. Apply confidence multiplier (line 168): conf_mult = (confidence - 0.5) * 3.33, range [0.5, 1.5]
6. risk_amount = equity * kelly_frac * conf_mult
7. size = risk_amount / stop_distance, capped at max_position_pct

---

## 5. PAPER TRADING LOOP (`paper_loop.py` — The Full Pipeline)

### Main Entry Point: `_process_epic()` (lines 860-1160)

```
_process_epic(epic, open_positions):
  ↓
STEP 0: Market hours check (line 863)
  └─ DEMO/LIVE only: If closed → log, return
  ↓
STEP 1: ML Prediction (line 880)
  └─ If None → return
  ↓
STEP 2: Market data (line 891)
  └─ Keys: regime, adx, rsi, atr
  └─ Track regime distribution
  ↓
STEP 3: Strategy processing (line 910)
  └─ signal = strategy_manager.process_prediction()
  └─ Track signal history
  ↓
STEP 3.5: HOLD check (line 942)
  └─ If direction == "HOLD" → return
  ↓
STEP 3.6: Duplicate signal detection (lines 957-981)
  └─ signal_key = (epic, direction, round(entry_price, 2))
  └─ If seen in last 60s → skip
  ↓
STEP 4: RISK CHECK (line 986) ⚠️ **CRITICAL BOTTLENECK**
  └─ risk_result = risk_manager.check_trade(signal, equity, atr, open_positions, trade_history)
  └─ If NOT approved → log rejection, return
  └─ If approved → continue
  ↓
STEP 4b: Min deal size check (line 1028)
  └─ If size < broker minimum → reject, return
  ↓
STEP 4c: Equity re-check (line 1060)
  └─ If changed > 1% → update risk_manager
  ↓
STEP 5: EXECUTION (line 1071)
  └─ exec_result = execution_engine.execute_signal()
  └─ If success: register trailing stop, persist, log
  └─ If failed: log error
```

### Trailing Stop Manager (lines 1161-1199)

4 phases:
- INITIAL: SL at initial level
- BREAKEVEN: SL = entry (when price ≥ TP1)
- TP1_LOCK: SL = TP1 (when price ≥ TP2)
- TRAILING: SL = current - (atr * 1.5) (beyond TP2)

---

## 6. EQUITY CURVE FILTER (`equity_curve_filter.py` lines 21-103)

### Configuration
| Param | Default | Purpose |
|-------|---------|---------|
| `sma_window` | **20** trades | Rolling window |
| `reduction_factor` | **0.50** (50%) | Size reduction |
| `min_trades_to_activate` | **10** | Activation threshold |

### Mechanism (lines 46-69)
- If trade_count < 10 → return 1.0
- sma = SMA(last 20 equity snapshots)
- If current < sma → return 0.50 (reduce size by 50%)
- Else → return 1.0

Applied AFTER Kelly sizing in risk_manager (line 236).

---

## CRITICAL ISSUES CAUSING 27% WIN RATE

### 1. **STOP-LOSS TOO WIDE** ❌ **PRIMARY CULPRIT**
- Current: 3.0 ATR base (scales 2.0-5.0 with vol)
- Problem: In trending markets, 3 ATR SL is MASSIVE
- Example: XAUUSD 1h ATR=15 → SL=45 pips, TP1=15 pips. SL/TP ratio = 3:1 (reversed!)
- Fix: Reduce to 1.5-2.0 ATR base

### 2. **TAKE-PROFIT TOO TIGHT** ❌ **SECONDARY CULPRIT**
- Current: 1.5x RR ratio on TP (line 193), TP1=1.0x risk, TP2=2.0x risk
- Problem: TP = 4.5 ATR, SL = 3 ATR → 1.5x RR (formula matches)
- But in ranges: price oscillates 2-3 ATR → TP never hit
- Fix: Increase TP RR to 2.5-3.0x, adjust TP1/TP2 for regime

### 3. **CONFIDENCE NOT FILTERED** ⚠️ **MISSED SIGNAL**
- Current: Trades all signals, only size reduction based on confidence
- Problem: conf_mult = (confidence - 0.5) * 3.33, range [0.5, 1.5]
  - conf=0.55 → 1.05x (nearly full size, barely above 50%)
- Fix: Add MIN_CONFIDENCE threshold (e.g., 0.60), skip signals below

### 4. **KELLY MIN_TRADES=30** ⚠️ **SLOW ADAPTATION**
- Current: min_trades=30 before Kelly activates
- Problem: First 30 trades use fixed-fractional → likely show low WR
- Then Kelly computes from losing trades → negative Kelly → 50% fallback
- Deadlock: Can't recover stats because sizing still suppressed
- Fix: Reduce min_trades to 10-15

### 5. **EQUITY CURVE 50% REDUCTION** ⚠️ **COMPOUNDS LOSSES**
- Current: 50% size reduction when below SMA(20)
- Problem: In losing streak, sizes SHRINK → takes longer to recover
- Better approach: Use % drawdown from peak, not SMA-based
- Fix: Replace with drawdown-based filter (already have drawdown_monitor)

### 6. **CIRCUIT BREAKER CONSECUTIVE LOSSES = 8** ⚠️ **TRIGGERS TOO OFTEN**
- Current: Max 8 consecutive losses (line 30, circuit_breakers.py)
- Problem: With 27% WR, average sequence ~1.7 wins per loss
- 8 consecutive is very likely → CB triggers frequently
- Fix: Increase to 12-15, but ONLY after fixing SL/TP (root cause)

### 7. **ATR MULTIPLIER CLAMPED AT 5.0x** ⚠️ **EXTREME VOL NOT HANDLED**
- Current: max_multiplier=5.0 (line 15, stop_manager.py)
- Problem: In extreme spikes, ATR 10x → SL still 5x wide
- Should skip trading in extreme vol, not just widen stops
- Volatility spike breaker exists but triggers at 5.0x ratio
- Fix: Lower threshold to 3.0x or 2.0x

### 8. **MINIMUM POSITION SIZE CHECK IS TOO LATE** ⚠️ **EXECUTION WASTE**
- Current: Min deal size check AFTER risk_manager.check_trade() (line 1028)
- Problem: Full risk pipeline runs, then min size check fails
- Should check min size inside RiskManager, before Kelly/sizing

### 9. **DYNAMIC MULTIPLIER ASYMMETRIC** ⚠️ **MINOR**
- Current: `scaled = base * (0.5 + 0.5 * ratio)`
- At ratio=0.5: scaled = 2.25x (mild tightening)
- At ratio=2.0: scaled = 4.5x (mild widening)
- Better: Use 1/(sqrt(ratio)) for symmetric response
- Impact: Low priority

### 10. **SLIPPAGE NOT SIMULATED** ⚠️ **HIDDEN LOSSES**
- Current: Entry at signal.entry_price (StrategyManager's target)
- Problem: Actual execution may be +0.5-1% worse (broker slippage)
- If actual entry worse, SL distance increases → higher loss risk
- Fix: Add slippage simulation (+0.5% for DEMO), recalc SL/TP from actual fill

---

## SUMMARY TABLE: ROOT CAUSES

| Root Cause | Severity | Impact | Fix Priority | File/Line |
|-----------|----------|--------|--------------|-----------|
| **SL too wide (3 ATR)** | **CRITICAL** | SL hit before TP | **P0** | risk_manager.py:161 |
| **TP too tight (1.5x RR)** | **CRITICAL** | Ranges = no TP hit | **P0** | risk_manager.py:193 |
| **Confidence not filtered** | **HIGH** | Low-conf trades at full size | **P1** | paper_loop.py:942 |
| **Kelly min_trades=30** | **HIGH** | Slow adaptation | **P1** | kelly_sizer.py:37 |
| **Equity curve 50% reduction** | **HIGH** | Compounds loss recovery | **P1** | equity_curve_filter.py:17 |
| **Dynamic multiplier clamped 5x** | **MEDIUM** | Extreme vol not handled | **P2** | stop_manager.py:15 |
| **Asymmetric scaling** | **LOW** | Minor efficiency loss | **P3** | stop_manager.py:34 |
| **Min size check too late** | **LOW** | CPU waste | **P3** | paper_loop.py:1028 |

---

## P0 FIXES (IMMEDIATE)

### 1. Reduce SL: 3.0 → 1.5-2.0 ATR
**File**: `risk_manager.py` line 161
Change: base_multiplier=3.0 → 2.0

### 2. Widen TP: 1.5x → 2.5x RR
**File**: `risk_manager.py` line 193
Change: risk_reward=1.5 → 2.5

### 3. Add Confidence Filter
**File**: `paper_loop.py` after line 942
Add: Skip signals with confidence < 0.60

---

## TESTING PLAN

After P0 fixes, backtest:
1. **SL multiplier sweep**: 1.0 - 3.0 ATR in 0.5 increments
2. **TP RR sweep**: 1.0 - 4.0x in 0.5 increments
3. **Confidence thresholds**: 0.50, 0.55, 0.60, 0.65, 0.70
4. **Measure**: Win rate, profit factor, Sharpe, max drawdown
5. **Target**: Get WR to 35%+ before Phase 5 (Live Trading)

