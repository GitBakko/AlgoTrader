# MANTIS AI - ML & Strategy Guide

## Model Architecture

### XGBoost 3-Class Classifier

For each of the 21 supported assets, we train an XGBoost classifier with 220 features:

```
Raw OHLCV Data (multi-timeframe: 1h, 4h, 1d)
    │
    ▼
Feature Engineering (220 features)
    ├── Technical indicators (EMA, MACD, RSI, BB, ATR, ADX, OBV, Stochastic RSI)
    ├── Candlestick patterns (8: hammer, engulfing, doji, stars, pin_bar, etc.)
    ├── Fibonacci clusters (7: distances + nearest + cluster_strength)
    ├── Market structure (3: BOS/CHoCH, swing HH/HL/LH/LL)
    ├── Keltner channels + Bollinger squeeze detection
    ├── VWAP bands (distance from VWAP, ±1/2 SD bands)
    └── Session features (cyclical hour_sin/cos, dow_sin/cos)
    │
    ▼
Optuna Hyperparameter Tuning (40 trials/asset, TPE sampler)
    │
    ▼
Walk-Forward Training (purged CV, embargo)
    │
    ▼
Isotonic Confidence Calibration (per fold)
    │
    ▼
XGBoost Classifier → 3-class prediction (BUY/HOLD/SELL + calibrated confidence)
```

### Performance

| Metric | Value |
|--------|-------|
| F1 Macro | 0.53-0.61 (varies by asset) |
| Features | 220 per asset |
| Tuning | Optuna TPE, 40 trials |
| Calibration | Isotonic regression |
| Training | Walk-forward with purge + embargo |

### Prediction Target

We predict **direction** as a 3-class classification task:

```
Classes:
  SELL = 0  — price decrease > 0.5x ATR in next N bars
  HOLD = 1  — price change < 0.5x ATR in next N bars
  BUY  = 2  — price increase > 0.5x ATR in next N bars

Primary Timeframe: 1h (with 4h and 1d as additional features)
```

Using ATR-relative targets instead of fixed percentages makes the model regime-adaptive.

### LSTM (Tested, Not in Production)

LSTM was implemented and tested but achieved F1 ~0.17 (near random). XGBoost consistently outperforms on our feature set. LSTM and TFT (Temporal Fusion Transformer) remain as future enhancement candidates if more sequential data becomes available.

---

## Feature Engineering Details (220 Features)

All features are computed using pure Polars/numpy (no ta-lib dependency).

### Core Technical Features (all assets)

```python
# Trend Indicators
ema_8, ema_21, ema_50, ema_200          # Exponential Moving Averages
ema_cross_8_21                           # EMA crossover signal
ema_cross_50_200                         # Golden/Death cross
macd, macd_signal, macd_histogram        # MACD
adx                                      # Average Directional Index

# Mean Reversion
rsi_14                                   # Relative Strength Index
rsi_divergence                           # Price vs RSI divergence (bullish=+1, bearish=-1)
stochastic_rsi_k, stochastic_rsi_d       # Stochastic RSI
bb_upper, bb_lower, bb_width, bb_pctb    # Bollinger Bands

# Volatility
atr_14                                   # Average True Range
atr_ratio = atr_14 / close              # Normalized volatility
historical_volatility_20                 # 20-day realized volatility

# Volume
obv                                      # On-Balance Volume
volume_sma_ratio                         # Volume relative to 20-bar average
vwap, vwap_distance                      # VWAP + distance from VWAP

# Price Action
returns_1, returns_5, returns_20         # Log returns at different lags
high_low_range = (high - low) / close    # Intraday range
close_position = (close - low) / (high - low)
```

### Advanced Features (Phase 8+)

```python
# Candlestick Patterns (8 binary features)
hammer, inverted_hammer, engulfing_bullish, engulfing_bearish
doji, morning_star, evening_star, pin_bar

# Fibonacci Clusters (7 features)
fib_distance_236, fib_distance_382, fib_distance_500
fib_distance_618, fib_distance_786
fib_nearest, fib_cluster_strength        # ATR-normalized

# Market Structure (3 features)
market_structure_bos                     # Break of Structure
market_structure_choch                   # Change of Character
swing_type                              # HH/HL/LH/LL classification

# Keltner Channels + Bollinger Squeeze
keltner_upper, keltner_lower
bb_inside_kc (squeeze detection)         # Binary + duration
squeeze_momentum                         # Momentum + volume breakout

# VWAP Bands
vwap_upper_1sd, vwap_lower_1sd
vwap_upper_2sd, vwap_lower_2sd

# Session Features (cyclical encoding)
hour_sin, hour_cos                       # Intraday cycle
dow_sin, dow_cos                         # Day-of-week cycle
```

### Multi-Timeframe Features

Features from 4h and 1d timeframes are merged via asof join (forward-fill):
- All technical indicators computed on each timeframe
- Suffix naming: `_4h`, `_1d` for additional timeframes
- Total: ~70 features per timeframe x 3 timeframes ≈ 220 features

### Feature Normalization

