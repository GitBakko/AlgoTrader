# Mean Reversion 4h Strategy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the failing "XGBoost predicts direction on 1h" approach with "mean reversion signals on 4h, XGBoost filters quality" — the single most impactful change to make MANTIS profitable.

**Architecture:** The direction comes from simple, proven rules (price deviation from VWAP/BB). XGBoost's role changes from "decide direction" to "score this mean reversion setup quality" (2-class: GOOD_SETUP / BAD_SETUP). Trading on 4h candles reduces spread impact from ~15% to ~3% of TP.

**Tech Stack:** Existing Python/FastAPI/Polars/XGBoost stack. No new dependencies.

---

## What Changes (and What Doesn't)

### Changes
| Component | Before | After |
|-----------|--------|-------|
| **Timeframe** | 1h (scalp) | 4h (swing) |
| **Direction decision** | XGBoost 3-class (BUY/SELL/HOLD) | Mean reversion rules (z-score bands) |
| **XGBoost role** | Predicts direction | Filters setup quality (2-class) |
| **Target** | Future return > ATR threshold | "Did this MR setup revert to mean within 12 bars?" |
| **Trade frequency** | ~35/day | ~3-6/day |
| **TP logic** | Fixed ATR multiple | Return to VWAP/EMA (dynamic) |
| **Win rate expected** | 37% (actual) | 55-65% (MR natural edge) |

### Stays the Same
- Feature engineering pipeline (220+ features)
- Cross-asset features
- Risk management (CB, Kelly, trailing stops, correlation guard)
- Regime gate (HMM + drift)
- Spread filter
- Frontend, API, monitoring, alerts
- Broker integration (Capital.com)

---

## Implementation Tasks

### Task 1: Config — Switch to 4h Timeframe

**Files:** `src/utils/config.py`, `.env`

Change `.env`:
```
SCALP_MODE_ENABLED=false
SCALP_CANDLE_RESOLUTION=4h
SCALP_CHECK_INTERVAL=900    # 15 min check interval (4h candles)
SCALP_SL_MULTIPLIER=2.0
SCALP_TP_RISK_REWARD=1.5    # MR has lower R:R but higher WR
```

This alone switches the entire pipeline to 4h candles. No code change needed.

---

### Task 2: Mean Reversion Signal Generator

**Files:**
- Create: `src/strategy/mean_reversion_strategy.py`
- Test: `tests/strategy/test_mean_reversion.py`

The MR strategy generates BUY/SELL signals based on price deviation from a dynamic mean:

**Entry rules (all must be true):**
- **SELL**: z-score > +2.0 (price far above VWAP/BB middle)
- **BUY**: z-score < -2.0 (price far below VWAP/BB middle)
- **Confirmation**: RSI in overbought (>70 for SELL) or oversold (<30 for BUY)
- **No strong trend**: ADX < 30 (mean reversion fails in trends)

**Exit rules:**
- **TP**: Price returns to VWAP/BB middle (z-score crosses 0)
- **SL**: z-score extends further (> 3.0 for SELL entry, < -3.0 for BUY entry)
- **Time stop**: 12 bars (48h) without reversion

**Implementation:**

```python
class MeanReversionStrategy:
    """Mean reversion signals from price deviation + confirmation."""
    
    Z_ENTRY = 2.0        # Enter when z-score exceeds this
    Z_STOP = 3.0         # Stop loss when z-score extends to this
    RSI_OB = 70           # Overbought threshold
    RSI_OS = 30           # Oversold threshold  
    ADX_MAX = 30          # Max ADX (no MR in strong trends)
    
    def generate_signal(self, market_data: dict) -> MRSignal:
        bb_pctb = market_data.get("bb_pctb", 0.5)  # 0=lower band, 1=upper band
        rsi = market_data.get("rsi", 50)
        adx = market_data.get("adx", 25)
        vwap_z = market_data.get("vwap_z_score", 0)
        
        # Use the stronger of BB and VWAP z-scores
        z_score = vwap_z if abs(vwap_z) > abs(bb_pctb - 0.5) * 4 else (bb_pctb - 0.5) * 4
        
        if adx > self.ADX_MAX:
            return MRSignal(direction="HOLD", reason="Trending market (ADX > 30)")
        
        if z_score > self.Z_ENTRY and rsi > self.RSI_OB:
            return MRSignal(direction="SELL", z_score=z_score, 
                          tp="return to mean", sl=f"z > {self.Z_STOP}")
        
        if z_score < -self.Z_ENTRY and rsi < self.RSI_OS:
            return MRSignal(direction="BUY", z_score=z_score,
                          tp="return to mean", sl=f"z < -{self.Z_STOP}")
        
        return MRSignal(direction="HOLD", reason="No extreme deviation")
```

