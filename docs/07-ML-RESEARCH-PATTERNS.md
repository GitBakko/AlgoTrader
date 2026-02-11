# ML Trading Research - Patterns & Hyperparameters

Research synthesis from key ML trading repositories and tutorials, mapped to
AlgoTrader AI's architecture. Each section identifies what the current codebase
already implements, what is missing, and specific code patterns to adopt.

**Sources studied:**
1. Stefan Jansen - *Machine Learning for Trading* (2nd ed.) + companion repo
2. PacktPublishing - *ML for Algorithmic Trading Second Edition* (same book, publisher repo)
3. bradleyboyuyang - *ML-HFT* framework (high-frequency ML trading)
4. Databento - *Building HFT Signals in Python with sklearn* (tutorial)

---

## 1. LSTM Architecture for Financial Time Series

### 1.1 Jansen/Packt Book Patterns (Chapter 18-19)

The book dedicates two full chapters to RNNs/LSTMs for trading. Key architecture:

```python
# Jansen's LSTM pattern for stock return prediction
import torch
import torch.nn as nn

class FinancialLSTM(nn.Module):
    """
    Jansen-style LSTM for financial time series.
    Key insight: use multiple stacked LSTM layers with dropout BETWEEN layers,
    not within layers (PyTorch's built-in dropout applies between layers).
    """
    def __init__(
        self,
        input_size: int,       # Number of features per timestep
        hidden_size: int = 128, # Hidden state dimension
        num_layers: int = 2,    # Stacked LSTM layers
        dropout: float = 0.2,   # Dropout between LSTM layers
        num_classes: int = 5,   # Output classes
        bidirectional: bool = False,  # Jansen uses unidirectional for causal data
    ):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
            bidirectional=bidirectional,
        )
        direction_factor = 2 if bidirectional else 1
        self.fc_dropout = nn.Dropout(0.3)  # Additional dropout before FC
        self.fc = nn.Linear(hidden_size * direction_factor, num_classes)

    def forward(self, x):
        # x shape: (batch, seq_len, features)
        lstm_out, (h_n, c_n) = self.lstm(x)
        # Use LAST hidden state (causal - only past information)
        last_hidden = lstm_out[:, -1, :]  # (batch, hidden_size)
        out = self.fc_dropout(last_hidden)
        out = self.fc(out)
        return out  # Raw logits, apply softmax in loss or post-processing
```

**Recommended hyperparameters from Jansen (financial data):**

| Parameter | Range | Jansen Default | Recommended for AlgoTrader |
|-----------|-------|----------------|---------------------------|
| `hidden_size` | 32-256 | 128 | 128 (Gold/SP500), 64 (BTC - less data) |
| `num_layers` | 1-3 | 2 | 2 (sweet spot: more capacity without vanishing gradients) |
| `dropout` | 0.1-0.5 | 0.2 | 0.3 (financial data is noisy, need regularization) |
| `sequence_length` | 10-120 | 60 | 60 bars (1h TF = 2.5 trading days) |
| `learning_rate` | 1e-4 to 1e-2 | 1e-3 | 1e-3 with ReduceLROnPlateau |
| `batch_size` | 32-256 | 64 | 64 |
| `epochs` | 50-200 | 100 | 100 with early stopping (patience=15) |
| `weight_decay` | 0-1e-4 | 1e-5 | 1e-5 (L2 regularization) |

### 1.2 ML-HFT Patterns

The ML-HFT repo uses a more sophisticated LSTM variant with attention:

```python
class LSTMWithAttention(nn.Module):
    """
    ML-HFT style: LSTM + self-attention on the sequence output.
    Attention helps the model focus on the most relevant timesteps
    (e.g., volatile bars, news events) rather than just the last bar.
    """
    def __init__(self, input_size, hidden_size=64, num_layers=2, num_classes=3):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers,
                            batch_first=True, dropout=0.2)
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1),
        )
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_size // 2, num_classes),
        )

    def forward(self, x):
        lstm_out, _ = self.lstm(x)  # (batch, seq_len, hidden)
        # Attention weights
        attn_weights = torch.softmax(
            self.attention(lstm_out).squeeze(-1), dim=1
        )  # (batch, seq_len)
        # Weighted sum of LSTM outputs
        context = torch.bmm(
            attn_weights.unsqueeze(1), lstm_out
        ).squeeze(1)  # (batch, hidden)
        return self.classifier(context)
```

### 1.3 Critical LSTM Implementation Notes

**Sequence construction (windowing) -- most common source of bugs:**

```python
def create_sequences(
    features: np.ndarray,
    targets: np.ndarray,
    seq_length: int = 60,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Create overlapping sequences for LSTM input.

    CRITICAL: Target is aligned to the LAST timestep of each window.
    The target at index i corresponds to the prediction horizon
    AFTER seeing features[i-seq_length+1 : i+1].

    Args:
        features: (n_samples, n_features) - already normalized
        targets: (n_samples,) - classification labels
        seq_length: Number of timesteps per sequence

    Returns:
        X: (n_sequences, seq_length, n_features)
        y: (n_sequences,) - target for each sequence
    """
    X, y = [], []
    for i in range(seq_length, len(features)):
        X.append(features[i - seq_length:i])
        y.append(targets[i])  # Target is for the LAST timestep
    return np.array(X), np.array(y)
```

**Walk-forward adaptation for LSTM (AlgoTrader integration):**

The current `WalkForwardSplitter` produces flat index arrays. For LSTM, we need
to convert each split's indices into sequences:

```python
# In the training loop, after getting walk-forward indices:
X_train_seq, y_train_seq = create_sequences(
    X[split.train_indices], y[split.train_indices], seq_length=60
)
X_val_seq, y_val_seq = create_sequences(
    X[split.val_indices], y[split.val_indices], seq_length=60
)
# IMPORTANT: For val/test, include the last seq_length bars from
# the previous split as prefix so we don't lose data at boundaries
```

**Training loop pattern from Jansen:**

```python
def train_lstm_epoch(model, dataloader, optimizer, criterion, device):
    model.train()
    total_loss = 0
    for X_batch, y_batch in dataloader:
        X_batch, y_batch = X_batch.to(device), y_batch.to(device)
        optimizer.zero_grad()
        logits = model(X_batch)
        loss = criterion(logits, y_batch)
        loss.backward()
        # Gradient clipping - ESSENTIAL for LSTM stability
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        total_loss += loss.item()
    return total_loss / len(dataloader)
```

### 1.4 What AlgoTrader Currently Has vs. Needs

**Has:**
- `BaseMLModel` ABC with `fit/predict/predict_proba/save/load` interface
- Walk-forward splitter with purge/embargo
- Feature normalization (rolling z-score)
- 5-class ATR-relative target builder

**Needs (for LSTM implementation):**
- `LSTMClassifier` class extending `BaseMLModel`
- Sequence windowing utility (flat features -> 3D tensors)
- PyTorch training loop with gradient clipping, LR scheduling
- GPU/CPU device management
- Early stopping based on validation loss
- Model serialization (state_dict + hyperparams)
- Adaptation of `ModelTrainer` to handle 3D input for sequential models

