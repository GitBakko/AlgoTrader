# AlgoTrader AI - ML & Strategy Guide

## Model Architecture

### Ensemble Stacking Approach

For each asset (Gold, BTC, S&P500) we train a 3-model ensemble:

```
Layer 1 (Base Models):
├── LSTM         → Captures sequential temporal patterns
├── TFT          → Long-range dependencies + attention on key features
└── XGBoost      → Non-linear feature interactions on tabular data

Layer 2 (Meta-Learner):
└── XGBoost      → Combines base model outputs into final prediction
```

### Why This Combination

| Model | Strength | Weakness | Role |
|-------|----------|----------|------|
| LSTM | Excellent at sequential patterns, momentum | Forgets very long-term | Short-medium patterns |
| TFT | Attention mechanism highlights key drivers | Slower training | Long-range + explainability |
| XGBoost | Fast, handles missing data, feature interactions | No temporal awareness | Tabular features, regime |

### Prediction Target

We predict **direction + magnitude** as a classification task:

```
Classes:
  STRONG_BUY  = price increase > 1.5x ATR in next N bars
  BUY         = price increase > 0.5x ATR in next N bars
  HOLD        = price change < 0.5x ATR in next N bars
  SELL        = price decrease > 0.5x ATR in next N bars
  STRONG_SELL = price decrease > 1.5x ATR in next N bars

Prediction Horizons:
  Short:  next 4 hours (for intraday)
  Medium: next 1-3 days (for swing)
  Long:   next 1-2 weeks (for position)
```

Using ATR-relative targets instead of fixed percentages makes the model regime-adaptive.

---

## Feature Engineering Details

### Technical Features (all assets)

```python
# Trend Indicators
ema_8, ema_21, ema_50, ema_200          # Exponential Moving Averages
ema_cross_8_21                           # EMA crossover signal
ema_cross_50_200                         # Golden/Death cross
macd, macd_signal, macd_histogram        # MACD
adx                                      # Average Directional Index

# Mean Reversion
rsi_14                                   # Relative Strength Index
rsi_divergence                           # Price vs RSI divergence
bb_upper, bb_lower, bb_width, bb_pctb    # Bollinger Bands

# Volatility
atr_14                                   # Average True Range
atr_ratio = atr_14 / close              # Normalized volatility
historical_volatility_20                 # 20-day realized volatility

# Volume
obv                                      # On-Balance Volume
volume_sma_ratio = volume / sma(volume, 20) # Volume relative to average
vwap                                     # Volume-Weighted Average Price

# Price Action
returns_1, returns_5, returns_20         # Log returns at different lags
high_low_range = (high - low) / close    # Intraday range
close_position = (close - low) / (high - low) # Where close is in range
```

### Asset-Specific Features

**Gold (XAUUSD):**
```python
# Macro (from FRED API)
fed_funds_rate                           # Federal Funds Rate
us_10y_yield                             # 10-Year Treasury Yield
real_yield = us_10y_yield - cpi_yoy      # Real interest rate
dxy_index                                # US Dollar Index
cpi_yoy_change                           # CPI Year-over-Year change rate
gold_silver_ratio                        # Gold/Silver ratio

# Derived
gold_usd_correlation_20d                 # Rolling correlation with DXY
gold_sp500_correlation_20d               # Rolling correlation with S&P500
```

**Bitcoin (BTCUSD):**
```python
# Cross-asset (top predictors per research)
gold_price_normalized                    # Gold price (top predictor for BTC)
sp500_returns                            # S&P 500 returns
nasdaq_returns                           # NASDAQ returns

# Blockchain metrics (optional, from on-chain APIs)
hash_rate_change                         # Mining hash rate change
active_addresses                         # Active wallet addresses
exchange_net_flow                        # Net flow to/from exchanges

# Crypto-specific
btc_dominance                            # BTC market cap dominance
funding_rate                             # Perpetual futures funding rate
```

**S&P 500 (US500):**
```python
# Market breadth
vix                                      # CBOE Volatility Index
vix_change                               # VIX rate of change
put_call_ratio                           # Options put/call ratio

# Macro
gdp_growth_rate                          # GDP growth rate
unemployment_rate                        # Unemployment rate
pmi_manufacturing                        # PMI Manufacturing

# Sentiment
news_sentiment_score                     # FinBERT aggregate sentiment
earnings_surprise_aggregate              # Aggregate earnings surprises
```

### Feature Normalization

```python
# For each feature:
# 1. Z-score normalization using rolling window (not global)
# 2. Window = 252 bars (1 year for daily, adjust for intraday)
# 3. This prevents look-ahead bias from global normalization

normalized_feature = (feature - rolling_mean(252)) / rolling_std(252)

# For volume and other non-stationary features:
# Use log transformation first, then z-score
log_volume = np.log1p(volume)
normalized_log_volume = z_score(log_volume, window=252)
```

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

### From ML Predictions to Trading Signals

```python
def generate_signal(asset: str, predictions: dict) -> Signal:
    """
    Combine ML predictions with technical confirmations.

    predictions = {
        "direction": "BUY",          # from ensemble
        "confidence": 0.78,          # meta-learner confidence
        "horizon": "medium",         # 1-3 days
        "lstm_vote": "BUY",
        "tft_vote": "BUY",
        "xgb_vote": "HOLD",
    }
    """

    # Step 1: Minimum confidence threshold
    if predictions["confidence"] < CONFIDENCE_THRESHOLD:  # 0.65
        return Signal.HOLD

    # Step 2: Model agreement (at least 2 of 3 must agree)
    votes = [predictions["lstm_vote"], predictions["tft_vote"], predictions["xgb_vote"]]
    if votes.count(predictions["direction"]) < 2:
        return Signal.HOLD

    # Step 3: Technical confirmation
    # RSI must not be extreme against the signal
    if predictions["direction"] == "BUY" and rsi > 80:
        return Signal.HOLD  # Overbought, don't buy
    if predictions["direction"] == "SELL" and rsi < 20:
        return Signal.HOLD  # Oversold, don't sell

    # Step 4: Regime filter
    # Don't trade counter-trend in strong trends
    if regime == "STRONG_BULL" and predictions["direction"] == "SELL":
        confidence *= 0.5  # Reduce confidence for counter-trend

    # Step 5: Generate signal with risk parameters
    return Signal(
        direction=predictions["direction"],
        confidence=predictions["confidence"],
        entry_price=current_price,
        stop_loss=calculate_atr_stop(direction, atr, multiplier=2.0),
        take_profit=calculate_atr_target(direction, atr, multiplier=3.0),
        position_size=risk_manager.calculate_size(stop_distance, confidence),
    )
```

### Confidence Calibration

Model confidence must be calibrated (not just raw softmax):

```python
# Use Platt scaling or isotonic regression on validation set
# to ensure 70% confidence = 70% historical accuracy

from sklearn.calibration import CalibratedClassifierCV
calibrated_model = CalibratedClassifierCV(base_model, method='isotonic')
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
- Not a major concern for our 3 assets (Gold, BTC, S&P500 are all active)
- However, if we add individual stocks later, ensure delisted stocks are included