```python
# Combined clip + rolling z-score (optimized single pass):
# 1. Clip outliers beyond ±5 std
# 2. Rolling z-score with window=252 (prevents look-ahead bias)

normalized = clip_and_zscore(feature, window=252, clip_std=5.0)

# For volume: log transform first, then z-score
log_volume = np.log1p(volume)
normalized_log_volume = clip_and_zscore(log_volume, window=252)
```

### Future Enhancement: Asset-Specific Features

These features are planned but not yet implemented:
- **Macro**: FRED API (CPI, Fed Funds, DXY, VIX) — requires data pipeline
- **Sentiment**: FinBERT news scoring — requires NLP pipeline
- **Blockchain**: On-chain metrics for crypto — requires data source

---

## Training Pipeline

### Walk-Forward Optimization

```
Timeline: ──────────────────────────────────────────────>

Step 1: [====TRAIN (252d)====][==VAL (63d)==][TEST (21d)]
Step 2:     [====TRAIN (252d)====][==VAL (63d)==][TEST (21d)]
Step 3:         [====TRAIN (252d)====][==VAL (63d)==][TEST (21d)]
...

Parameters:
  train_window  = 252 trading days (1 year)
  val_window    = 63 trading days (3 months)
  test_window   = 21 trading days (1 month)
  step_size     = 21 trading days (1 month)

For intraday (4h bars):
  train_window  = 1512 bars (~252 days x 6 bars/day)
  val_window    = 378 bars
  test_window   = 126 bars
  step_size     = 126 bars
```

### Purged Cross-Validation

To prevent data leakage between train and validation:

```python
# Purge gap = max prediction horizon (e.g., 5 days)
# Embargo = additional gap after validation set

[TRAIN...][PURGE_GAP][VALIDATION][EMBARGO][NEXT_TRAIN...]

purge_gap = prediction_horizon  # e.g., 5 days for medium-term
embargo = 2  # additional safety margin in days
```

### Hyperparameter Optimization

Use **Optuna** with the walk-forward framework:

```python
# For each walk-forward step:
#   1. Train with candidate hyperparameters on train set
#   2. Evaluate on validation set
#   3. Optuna selects next candidates via TPE sampler
#   4. Best params used for test set evaluation

# Key hyperparameters per model:
LSTM:
  hidden_size: [64, 128, 256]
  num_layers: [1, 2, 3]
  dropout: [0.1, 0.3, 0.5]
  learning_rate: [1e-4, 1e-3]
  sequence_length: [30, 60, 120]

TFT:
  hidden_size: [32, 64, 128]
  attention_heads: [1, 4]
  dropout: [0.1, 0.3]
  learning_rate: [1e-4, 1e-3]

XGBoost:
  max_depth: [3, 6, 9]
  learning_rate: [0.01, 0.1, 0.3]
  n_estimators: [100, 500, 1000]
  subsample: [0.7, 0.9]
  colsample_bytree: [0.7, 0.9]
```

---

## Signal Generation Logic

### Strategy Router (Regime-Based)

The `StrategyRouter` selects the appropriate strategy based on market regime:

```
Market Regime Detection (ADX + EMA slope)
    │
    ├── Trending (ADX > 25) → ML Strategy (XGBoost prediction)
    │
    └── Ranging (ADX < 20)  → Best of:
                               ├── Volatility Squeeze Strategy (BB inside KC)
                               ├── VWAP Reversion Strategy (±2SD entry)
                               └── ML Strategy (fallback)
```

### From XGBoost Prediction to Trading Signal

```python
# XGBoost outputs calibrated probabilities for 3 classes:
# P(SELL), P(HOLD), P(BUY)

# Step 1: Minimum confidence threshold (0.40 for 3-class)
if max_probability < 0.40:
    return Signal.HOLD

# Step 2: ADX pre-signal filter
if adx < 20:
    reject  # choppy market
if adx > 25:
    confidence += 0.05  # boost for trending

# Step 3: RSI extreme filter
if direction == BUY and rsi > 80: return HOLD
if direction == SELL and rsi < 20: return HOLD

# Step 4: Regime filter (counter-trend penalty)
if regime == STRONG_BULL and direction == SELL:
    confidence *= 0.5

# Step 5: Generate signal with risk parameters
signal = Signal(direction, confidence, entry, SL, TP1, TP2)
```

### Additional Strategies

**Volatility Squeeze** (`squeeze_strategy.py`):
- Detects Bollinger Bands inside Keltner Channels
- Entry on momentum + volume breakout
- Works best in ranging markets transitioning to trending

**VWAP Reversion** (`vwap_strategy.py`):
- Entry at ±2 standard deviations from VWAP
- Take profit at VWAP center
- Stop loss at ±3 standard deviations
- ADX and RSI filters

**Pairs Trading Gold-BTC** (`pairs/pairs_strategy.py`):
- Engle-Granger cointegration test (ADF)
- Z-score entry (±2) / exit (±0.5)
- Dollar-neutral position sizing

### Confidence Calibration

Isotonic regression calibration is applied per walk-forward fold:

```python
# Calibration ensures: 70% predicted confidence ≈ 70% actual accuracy
# Fitted on validation set of each fold, saved with model

from src.models.calibration import ConfidenceCalibrator
calibrator = ConfidenceCalibrator(method='isotonic')
calibrator.fit(val_probabilities, val_labels)
calibrated_probs = calibrator.transform(test_probabilities)
# ECE (Expected Calibration Error) tracked as quality metric
```

---

## Risk Management Details

### Position Sizing Formula

```python
def calculate_position_size(
    account_equity: float,
    risk_per_trade: float,    # 0.01 = 1%
    entry_price: float,
    stop_loss_price: float,
    confidence: float,        # 0.0 - 1.0
) -> float:
    """
    Volatility-adjusted position sizing with confidence scaling.
    """
    # Base risk amount
    risk_amount = account_equity * risk_per_trade

    # Stop distance in price
    stop_distance = abs(entry_price - stop_loss_price)

    # Base position size
    base_size = risk_amount / stop_distance

    # Scale by confidence (higher confidence = larger size, but capped)
    # Mapping: confidence 0.65 -> 0.5x, 0.80 -> 1.0x, 0.95 -> 1.5x
    confidence_multiplier = max(0.5, min(1.5, (confidence - 0.5) * 3.33))

    # Apply confidence scaling
    final_size = base_size * confidence_multiplier

    # Apply maximum size cap (never more than 5% of equity in one trade)
    max_size = (account_equity * 0.05) / entry_price
    final_size = min(final_size, max_size)

    return final_size
```

### ATR-Based Stop Loss

```python
def calculate_atr_stop(
    direction: str,
    entry_price: float,
    atr_value: float,
    multiplier: float = 2.0,
) -> float:
    """
    ATR-based dynamic stop loss.

    Multipliers by trading style:
      Intraday:  1.5 - 2.0
      Swing:     2.0 - 2.5
      Position:  2.5 - 3.5
    """
    stop_distance = atr_value * multiplier

    if direction == "BUY":
        return entry_price - stop_distance
    else:
        return entry_price + stop_distance
```

### Portfolio Allocation

```python
# Base allocation (adjusted dynamically by regime and correlation)
BASE_ALLOCATION = {
    "GOLD":   0.35,  # 35% - Stability anchor
    "BTC":    0.30,  # 30% - Growth/alpha generator
    "SP500":  0.35,  # 35% - Market beta
}

# Regime adjustments:
# Bull market:  reduce Gold to 25%, increase BTC to 35%, SP500 to 40%
# Bear market:  increase Gold to 45%, reduce BTC to 20%, SP500 to 35%
# High vol:     increase Gold to 50%, reduce BTC to 15%, SP500 to 35%
# Crypto bull:  Gold 30%, increase BTC to 40%, SP500 to 30%
```

---

## Model Monitoring & Retraining

### Drift Detection

Monitor these metrics continuously:

```python
# 1. Prediction accuracy rolling window
rolling_accuracy = calculate_accuracy(last_N_predictions)
if rolling_accuracy < baseline_accuracy * 0.8:
    trigger_alert("Model accuracy degraded")

# 2. Feature distribution shift (Kolmogorov-Smirnov test)
for feature in features:
    ks_stat, p_value = ks_2samp(training_distribution, recent_distribution)
    if p_value < 0.01:
        trigger_alert(f"Feature distribution shift: {feature}")

# 3. Prediction confidence decay
avg_confidence = mean(recent_confidences)
if avg_confidence < 0.5:
    trigger_alert("Model confidence declining")
```

### Retraining Schedule

```
Automatic retraining triggers:
  1. Scheduled: Every 30 days (new walk-forward step)
  2. Accuracy-based: When rolling accuracy drops below threshold
  3. Drift-based: When significant feature distribution shift detected
  4. Manual: Triggered via dashboard

Retraining process:
  1. Collect latest data
  2. Rebuild features
  3. Train new models with walk-forward
  4. Compare new vs current model on recent data
  5. If new model is better -> deploy (with shadow testing first)
  6. If new model is worse -> keep current, alert team
```

---

## Avoiding Common Pitfalls

### Overfitting Prevention Checklist
- [ ] Walk-forward optimization (never train on future data)
- [ ] Purged cross-validation (gap between train/val/test)
- [ ] Limited features per model (avoid curse of dimensionality)
- [ ] Regularization in all models (dropout, L1/L2, early stopping)
- [ ] Out-of-sample validation always reserved
- [ ] Compare against simple baselines (buy & hold, random)
- [ ] Realistic transaction costs in backtests
- [ ] Slippage simulation based on asset liquidity

### Look-Ahead Bias Prevention
- [ ] All features calculated using only past data
- [ ] Point-in-time data for macro features (use release dates, not revision dates)
- [ ] No future information in feature normalization (use rolling windows)
- [ ] Backtesting engine enforces strict temporal ordering
- [ ] Data splits are always chronological, never random

### Survivorship Bias
- Not a major concern for major assets (Gold, BTC, S&P500, etc.)
- Stock CFDs (NVDA, TSLA) could be affected — monitor for delistings
- Crypto assets (SOL, ETH, BNB, DOGE, DASH, ICP) have higher risk of structural changes