---

## 2. Temporal Fusion Transformer (TFT)

### 2.1 Jansen's TFT Coverage (Chapter 19)

Jansen covers TFT extensively as the state-of-the-art for multi-horizon
financial forecasting. He uses the `pytorch-forecasting` library:

```python
# Jansen's TFT pattern using pytorch-forecasting
from pytorch_forecasting import TemporalFusionTransformer
from pytorch_forecasting.data import TimeSeriesDataSet

# Step 1: Create TimeSeriesDataSet (handles windowing automatically)
training_dataset = TimeSeriesDataSet(
    data=train_df,
    time_idx="time_idx",              # Integer time index
    target="target",                   # What to predict
    group_ids=["asset"],              # Group by asset (allows multi-asset)
    max_encoder_length=60,             # Lookback window
    max_prediction_length=6,           # Prediction horizon (bars)
    static_categoricals=["asset"],     # Asset identifier
    time_varying_known_reals=[         # Features known in advance
        "day_of_week", "hour_of_day",
        "month", "is_us_market_open",
    ],
    time_varying_unknown_reals=[       # Features only known up to now
        "close_norm", "volume_norm", "rsi_14",
        "macd", "atr_ratio", "bb_pctb",
        "returns_1", "returns_5",
    ],
    time_varying_unknown_categoricals=[
        "regime",                      # Market regime as categorical
    ],
    add_relative_time_idx=True,
    add_target_scales=True,
    add_encoder_length=True,
)
```

**TFT architecture hyperparameters (Jansen recommendations for finance):**

| Parameter | Range | Recommended | Notes |
|-----------|-------|-------------|-------|
| `hidden_size` | 16-128 | 64 | Smaller than LSTM; attention compensates |
| `attention_head_size` | 1-4 | 4 | More heads = better feature interaction |
| `dropout` | 0.1-0.3 | 0.1 | TFT is naturally regularized by gating |
| `hidden_continuous_size` | 8-64 | 32 | Size for continuous variable embeddings |
| `learning_rate` | 1e-4 to 1e-2 | 3e-3 | Can be higher than LSTM |
| `max_encoder_length` | 30-120 | 60 | Same as LSTM sequence length |
| `max_prediction_length` | 1-24 | 6 | Match your horizon_bars |

```python
# TFT model creation (Jansen pattern)
tft = TemporalFusionTransformer.from_dataset(
    training_dataset,
    hidden_size=64,
    attention_head_size=4,
    dropout=0.1,
    hidden_continuous_size=32,
    output_size=5,                      # 5 classes for classification
    loss=CrossEntropy(),                # Classification loss
    log_interval=10,
    reduce_on_plateau_patience=5,
    learning_rate=3e-3,
)
```

### 2.2 Custom TFT Implementation (Without pytorch-forecasting)

For more control (recommended for AlgoTrader), a custom implementation:

```python
class TemporalFusionTransformerClassifier(nn.Module):
    """
    Simplified TFT for classification.
    Key components:
    1. Variable Selection Networks (VSN) - learns which features matter
    2. LSTM encoder for temporal patterns
    3. Multi-head attention for long-range dependencies
    4. Gated Residual Networks (GRN) for non-linear processing
    """
    def __init__(
        self,
        num_continuous_features: int,
        num_categorical_features: int = 0,
        hidden_size: int = 64,
        num_attention_heads: int = 4,
        num_lstm_layers: int = 1,
        dropout: float = 0.1,
        num_classes: int = 5,
        seq_length: int = 60,
    ):
        super().__init__()
        self.hidden_size = hidden_size

        # Variable Selection Network
        self.vsn = VariableSelectionNetwork(
            num_continuous_features, hidden_size, dropout
        )

        # LSTM encoder
        self.lstm_encoder = nn.LSTM(
            input_size=hidden_size,
            hidden_size=hidden_size,
            num_layers=num_lstm_layers,
            batch_first=True,
            dropout=dropout if num_lstm_layers > 1 else 0.0,
        )

        # Multi-head attention
        self.attention = nn.MultiheadAttention(
            embed_dim=hidden_size,
            num_heads=num_attention_heads,
            dropout=dropout,
            batch_first=True,
        )

        # Gated Residual Network for post-attention processing
        self.grn = GatedResidualNetwork(hidden_size, hidden_size, dropout)

        # Classification head
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size // 2, num_classes),
        )

    def forward(self, x_continuous, x_categorical=None):
        # Variable selection
        selected, var_weights = self.vsn(x_continuous)

        # LSTM encoding
        lstm_out, _ = self.lstm_encoder(selected)

        # Self-attention (causal mask for temporal data)
        seq_len = lstm_out.size(1)
        causal_mask = torch.triu(
            torch.ones(seq_len, seq_len, device=lstm_out.device), diagonal=1
        ).bool()
        attn_out, attn_weights = self.attention(
            lstm_out, lstm_out, lstm_out, attn_mask=causal_mask
        )

        # Gated residual connection
        enriched = self.grn(attn_out + lstm_out)

        # Use last timestep for classification
        last = enriched[:, -1, :]
        return self.classifier(last), var_weights, attn_weights


class VariableSelectionNetwork(nn.Module):
    """Learns feature importance weights dynamically per sample."""
    def __init__(self, input_size, hidden_size, dropout=0.1):
        super().__init__()
        self.flattened_grn = GatedResidualNetwork(
            input_size, input_size, dropout, context_size=hidden_size
        )
        self.softmax = nn.Softmax(dim=-1)
        self.feature_transform = nn.Linear(input_size, hidden_size)

    def forward(self, x):
        # x: (batch, seq_len, n_features)
        # Compute feature importance weights
        flat = x.reshape(-1, x.size(-1))
        weights = self.softmax(self.flattened_grn(flat))
        weights = weights.reshape(x.shape)

        # Apply weights and transform
        selected = x * weights
        return self.feature_transform(selected), weights


class GatedResidualNetwork(nn.Module):
    """Core building block of TFT: linear + ELU + gating + residual."""
    def __init__(self, input_size, hidden_size, dropout=0.1, context_size=None):
        super().__init__()
        self.fc1 = nn.Linear(input_size + (context_size or 0), hidden_size)
        self.elu = nn.ELU()
        self.fc2 = nn.Linear(hidden_size, hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.gate = nn.Linear(hidden_size, hidden_size)
        self.sigmoid = nn.Sigmoid()
        self.layer_norm = nn.LayerNorm(hidden_size)
        self.skip = nn.Linear(input_size, hidden_size) if input_size != hidden_size else nn.Identity()

    def forward(self, x, context=None):
        if context is not None:
            x_input = torch.cat([x, context], dim=-1)
        else:
            x_input = x
        hidden = self.elu(self.fc1(x_input))
        hidden = self.dropout(self.fc2(hidden))
        gate = self.sigmoid(self.gate(hidden))
        gated = gate * hidden
        return self.layer_norm(gated + self.skip(x))
```

### 2.3 TFT's Unique Value for AlgoTrader

The TFT's Variable Selection Network provides **interpretable feature importance
per prediction**, which maps directly to AlgoTrader's need for explainability:

```python
# After inference:
prediction, var_weights, attn_weights = tft_model(x_continuous)

# var_weights tells us: for THIS specific prediction, which features mattered most
# This is much more useful than static XGBoost feature importance
top_features = torch.topk(var_weights[:, -1, :], k=5)
# "Gold price and DXY drove this BUY signal on BTC"
```

---

## 3. Feature Engineering Pipelines

### 3.1 Jansen's Feature Engineering (Chapters 4-5, 24-25)

Jansen's approach is the most comprehensive across the repositories studied.
His feature taxonomy:

**Category 1: Price-derived (AlgoTrader already implements these)**
```python
# Technical indicators - AlgoTrader has all of these
features_price = [
    "returns_1d", "returns_5d", "returns_21d", "returns_63d",  # Multi-horizon returns
    "volatility_21d", "volatility_63d",    # Rolling volatility
    "rsi_14", "macd", "macd_signal",       # Momentum
    "bb_pctb", "bb_width",                 # Mean reversion
    "atr_14", "atr_ratio",                # Volatility regime
]
```

**Category 2: Lagged features (Jansen's key insight -- AlgoTrader MISSING)**
```python
# Create lagged versions of key features
# This gives the model explicit access to recent history without
# relying solely on LSTM memory
def add_lagged_features(
    df: pl.DataFrame,
    columns: list[str],
    lags: list[int] = [1, 2, 3, 5, 10, 21],
) -> pl.DataFrame:
    """
    Add lagged values of features.
    Critical for tree-based models (XGBoost) which cannot learn temporal
    patterns without explicit lag features.
    """
    for col in columns:
        for lag in lags:
            df = df.with_columns(
                pl.col(col).shift(lag).alias(f"{col}_lag_{lag}")
            )
    return df

# Which features to lag (Jansen's recommendation):
LAG_FEATURES = [
    "returns_1",       # Recent return momentum
    "rsi_14",          # RSI trajectory
    "macd_histogram",  # MACD momentum
    "volume_sma_ratio", # Volume trend
    "atr_ratio",       # Volatility trajectory
    "bb_pctb",         # BB position trajectory
]
LAG_PERIODS = [1, 2, 3, 5, 10]  # 1h bars: up to ~2 trading days
```

**Category 3: Interaction features (Jansen Chapter 6)**
```python
def add_interaction_features(df: pl.DataFrame) -> pl.DataFrame:
    """
    Cross-feature interactions that help tree models.
    These encode domain knowledge about market microstructure.
    """
    # Momentum + volume confirmation
    df = df.with_columns(
        (pl.col("returns_1") * pl.col("volume_sma_ratio")).alias("return_volume_interaction")
    )

    # Volatility regime indicator
    df = df.with_columns(
        (pl.col("atr_ratio") * pl.col("bb_width")).alias("volatility_regime_signal")
    )

    # RSI divergence from price (price new high but RSI lower)
    df = df.with_columns(
        (
            pl.col("close").rolling_max(window_size=14) == pl.col("close")
        ).cast(pl.Int32).alias("_price_new_high"),
    )
    df = df.with_columns(
        (
            pl.col("rsi_14") - pl.col("rsi_14").rolling_max(window_size=14)
        ).alias("rsi_price_divergence")
    )

    # Trend strength: ADX * sign of EMA slope
    df = df.with_columns(
        (
            pl.col("adx") * (pl.col("ema_21") - pl.col("ema_21").shift(1)).sign()
        ).alias("trend_strength_directed")
    )

    return df
```

**Category 4: Time-based features (Jansen + Databento)**
```python
def add_time_features(df: pl.DataFrame) -> pl.DataFrame:
    """
    Cyclical time features using sin/cos encoding.
    Critical for capturing intraday patterns and seasonality.
    """
    if "timestamp" not in df.columns:
        return df

    ts = pl.col("timestamp")

    df = df.with_columns([
        # Hour of day (cyclical)
        (2 * np.pi * ts.dt.hour() / 24).sin().alias("hour_sin"),
        (2 * np.pi * ts.dt.hour() / 24).cos().alias("hour_cos"),
        # Day of week (cyclical)
        (2 * np.pi * ts.dt.weekday() / 5).sin().alias("dow_sin"),
        (2 * np.pi * ts.dt.weekday() / 5).cos().alias("dow_cos"),
        # Month (cyclical)
        (2 * np.pi * ts.dt.month() / 12).sin().alias("month_sin"),
        (2 * np.pi * ts.dt.month() / 12).cos().alias("month_cos"),
        # Is US market open (9:30-16:00 ET)
        (
            (ts.dt.hour() >= 14) & (ts.dt.hour() < 21)  # UTC approximation
        ).cast(pl.Int32).alias("us_market_open"),
    ])

    return df
```

### 3.2 ML-HFT Feature Pipeline

The ML-HFT repo focuses on order book features (not directly applicable to
AlgoTrader's OHLC-based system), but its feature selection methodology is
valuable:

```python
# ML-HFT's feature importance-based selection pipeline
def select_features_iteratively(
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: list[str],
    n_features_to_select: int = 30,
) -> list[str]:
    """
    Iterative feature selection using XGBoost importance.
    Train -> rank features -> remove bottom 20% -> repeat.
    """
    current_features = list(range(len(feature_names)))

    while len(current_features) > n_features_to_select:
        model = xgb.XGBClassifier(
            max_depth=4, n_estimators=100, learning_rate=0.1
        )
        model.fit(X_train[:, current_features], y_train)

        importance = model.feature_importances_
        # Remove bottom 20% of features
        threshold = np.percentile(importance, 20)
        current_features = [
            f for f, imp in zip(current_features, importance)
            if imp > threshold
        ]

    return [feature_names[i] for i in current_features]
```

### 3.3 Databento Tutorial Features

The Databento tutorial focuses on order-flow features from L2 book data:

```python
# While AlgoTrader uses OHLC, the derived feature concepts apply:
# 1. Price impact: how much price moves per unit of volume
# 2. Imbalance: ratio of buy vs sell pressure
# 3. Microstructure noise: high-frequency volatility residual

# Adapted for OHLC data:
def add_microstructure_features(df: pl.DataFrame) -> pl.DataFrame:
    """Microstructure-inspired features from OHLC data."""
    # Price impact proxy (Amihud illiquidity)
    df = df.with_columns(
        (
            pl.col("returns_1").abs() / (pl.col("volume") + 1e-10)
        ).alias("amihud_illiquidity")
    )

    # Kyle's lambda proxy (price sensitivity to order flow)
    df = df.with_columns(
        (
            pl.col("close").diff().abs()
            / pl.col("volume").rolling_sum(window_size=5).sqrt()
        ).fill_nan(0.0).alias("kyle_lambda_proxy")
    )

    # Roll's spread estimate (from serial covariance of returns)
    df = df.with_columns(
        (
            pl.col("returns_1") * pl.col("returns_1").shift(1)
        ).alias("_return_cov")
    )
    df = df.with_columns(
        pl.when(pl.col("_return_cov") < 0)
        .then(2 * (-pl.col("_return_cov")).sqrt())
        .otherwise(0.0)
        .rolling_mean(window_size=20)
        .alias("roll_spread_estimate")
    )
    df = df.drop(["_return_cov"])

    return df
```

### 3.4 Feature Engineering Gap Analysis for AlgoTrader

| Feature Category | Current Status | Priority | Effort |
|-----------------|----------------|----------|--------|
| Technical indicators (EMA, RSI, MACD, BB, ATR, ADX) | COMPLETE | - | - |
| Rolling z-score normalization | COMPLETE | - | - |
| Log transform for volume | COMPLETE | - | - |
| **Lagged features** | **MISSING** | **HIGH** | Low |
| **Time/cyclical features** | **MISSING** | **HIGH** | Low |
| **Interaction features** | **MISSING** | **MEDIUM** | Low |
| **Microstructure proxies** | **MISSING** | **LOW** | Low |
| FRED macro data | MISSING (Phase 2B) | HIGH | Medium |
| FinBERT sentiment | MISSING (Phase 2B) | MEDIUM | High |
| Blockchain metrics for BTC | MISSING (Phase 2B) | LOW | Medium |

---

## 4. XGBoost/LightGBM Tuning for Financial Classification

### 4.1 Jansen's Gradient Boosting Approach (Chapters 11-12)

Jansen provides the most thorough treatment of tree-based models for trading.
Key insights that differ from standard ML:

**Hyperparameter strategy (financial data is NOISY):**

```python
# Jansen's recommended XGBoost config for financial classification
XGBOOST_FINANCIAL_CONFIG = {
    # Conservative depth - overfitting is the #1 risk
    "max_depth": 4,               # Jansen: 3-6, shallower is better for noisy data
    "min_child_weight": 10,       # Higher than default (1) to prevent fitting noise
    "learning_rate": 0.05,        # Lower than default (0.3) for better generalization
    "n_estimators": 1000,         # High, but with early stopping
    "early_stopping_rounds": 50,  # Critical: stops when val loss stops improving

    # Subsampling for regularization
    "subsample": 0.7,             # Row subsampling (Jansen: 0.6-0.8)
    "colsample_bytree": 0.7,     # Feature subsampling per tree
    "colsample_bylevel": 0.7,    # Feature subsampling per level

    # Regularization
    "reg_alpha": 0.1,             # L1 regularization
    "reg_lambda": 1.0,            # L2 regularization
    "gamma": 0.1,                 # Minimum loss reduction for split

    # Multi-class
    "objective": "multi:softprob",
    "num_class": 5,
    "eval_metric": "mlogloss",
    "tree_method": "hist",         # Fast histogram-based
}
```

**LightGBM alternative (Jansen Chapter 12):**

```python
LIGHTGBM_FINANCIAL_CONFIG = {
    "objective": "multiclass",
    "num_class": 5,
    "metric": "multi_logloss",
    "boosting_type": "gbdt",

    "num_leaves": 31,              # Key LightGBM param (replaces max_depth)
    "max_depth": -1,               # Let num_leaves control complexity
    "min_data_in_leaf": 20,        # Like min_child_weight
    "learning_rate": 0.05,
    "n_estimators": 1000,

    "feature_fraction": 0.7,       # colsample_bytree equivalent
    "bagging_fraction": 0.7,       # subsample equivalent
    "bagging_freq": 5,             # Apply bagging every 5 iterations

    "lambda_l1": 0.1,
    "lambda_l2": 1.0,
    "min_gain_to_split": 0.1,     # gamma equivalent

    "verbose": -1,
}
```

### 4.2 AlgoTrader's Current XGBoost vs. Jansen's Recommendations

Comparing `backend/src/models/xgboost_model.py` with research best practices:

| Parameter | AlgoTrader Current | Jansen Recommended | Action |
|-----------|-------------------|-------------------|--------|
| `max_depth` | 6 | 4 | **Reduce to 4** (less overfitting) |
| `learning_rate` | 0.1 | 0.05 | **Reduce to 0.05** |
| `n_estimators` | 500 | 1000 | **Increase to 1000** (early stopping compensates) |
| `min_child_weight` | 5 | 10 | **Increase to 10** |
| `subsample` | 0.8 | 0.7 | **Reduce to 0.7** |
| `colsample_bytree` | 0.8 | 0.7 | **Reduce to 0.7** |
| `gamma` | (not set) | 0.1 | **Add gamma=0.1** |
| `colsample_bylevel` | (not set) | 0.7 | **Add colsample_bylevel=0.7** |

**The current baseline F1 of 0.20-0.24 can likely be improved to 0.30-0.40 by:**
1. Reducing max_depth (less overfitting)
2. Adding lagged features (gives XGBoost temporal context)
3. Adding time features (captures intraday patterns)
4. Using the tuned hyperparameters above

### 4.3 Optuna Hyperparameter Search (Jansen + ML-HFT pattern)

```python
import optuna

def objective_xgboost(trial, X_train, y_train, X_val, y_val):
    """Optuna objective for XGBoost hyperparameter tuning."""
    params = {
        "max_depth": trial.suggest_int("max_depth", 3, 7),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
        "n_estimators": 1000,  # Fixed, rely on early stopping
        "min_child_weight": trial.suggest_int("min_child_weight", 5, 20),
        "subsample": trial.suggest_float("subsample", 0.6, 0.9),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 0.9),
        "gamma": trial.suggest_float("gamma", 0.0, 0.5),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 1.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
    }

    model = xgb.XGBClassifier(
        **params,
        objective="multi:softprob",
        num_class=5,
        eval_metric="mlogloss",
        tree_method="hist",
        early_stopping_rounds=50,
    )

    # Use sample weights for class imbalance
    class_counts = np.bincount(y_train.astype(int), minlength=5)
    sample_weights = np.array([
        len(y_train) / (5 * class_counts[int(y)]) for y in y_train
    ])

    model.fit(
        X_train, y_train,
        sample_weight=sample_weights,
        eval_set=[(X_val, y_val)],
        verbose=False,
    )

    y_pred = model.predict(X_val)
    return f1_score(y_val, y_pred, average="macro")

# Run optimization
study = optuna.create_study(direction="maximize")
study.optimize(lambda trial: objective_xgboost(
    trial, X_train, y_train, X_val, y_val
), n_trials=100)
```

---

## 5. Classification Strategy: 5-Class vs 3-Class vs Binary

### 5.1 What the Research Shows

**Jansen (Chapter 7-8):** Uses binary classification (up/down) for simplicity
in examples, but recommends multi-class for production systems to capture
signal strength.

**ML-HFT:** Uses 3-class (up/flat/down) with fixed-threshold approach:
```python
# ML-HFT's 3-class approach
# Return > +0.001 -> UP (1)
# Return < -0.001 -> DOWN (-1)
# Otherwise       -> FLAT (0)
```

**Databento tutorial:** Uses binary classification (up/down) with aggressive
filtering: only predict when confidence > 0.6, treat everything else as "no
trade."

### 5.2 Comparison for AlgoTrader's Use Case

| Approach | Pros | Cons | Best For |
|----------|------|------|----------|
| **Binary (up/down)** | Simple, highest accuracy, balanced classes | No signal strength, forced to predict | Quick MVP, baselines |
| **3-class (buy/hold/sell)** | Captures uncertainty, allows "no trade" | HOLD class often dominates (60-70%) | Moderate approach |
| **5-class (current)** | Rich signal, captures magnitude | Sparse extremes, harder to learn | Production with sufficient data |
| **Hierarchical** | Binary first, then magnitude | More complex, two models | Best of both worlds |

### 5.3 Recommended Approach for AlgoTrader

The current 5-class ATR-relative system is well-designed but may be causing the
low F1 scores because STRONG_BUY and STRONG_SELL are rare events. Jansen's
solution: **hierarchical classification**:

```python
class HierarchicalTargetBuilder:
    """
    Two-stage classification:
    Stage 1: Direction (3-class: UP / FLAT / DOWN)
    Stage 2: Magnitude (2-class: STRONG / NORMAL)

    The ensemble combines both stages:
    - If Stage 1 = UP and Stage 2 = STRONG -> STRONG_BUY
    - If Stage 1 = UP and Stage 2 = NORMAL -> BUY
    - If Stage 1 = FLAT -> HOLD (regardless of Stage 2)
    """
    def __init__(self, horizon_bars: int = 6, atr_column: str = "atr_14"):
        self.horizon_bars = horizon_bars
        self.atr_column = atr_column

    def build_direction_target(self, df: pl.DataFrame) -> pl.DataFrame:
        """3-class target: 0=DOWN, 1=FLAT, 2=UP"""
        # ... ATR-relative with 0.5x threshold
        pass

    def build_magnitude_target(self, df: pl.DataFrame) -> pl.DataFrame:
        """2-class target: 0=NORMAL, 1=STRONG (conditioned on non-FLAT)"""
        # ... ATR-relative with 1.5x threshold
        pass
```

**Alternative: Class merging during training, expanding during inference:**

```python
# Train on 3 classes (better F1), map back to 5 for risk sizing
CLASS_MAPPING_3TO5 = {
    0: {  # DOWN -> SELL or STRONG_SELL based on confidence
        "high_conf": SignalClass.STRONG_SELL,  # confidence > 0.8
        "normal": SignalClass.SELL,
    },
    1: {  # FLAT -> HOLD
        "any": SignalClass.HOLD,
    },
    2: {  # UP -> BUY or STRONG_BUY based on confidence
        "high_conf": SignalClass.STRONG_BUY,
        "normal": SignalClass.BUY,
    },
}
```

---

## 6. Ensemble Stacking Techniques

### 6.1 Jansen's Ensemble Approach (Chapter 12)

Jansen describes two main ensemble patterns for financial ML:

**Pattern 1: Stacking with out-of-fold predictions**

```python
from sklearn.model_selection import cross_val_predict

def build_stacking_ensemble(
    base_models: list,  # [LSTM, TFT, XGBoost]
    meta_model,         # XGBoost meta-learner
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_test: np.ndarray,
    n_folds: int = 5,   # Internal CV for stacking
) -> tuple[np.ndarray, np.ndarray]:
    """
    Proper stacking with out-of-fold predictions to prevent leakage.

    CRITICAL: The meta-learner must be trained on OUT-OF-FOLD predictions
    from the base models, not their training set predictions.
    Otherwise, base models that overfit will dominate the ensemble.
    """
    # Step 1: Generate out-of-fold predictions for each base model
    stacking_train = np.zeros((len(X_train), len(base_models) * 5))  # 5 classes each
    stacking_test = np.zeros((len(X_test), len(base_models) * 5))

    for i, model in enumerate(base_models):
        # Out-of-fold predictions on training set
        oof_preds = cross_val_predict(
            model, X_train, y_train,
            cv=PurgedTimeSeriesSplit(n_folds),  # Time-series aware CV!
            method="predict_proba",
        )
        stacking_train[:, i*5:(i+1)*5] = oof_preds

        # Full training set prediction on test set
        model.fit(X_train, y_train)
        stacking_test[:, i*5:(i+1)*5] = model.predict_proba(X_test)

    # Step 2: Train meta-learner on stacking features
    meta_model.fit(stacking_train, y_train)
    final_predictions = meta_model.predict_proba(stacking_test)

    return final_predictions, stacking_test
```

**Pattern 2: Weighted averaging (simpler, often competitive)**

```python
class WeightedEnsemble:
    """
    Simpler ensemble: weighted average of base model probabilities.
    Weights learned from validation performance.
    """
    def __init__(self):
        self.weights = {}

    def fit_weights(
        self,
        model_predictions: dict[str, np.ndarray],  # model_name -> probas
        y_true: np.ndarray,
    ):
        """
        Learn optimal weights using scipy optimization.
        Minimizes log-loss on validation set.
        """
        from scipy.optimize import minimize

        model_names = list(model_predictions.keys())
        n_models = len(model_names)
        probas = np.stack([model_predictions[name] for name in model_names])

        def neg_log_likelihood(w):
            w = np.exp(w) / np.exp(w).sum()  # Softmax to ensure sum=1
            blended = np.tensordot(w, probas, axes=([0], [0]))
            blended = np.clip(blended, 1e-10, 1 - 1e-10)
            return -np.mean(np.log(blended[np.arange(len(y_true)), y_true]))

        result = minimize(neg_log_likelihood, np.ones(n_models) / n_models)
        opt_weights = np.exp(result.x) / np.exp(result.x).sum()

        self.weights = {name: float(w) for name, w in zip(model_names, opt_weights)}

    def predict_proba(self, model_predictions: dict[str, np.ndarray]) -> np.ndarray:
        """Blend predictions using learned weights."""
        probas = []
        for name, pred in model_predictions.items():
            weight = self.weights.get(name, 1.0 / len(model_predictions))
            probas.append(pred * weight)
        return np.sum(probas, axis=0)
```

### 6.2 Ensemble Integration for AlgoTrader

Current AlgoTrader architecture calls for XGBoost meta-learner stacking.
Here is the recommended implementation pattern:

```python
class EnsemblePredictor:
    """
    Orchestrates ensemble inference for AlgoTrader.

    Pipeline:
    1. XGBoost: flat features -> predict_proba
    2. LSTM: sequenced features -> predict_proba
    3. TFT: sequenced features + static -> predict_proba
    4. Meta-learner: [proba_xgb, proba_lstm, proba_tft, meta_features] -> final
    """
    def __init__(
        self,
        xgboost_model: XGBoostClassifier,
        lstm_model: LSTMClassifier,
        tft_model: TFTClassifier,
        meta_model: XGBoostClassifier,
    ):
        self.base_models = {
            "xgboost": xgboost_model,
            "lstm": lstm_model,
            "tft": tft_model,
        }
        self.meta_model = meta_model

    def predict(
        self,
        features_flat: np.ndarray,    # (1, n_features) for XGBoost
        features_seq: np.ndarray,     # (1, seq_len, n_features) for LSTM/TFT
    ) -> PredictionResult:
        """Generate ensemble prediction."""
        base_predictions = {}

        # Base model predictions
        base_predictions["xgboost"] = self.base_models["xgboost"].predict_proba(features_flat)
        base_predictions["lstm"] = self.base_models["lstm"].predict_proba(features_seq)
        base_predictions["tft"] = self.base_models["tft"].predict_proba(features_seq)

        # Meta-features: concatenate all base probabilities + model agreement
        meta_features = np.concatenate([
            base_predictions["xgboost"],
            base_predictions["lstm"],
            base_predictions["tft"],
        ], axis=1)  # (1, 15) for 3 models x 5 classes

        # Add model agreement features
        votes = np.array([
            np.argmax(base_predictions["xgboost"]),
            np.argmax(base_predictions["lstm"]),
            np.argmax(base_predictions["tft"]),
        ])
        agreement = (votes == np.median(votes)).sum() / len(votes)
        max_conf = max(p.max() for p in base_predictions.values())
        meta_features = np.concatenate([
            meta_features,
            [[agreement, max_conf]],
        ], axis=1)

        # Meta-learner final prediction
        final_proba = self.meta_model.predict_proba(meta_features)[0]
        predicted_class = int(np.argmax(final_proba))

        return PredictionResult(
            signal_class=predicted_class,
            signal_name=SignalClass(predicted_class).name,
            confidence=float(final_proba[predicted_class]),
            probabilities={
                SignalClass(i).name: float(p) for i, p in enumerate(final_proba)
            },
        )
```

### 6.3 Meta-Learner Training Pattern

```python
def train_meta_learner(
    base_models: dict[str, BaseMLModel],
    meta_model: XGBoostClassifier,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    splitter: WalkForwardSplitter,
) -> XGBoostClassifier:
    """
    Train meta-learner using out-of-fold base model predictions.

    CRITICAL: Use walk-forward splits (not random CV) to generate
    out-of-fold predictions. This preserves temporal ordering.
    """
    n_models = len(base_models)
    n_classes = 5
    oof_predictions = np.zeros((len(X_train), n_models * n_classes))

    # Generate out-of-fold predictions
    for split in splitter.split(len(X_train)):
        X_fold_train = X_train[split.train_indices]
        y_fold_train = y_train[split.train_indices]
        X_fold_val = X_train[split.val_indices]

        for i, (name, model) in enumerate(base_models.items()):
            model.fit(X_fold_train, y_fold_train)
            fold_preds = model.predict_proba(X_fold_val)
            oof_predictions[split.val_indices, i*n_classes:(i+1)*n_classes] = fold_preds

    # Remove rows where we don't have OOF predictions (first training window)
    valid_mask = oof_predictions.sum(axis=1) > 0
    oof_valid = oof_predictions[valid_mask]
    y_valid = y_train[valid_mask]

    # Train meta-learner
    meta_model.fit(oof_valid, y_valid)
    return meta_model
```

---

## 7. Data Preprocessing for Financial ML

### 7.1 Normalization Strategy Comparison

| Method | Jansen | ML-HFT | Databento | AlgoTrader Current |
|--------|--------|--------|-----------|-------------------|
| Rolling z-score | Primary | Yes | No | Yes (252 window) |
| Min-max scaling | Alternative | No | Yes | No |
| Log transform (volume) | Yes | Yes | No | Yes |
| Rank transform | Yes (Chapter 4) | No | No | **MISSING** |
| Winsorization/clipping | 3 sigma | No | No | 5 sigma |

**Jansen's rank transform (recommended addition):**

```python
def rank_normalize(
    df: pl.DataFrame,
    columns: list[str],
    window: int = 252,
) -> pl.DataFrame:
    """
    Rank-based normalization: maps values to [0, 1] based on
    their rank within a rolling window.

    Benefits:
    - Robust to outliers (unlike z-score)
    - Bounded output (unlike z-score)
    - Preserves ordinal relationships
    - Handles non-Gaussian distributions well (financial data!)
    """
    for col in columns:
        if col not in df.columns:
            continue

        # Rolling rank: what percentile is the current value?
        rank_col = f"{col}_rank"
        df = df.with_columns(
            (
                pl.col(col).rolling_map(
                    function=lambda s: (s.rank()[-1] - 1) / (len(s) - 1) if len(s) > 1 else 0.5,
                    window_size=window,
                    min_periods=window // 2,
                )
            ).alias(rank_col)
        )

    return df
```

### 7.2 Missing Data Handling

**Jansen's approach (more sophisticated than AlgoTrader's current `nan_to_num(0.0)`):**

```python
def handle_missing_data(df: pl.DataFrame, feature_cols: list[str]) -> pl.DataFrame:
    """
    Multi-strategy missing data handling for financial features.

    Strategy by feature type:
    - Returns/momentum: fill with 0 (no return = no movement)
    - Moving averages: forward fill (last valid value)
    - Oscillators (RSI, BB%B): fill with neutral value (50, 0.5)
    - Volume: fill with rolling median
    - Derived features: fill with 0 after log warning
    """
    # Returns - fill with 0
    return_cols = [c for c in feature_cols if c.startswith("returns_")]
    for col in return_cols:
        df = df.with_columns(pl.col(col).fill_null(0.0))

    # EMAs - forward fill
    ema_cols = [c for c in feature_cols if c.startswith("ema_")]
    for col in ema_cols:
        df = df.with_columns(pl.col(col).forward_fill())

    # RSI - fill with 50 (neutral)
    rsi_cols = [c for c in feature_cols if c.startswith("rsi_")]
    for col in rsi_cols:
        df = df.with_columns(pl.col(col).fill_null(50.0))

    # BB %B - fill with 0.5 (middle of band)
    if "bb_pctb" in feature_cols:
        df = df.with_columns(pl.col("bb_pctb").fill_null(0.5))

    # Everything else - fill with 0
    remaining = [c for c in feature_cols if c in df.columns]
    for col in remaining:
        if df[col].null_count() > 0:
            df = df.with_columns(pl.col(col).fill_null(0.0))

    return df
```

### 7.3 Stationarity Enforcement

```python
def enforce_stationarity(df: pl.DataFrame) -> pl.DataFrame:
    """
    Jansen's stationarity pipeline.
    Financial time series must be stationary for ML models.

    Non-stationary features (prices, OBV) -> differencing or returns
    Already-stationary features (RSI, returns) -> use as-is
    Trend features (EMA) -> use cross/spread instead of raw value
    """
    # Convert EMA levels to spreads (stationary!)
    if "ema_8" in df.columns and "close" in df.columns:
        df = df.with_columns(
            ((pl.col("ema_8") - pl.col("close")) / pl.col("close")).alias("ema_8_spread")
        )
    if "ema_21" in df.columns and "close" in df.columns:
        df = df.with_columns(
            ((pl.col("ema_21") - pl.col("close")) / pl.col("close")).alias("ema_21_spread")
        )
    if "ema_50" in df.columns and "close" in df.columns:
        df = df.with_columns(
            ((pl.col("ema_50") - pl.col("close")) / pl.col("close")).alias("ema_50_spread")
        )
    if "ema_200" in df.columns and "close" in df.columns:
        df = df.with_columns(
            ((pl.col("ema_200") - pl.col("close")) / pl.col("close")).alias("ema_200_spread")
        )

    # MACD is already stationary (difference of EMAs)
    # RSI is already stationary (bounded oscillator)
    # ATR ratio is already stationary (normalized by close)
    # BB %B is already stationary (bounded 0-1)
    # Returns are already stationary (by definition)

    return df
```

---

## 8. Walk-Forward vs Expanding Window vs Time-Series CV

### 8.1 Comparison from Research

| Method | Jansen | ML-HFT | Description | When to Use |
|--------|--------|--------|-------------|-------------|
| **Walk-forward (rolling)** | Primary | Yes | Fixed window slides forward | Default for AlgoTrader |
| **Expanding window** | Alternative | No | Window grows from start | When more data always helps |
| **Purged K-fold** | Yes | No | K temporal folds with purge gaps | Hyperparameter tuning |
| **Combinatorial purged CV** | Yes (Ch. 7) | No | All possible train/test combinations | Most robust evaluation |

### 8.2 Jansen's Purged K-Fold Implementation

```python
class PurgedKFold:
    """
    Jansen's purged K-fold for time series.
    Unlike standard K-fold, this:
    1. Never shuffles data
    2. Adds purge gap between train and test to prevent leakage
    3. Adds embargo period after test set
    """
    def __init__(self, n_splits=5, purge_gap=5, embargo=2):
        self.n_splits = n_splits
        self.purge_gap = purge_gap
        self.embargo = embargo

    def split(self, n_samples):
        fold_size = n_samples // self.n_splits
        for i in range(self.n_splits):
            test_start = i * fold_size
            test_end = min((i + 1) * fold_size, n_samples)

            # Training: everything except test + purge + embargo
            train_end_before = max(0, test_start - self.purge_gap)
            train_start_after = min(n_samples, test_end + self.embargo)

            train_indices = np.concatenate([
                np.arange(0, train_end_before),
                np.arange(train_start_after, n_samples),
            ])
            test_indices = np.arange(test_start, test_end)

            yield train_indices, test_indices
```

### 8.3 Walk-Forward Enhancement: Expanding + Rolling Hybrid

**Jansen recommends this hybrid for assets with regime changes:**

```python
class HybridWalkForwardSplitter:
    """
    Hybrid approach: expanding window until max size, then rolling.

    Rationale:
    - Early folds benefit from more training data (expanding)
    - Later folds avoid using stale data from years ago (rolling cap)
    """
    def __init__(
        self,
        min_train_window: int = 252,
        max_train_window: int = 756,  # 3 years cap
        val_window: int = 63,
        test_window: int = 21,
        step_size: int = 21,
        purge_gap: int = 5,
        embargo: int = 2,
    ):
        self.min_train_window = min_train_window
        self.max_train_window = max_train_window
        self.val_window = val_window
        self.test_window = test_window
        self.step_size = step_size
        self.purge_gap = purge_gap
        self.embargo = embargo

    def split(self, n_samples):
        fold_index = 0
        train_start = 0
        val_start_pos = self.min_train_window + self.purge_gap

        while True:
            # Expanding: start from 0 until max window reached
            # Then rolling: slide train_start forward
            if val_start_pos - train_start > self.max_train_window:
                train_start = val_start_pos - self.max_train_window

            train_end = val_start_pos - self.purge_gap
            val_end = val_start_pos + self.val_window
            test_start = val_end + self.embargo
            test_end = test_start + self.test_window

            if test_end > n_samples:
                break

            yield WalkForwardSplit(
                fold_index=fold_index,
                train_start=train_start,
                train_end=train_end,
                val_start=val_start_pos,
                val_end=val_end,
                test_start=test_start,
                test_end=test_end,
            )

            fold_index += 1
            val_start_pos += self.step_size
```

### 8.4 AlgoTrader Walk-Forward Status

The current `WalkForwardSplitter` implements rolling window with purge+embargo,
which is correct and follows Jansen's primary recommendation. Potential
improvements:

1. **Add expanding/hybrid mode** as an option (parameter `mode: "rolling" | "expanding" | "hybrid"`)
2. **Add combinatorial purged CV** for hyperparameter tuning (Optuna integration)
3. **Current window sizes are appropriate** (252/63/21 for daily; already scaled for hourly)

---

## 9. Portfolio-Level Risk Management Integrated with ML Signals

### 9.1 Jansen's Portfolio-ML Integration (Chapters 5, 23)

Jansen describes how ML predictions feed into portfolio construction:

```python
class MLPortfolioManager:
    """
    Jansen's pattern: ML signals -> portfolio optimization.

    Key insight: Don't just trade signals independently per asset.
    Use the correlation structure and confidence levels to optimize
    the portfolio as a whole.
    """
    def __init__(
        self,
        assets: list[str],
        base_allocation: dict[str, float],
        max_total_risk: float = 0.10,  # 10% of equity
        max_per_asset_risk: float = 0.05,
        max_correlation_penalty: float = 0.5,
    ):
        self.assets = assets
        self.base_allocation = base_allocation
        self.max_total_risk = max_total_risk
        self.max_per_asset_risk = max_per_asset_risk
        self.max_correlation_penalty = max_correlation_penalty

    def optimize_positions(
        self,
        signals: dict[str, PredictionResult],
        current_positions: dict[str, float],
        rolling_correlations: np.ndarray,
        account_equity: float,
    ) -> dict[str, float]:
        """
        Optimize position sizes considering:
        1. ML signal confidence
        2. Portfolio correlation
        3. Current drawdown state
        4. Volatility regime
        """
        target_positions = {}

        for asset in self.assets:
            signal = signals.get(asset)
            if signal is None or signal.confidence < 0.65:
                target_positions[asset] = 0.0
                continue

            # Base size from allocation
            base_size = self.base_allocation[asset] * account_equity

            # Confidence scaling (0.65 -> 0.5x, 0.80 -> 1.0x, 0.95 -> 1.5x)
            conf_scale = max(0.5, min(1.5, (signal.confidence - 0.5) * 3.33))

            # Correlation penalty
            corr_penalty = 1.0
            for other_asset in self.assets:
                if other_asset == asset:
                    continue
                other_signal = signals.get(other_asset)
                if other_signal and other_signal.signal_class == signal.signal_class:
                    # Same direction signals = correlated exposure
                    pair_corr = self._get_correlation(
                        asset, other_asset, rolling_correlations
                    )
                    if pair_corr > 0.5:
                        corr_penalty *= (1 - self.max_correlation_penalty * pair_corr)

            target_positions[asset] = base_size * conf_scale * corr_penalty

        # Normalize to respect max total risk
        total_risk = sum(abs(v) for v in target_positions.values())
        max_risk_amount = account_equity * self.max_total_risk
        if total_risk > max_risk_amount:
            scale = max_risk_amount / total_risk
            target_positions = {k: v * scale for k, v in target_positions.items()}

        return target_positions
```

### 9.2 Signal Calibration and Kelly Criterion

**Jansen recommends using calibrated probabilities for position sizing:**

```python
from sklearn.calibration import CalibratedClassifierCV

def calibrate_model(model, X_cal, y_cal, method="isotonic"):
    """
    Calibrate model probabilities.

    Raw softmax outputs are NOT calibrated (70% confidence != 70% accuracy).
    Isotonic regression maps raw probabilities to empirical frequencies.
    """
    calibrated = CalibratedClassifierCV(
        estimator=model,
        method=method,  # "isotonic" or "sigmoid" (Platt scaling)
        cv="prefit",     # Model already trained
    )
    calibrated.fit(X_cal, y_cal)
    return calibrated

# Kelly criterion for optimal bet sizing
def kelly_position_size(
    win_probability: float,  # Must be CALIBRATED probability
    win_loss_ratio: float,   # Average win / average loss
    fraction: float = 0.25,  # Use fractional Kelly (safer)
) -> float:
    """
    Kelly criterion: f* = (p * b - q) / b
    where p = win probability, q = 1-p, b = win/loss ratio

    Fractional Kelly (25%) is standard for trading:
    - Full Kelly is too aggressive (huge drawdowns)
    - Quarter Kelly provides ~75% of growth with ~25% of variance
    """
    q = 1 - win_probability
    kelly = (win_probability * win_loss_ratio - q) / win_loss_ratio
    return max(0, kelly * fraction)
```

### 9.3 Drawdown-Adaptive Sizing (ML-HFT pattern)

```python
class DrawdownAdaptiveSizer:
    """
    Reduce position sizes as drawdown increases.
    Prevents catastrophic losses during losing streaks.
    """
    def __init__(
        self,
        drawdown_tiers: list[tuple[float, float]] = None,
    ):
        # (drawdown_threshold, size_multiplier)
        self.tiers = drawdown_tiers or [
            (0.00, 1.00),   # No drawdown: full size
            (0.03, 0.75),   # 3% drawdown: 75% size
            (0.05, 0.50),   # 5% drawdown: 50% size
            (0.08, 0.25),   # 8% drawdown: 25% size
            (0.10, 0.10),   # 10% drawdown: 10% size
            (0.15, 0.00),   # 15% drawdown: STOP TRADING
        ]

    def get_size_multiplier(self, current_drawdown: float) -> float:
        """Get position size multiplier based on current drawdown."""
        for threshold, multiplier in reversed(self.tiers):
            if current_drawdown >= threshold:
                return multiplier
        return 1.0
```

---

## 10. Specific Recommendations for AlgoTrader AI

### 10.1 Immediate Improvements (Low Effort, High Impact)

These changes require minimal code modifications:

**1. XGBoost hyperparameter update** -- modify `xgboost_model.py`:
```python
# Current defaults -> Recommended defaults
max_depth: 6 -> 4
learning_rate: 0.1 -> 0.05
n_estimators: 500 -> 1000
min_child_weight: 5 -> 10
subsample: 0.8 -> 0.7
colsample_bytree: 0.8 -> 0.7
# Add new params:
gamma: 0.1
colsample_bylevel: 0.7
```

**2. Add lagged features** -- new function in `technical.py` or `builder.py`:
- Lag `returns_1`, `rsi_14`, `macd_histogram`, `volume_sma_ratio`, `atr_ratio`, `bb_pctb`
- Lags: [1, 2, 3, 5, 10]
- Expected F1 improvement: +0.05-0.10 for XGBoost

**3. Add time features** -- cyclical encoding of hour, day-of-week, month

**4. Add EMA spreads** -- `(ema_N - close) / close` instead of raw EMA values

### 10.2 Medium-Term Improvements (Moderate Effort)

**5. Implement LSTMClassifier** extending `BaseMLModel`:
- 2-layer LSTM, hidden_size=128, dropout=0.3
- Sequence length=60, gradient clipping=1.0
- Adapt `ModelTrainer` to handle 3D sequences

**6. Implement TFTClassifier** extending `BaseMLModel`:
- Either custom (as in Section 2.2) or via `pytorch-forecasting`
- hidden_size=64, 4 attention heads, dropout=0.1

**7. Implement ensemble stacking**:
- Out-of-fold prediction generation during walk-forward
- XGBoost meta-learner trained on base model probabilities
- Add model agreement and max-confidence as meta-features

**8. Add Optuna hyperparameter optimization**:
- Integrate into `ModelTrainer`
- 50-100 trials per asset per model type
- Use walk-forward validation loss as objective

### 10.3 Long-Term Architecture Improvements

**9. Implement hierarchical classification** (3-class direction + 2-class magnitude)

**10. Add probability calibration** (isotonic regression on validation predictions)

**11. Implement hybrid walk-forward** (expanding -> rolling at max window)

**12. Add rank-based normalization** as alternative to z-score

### 10.4 Expected Performance Improvements

| Change | Expected F1 Improvement | Confidence |
|--------|------------------------|------------|
| XGBoost hyperparameter tuning | +0.03-0.08 | High |
| Add lagged features | +0.05-0.10 | High |
| Add time features | +0.02-0.05 | Medium |
| Add EMA spreads (stationarity) | +0.02-0.04 | Medium |
| Switch to 3-class direction | +0.05-0.15 | High |
| Add LSTM base model | +0.02-0.05 (ensemble) | Medium |
| Add TFT base model | +0.02-0.05 (ensemble) | Medium |
| Ensemble stacking | +0.03-0.08 | Medium-High |
| Optuna tuning | +0.03-0.06 | Medium |
| **Cumulative (realistic)** | **0.35-0.50 total F1** | Medium |

The current baseline F1 of 0.20-0.24 should be improvable to 0.35-0.50 range
with these changes. Note that F1 > 0.50 on 5-class financial prediction is
considered excellent; most academic papers report 0.30-0.45.

---

## 11. Code Integration Checklist

### Files to Modify

| File | Changes |
|------|---------|
| `backend/src/models/xgboost_model.py` | Update default hyperparameters |
| `backend/src/features/technical.py` | Add lagged features, time features, EMA spreads |
| `backend/src/features/builder.py` | Wire new feature types into pipeline |
| `backend/src/features/normalizer.py` | Add rank normalization option |
| `backend/src/models/base_model.py` | Add `requires_sequences` property for LSTM/TFT |
| `backend/src/models/trainer.py` | Handle 3D input for sequential models |
| `backend/src/models/walk_forward.py` | Add expanding/hybrid modes |
| `backend/src/models/target_builder.py` | Add 3-class hierarchical target option |
| `backend/src/models/schemas.py` | Add ensemble-related schemas |
| `backend/src/models/prediction_service.py` | Support ensemble inference |

### New Files to Create

| File | Purpose |
|------|---------|
| `backend/src/models/lstm_model.py` | LSTM classifier (PyTorch) |
| `backend/src/models/tft_model.py` | TFT classifier (PyTorch) |
| `backend/src/models/ensemble.py` | Ensemble stacking meta-learner |
| `backend/src/models/calibrator.py` | Probability calibration utilities |
| `backend/src/models/hyperopt.py` | Optuna integration for hyperparameter search |
| `backend/src/features/lagged.py` | Lagged feature builder |
| `backend/src/features/temporal.py` | Time/cyclical feature builder |
| `backend/src/features/microstructure.py` | Microstructure-inspired features |