---

### Task 3: New Target Builder for MR Quality Scoring

**Files:**
- Create: `src/models/mr_target_builder.py`  
- Test: `tests/models/test_mr_target_builder.py`

Instead of "will price go up or down?", the new target answers: **"Did this mean reversion setup actually revert within N bars?"**

**Label logic:**
```
For each bar where |z_score| > 2.0:
  Look ahead 12 bars (48h on 4h TF)
  If price returned to mean (z_score crossed 0): GOOD_SETUP = 1
  If price kept extending (z_score got worse): BAD_SETUP = 0
  
For bars where |z_score| <= 2.0: 
  Not a setup → exclude from training (NaN target)
```

This is a **binary classification** task, much easier than 3-class direction prediction.

---

### Task 4: XGBoost as Quality Filter

**Files:**
- Modify: `src/models/prediction_service.py`
- Modify: `src/strategy/strategy_manager.py`

Change the prediction flow:
```
Before: XGBoost → direction (BUY/SELL/HOLD) → risk check → execute
After:  MR rules → direction (BUY/SELL/HOLD) → XGBoost quality score → risk check → execute
```

XGBoost predicts `P(GOOD_SETUP)`. If P > 0.60 → allow trade. If P < 0.60 → reject.

The confidence threshold becomes a **quality gate**, not a direction predictor.

---

### Task 5: Integration in Strategy Manager

**Files:**
- Modify: `src/strategy/strategy_manager.py`

Add a new mode `MR_PRIMARY` alongside `ML_PRIMARY` and `SCALP_MODE`:

```python
if settings.mr_primary_enabled:
    # 1. MR strategy generates direction from z-score bands
    mr_signal = self.mr_strategy.generate_signal(market_data)
    if mr_signal.direction == "HOLD":
        return TradingSignal(direction="HOLD", ...)
    
    # 2. XGBoost scores setup quality
    quality = prediction.confidence  # Now P(GOOD_SETUP)
    if quality < settings.mr_min_quality:
        return TradingSignal(direction="HOLD", reason=f"Quality {quality:.2f} < {settings.mr_min_quality}")
    
    # 3. Return signal with MR direction + XGBoost quality as confidence
    return TradingSignal(
        direction=mr_signal.direction,
        confidence=quality,
        entry_price=market_data["current_price"],
        suggested_stop=mr_signal.stop_level,
        suggested_tp=mr_signal.tp_level,
        strategy_name="mean_reversion",
    )
```

---

### Task 6: Retrain All Models with New Targets + 4h Data

**Steps:**
1. Download 4h historical data for all 10 assets
2. Build features on 4h timeframe
3. Generate MR quality labels (GOOD_SETUP / BAD_SETUP)
4. Train XGBoost binary classifier on each asset
5. Walk-forward validate with real spread costs
6. Compare: old approach vs new approach

---

### Task 7: Validation — Does It Work?

Run walk-forward on 4h with MR targets. The gate criteria:

```
PASS if:
  - Win rate > 50% (MR natural edge)
  - Profit factor > 1.2 (after spread costs)
  - At least 5 assets profitable OOS
  
FAIL if:
  - Win rate < 45%
  - Profit factor < 1.0 after costs
  → The MR approach doesn't work on these assets with this broker
```

---

## Execution Order

1. **Task 1**: Config switch to 4h (5 min)
2. **Task 2**: MR signal generator (1-2h)
3. **Task 3**: MR target builder (1h)
4. **Task 4**: XGBoost as filter (30min)
5. **Task 5**: Strategy manager integration (1h)
6. **Task 6**: Retrain (30min + training time)
7. **Task 7**: Validation (30min + backtest time)

**Total estimated: 1 giornata di lavoro**

---

## Risk Mitigation

- **Se MR non funziona su 4h**: provare 1d (ancora meno trade, spread ancora meno impattante)
- **Se XGBoost non filtra bene i setup**: usare solo le regole MR senza ML (baseline)
- **Se nessun asset funziona**: il problema e Capital.com (spread troppo alti per qualsiasi strategia intraday) → migrare a Bybit
- **Rollback**: tutto il vecchio codice resta, basta cambiare `MR_PRIMARY_ENABLED=false` per tornare al vecchio approccio
