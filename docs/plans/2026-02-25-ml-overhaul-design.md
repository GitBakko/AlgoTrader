# ML Trading System Overhaul — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 27% win rate by implementing 3-level overhaul: trend filters, model improvements, and strategy architecture changes. Target: >35% WR with positive Kelly fraction.

**Architecture:** Three phases executed sequentially. Phase A (pre-trade filters) deploys immediately without retraining. Phase B (model improvements) requires retraining all 20 models. Phase C (strategy overhaul) adds trend-following as primary strategy with ML confirmation.

**Tech Stack:** Python 3.12, XGBoost, Polars, FastAPI, Optuna, pytest

**Root Causes (ranked by impact):**
1. Purge gap (5) < prediction horizon (6) → data leakage in training
2. 205+ features for 3 classes → overfitting
3. No trend filter → trades against macro direction
4. Confidence threshold 0.40 → too low (random baseline = 0.333)
5. All 20 assets always active → no quality filtering
6. XGBoost too complex (max_depth=6, weak regularization)
7. R:R ratio 1.5:1 → needs 40% WR to break even

---

## Phase A: Pre-Trade Filters (No Retrain Needed)

### Task A1: Trend Filter in SignalGenerator

**Files:**
- Modify: `backend/src/strategy/signal_generator.py`
- Modify: `backend/src/strategy/schemas.py`
- Test: `backend/tests/strategy/test_signal_generator.py`

**Step 1: Add SMA trend filter fields to StrategyConfig**

In `backend/src/strategy/schemas.py`, add to `StrategyConfig` (after line 52):
```python
    # Trend filter (Phase A1)
    trend_sma_penalty: float = Field(default=0.70, ge=0.0, le=1.0)
    trend_ema_slope_min: float = Field(default=0.02, ge=0.0, le=0.5)
    trend_ema_slope_penalty: float = Field(default=0.80, ge=0.0, le=1.0)
```

**Step 2: Add sma_50 and ema_slope params to generate_signal**

In `backend/src/strategy/signal_generator.py`, update `generate_signal` signature (line 39):
```python
    @staticmethod
    def generate_signal(
        prediction: PredictionResult,
        epic: str,
        current_price: float,
        atr: float,
        rsi: float | None = None,
        regime: str | None = None,
        config: StrategyConfig | None = None,
        adx: float | None = None,
        sma_50: float | None = None,
        ema_slope: float | None = None,
    ) -> TradingSignal:
```

**Step 3: Add trend filter logic after direction mapping (after line 93)**

Insert after `# 2. Map SignalClass to direction` block:
```python
        # 2.1. SMA trend filter — penalize counter-trend relative to SMA(50)
        if sma_50 is not None and sma_50 > 0:
            if direction == SignalDirection.BUY and current_price < sma_50 * 0.995:
                original = confidence
                confidence *= cfg.trend_sma_penalty
                logger.debug(
                    f"{epic}: SMA trend penalty (BUY below SMA50): "
                    f"{original:.2f} -> {confidence:.2f}"
                )
            elif direction == SignalDirection.SELL and current_price > sma_50 * 1.005:
                original = confidence
                confidence *= cfg.trend_sma_penalty
                logger.debug(
                    f"{epic}: SMA trend penalty (SELL above SMA50): "
                    f"{original:.2f} -> {confidence:.2f}"
                )

        # 2.2. EMA slope filter — penalize signals when trend is flat
        if ema_slope is not None and atr > 0:
            normalized_slope = abs(ema_slope) / atr
            if normalized_slope < cfg.trend_ema_slope_min:
                original = confidence
                confidence *= cfg.trend_ema_slope_penalty
                logger.debug(
                    f"{epic}: EMA slope penalty (flat trend, slope/ATR={normalized_slope:.3f}): "
                    f"{original:.2f} -> {confidence:.2f}"
                )

        # 2.3. Re-check confidence after trend filters
        if confidence < cfg.min_confidence:
            logger.debug(
                f"{epic}: Confidence {confidence:.2f} below threshold "
                f"after trend filters -> HOLD"
            )
            return _make_hold_signal(epic, current_price, regime)
```

**Step 4: Update PredictionService to pass SMA/EMA data**

In `backend/src/models/prediction_service.py`, in the `predict()` method where market data is cached, extract `sma_50` and `ema_slope` and return them in the `PredictionResult` or as separate fields in the cached market data dict. The paper_loop already has access to the market data dict from PredictionService — ensure `sma_50` and `ema_21` values are included.

**Step 5: Update paper_loop to pass SMA/EMA to SignalGenerator**

In `backend/src/trading/paper_loop.py`, in `_process_epic()` where `SignalGenerator.generate_signal()` is called, add the new params:
```python
signal = SignalGenerator.generate_signal(
    prediction=prediction,
    epic=epic,
    current_price=price,
    atr=atr,
    rsi=rsi,
    regime=regime,
    config=config,
    adx=adx,
    sma_50=market_data.get("sma_50"),
    ema_slope=market_data.get("ema_slope"),
)
```

**Step 6: Write tests**

```python
# tests/strategy/test_signal_generator_trend_filter.py

def test_buy_below_sma50_penalized():
    """BUY signal below SMA50 gets confidence penalty."""
    pred = PredictionResult(signal_class=SignalClass.BUY, confidence=0.65, probabilities=[0.1, 0.25, 0.65])
    signal = SignalGenerator.generate_signal(
        prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
        sma_50=105.0,  # price well below SMA50
    )
    # 0.65 * 0.70 = 0.455, still above 0.40 min
    assert signal.confidence < 0.65
    assert signal.direction == SignalDirection.BUY

def test_sell_above_sma50_penalized():
    """SELL signal above SMA50 gets confidence penalty."""
    pred = PredictionResult(signal_class=SignalClass.SELL, confidence=0.55, probabilities=[0.55, 0.25, 0.2])
    signal = SignalGenerator.generate_signal(
        prediction=pred, epic="XAUUSD", current_price=110.0, atr=2.0,
        sma_50=105.0,  # price well above SMA50
    )
    # 0.55 * 0.70 = 0.385, below 0.40 → HOLD
    assert signal.direction == SignalDirection.HOLD

def test_flat_ema_slope_penalized():
    """Signal with flat EMA slope gets penalty."""
    pred = PredictionResult(signal_class=SignalClass.BUY, confidence=0.60, probabilities=[0.1, 0.3, 0.6])
    signal = SignalGenerator.generate_signal(
        prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
        ema_slope=0.01,  # tiny slope, 0.01/2.0 = 0.005 < 0.02 threshold
    )
    assert signal.confidence < 0.60

def test_no_penalty_when_sma_agrees():
    """BUY above SMA50 gets no penalty."""
    pred = PredictionResult(signal_class=SignalClass.BUY, confidence=0.65, probabilities=[0.1, 0.25, 0.65])
    signal = SignalGenerator.generate_signal(
        prediction=pred, epic="XAUUSD", current_price=110.0, atr=2.0,
        sma_50=105.0,  # price above SMA50, aligned with BUY
    )
    assert signal.confidence == 0.65  # No penalty
```

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_signal_generator_trend_filter.py -v`

**Commit:** `feat: add SMA/EMA trend filters to signal generator`

---

### Task A2: Raise Confidence Threshold + Confidence Tiering

**Files:**
- Modify: `backend/src/strategy/schemas.py` (line 44)
- Modify: `backend/src/strategy/regime_adapter.py` (lines 10-26)
- Modify: `backend/src/risk/risk_manager.py`
- Test: `backend/tests/strategy/test_confidence_tiering.py`

**Step 1: Raise min_confidence default**

In `backend/src/strategy/schemas.py` line 44:
```python
    min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)  # was 0.40
```

**Step 2: Update regime adapter thresholds**

In `backend/src/strategy/regime_adapter.py` lines 10-26:
```python
_REGIME_PARAMS: dict[str, dict[str, float]] = {
    "trending_up": {
        "min_confidence": 0.48,     # was 0.40
        "stop_multiplier": 2.5,     # was 3.5
        "counter_trend_penalty": 0.5,  # was 0.4 (less harsh)
    },
    "trending_down": {
        "min_confidence": 0.50,     # was 0.45
        "stop_multiplier": 2.0,     # was 2.5
        "counter_trend_penalty": 0.4,  # was 0.3 (less harsh)
    },
    "ranging": {
        "min_confidence": 0.52,     # was 0.45
        "stop_multiplier": 2.0,     # was 2.5
        "counter_trend_penalty": 0.7,  # unchanged
    },
}
```

**Step 3: Add confidence-based position size scaling**

In `backend/src/risk/risk_manager.py`, add a static method and use it in position sizing (after Kelly/fixed-fractional sizing, before equity curve filter):

```python
@staticmethod
def confidence_size_multiplier(confidence: float) -> float:
    """Scale position size by confidence tier.

    < 0.50: 0.0 (rejected by min_confidence)
    0.50-0.58: 0.50x
    0.58-0.65: 0.75x
    >= 0.65: 1.0x
    """
    if confidence < 0.50:
        return 0.0
    elif confidence < 0.58:
        return 0.50
    elif confidence < 0.65:
        return 0.75
    return 1.0
```

Apply it in `check_trade()` after position sizing:
```python
# Confidence tiering
conf_mult = self.confidence_size_multiplier(signal.confidence)
if conf_mult < 1.0:
    adjustments.append(f"Confidence tier: {conf_mult:.0%} (conf={signal.confidence:.2f})")
    size *= conf_mult
```

**Step 4: Write tests**

```python
# tests/strategy/test_confidence_tiering.py

def test_confidence_below_050_rejected():
    """Signals below 0.50 confidence are HOLD."""
    pred = PredictionResult(signal_class=SignalClass.BUY, confidence=0.45, probabilities=[0.1, 0.45, 0.45])
    signal = SignalGenerator.generate_signal(
        prediction=pred, epic="XAUUSD", current_price=100.0, atr=2.0,
    )
    assert signal.direction == SignalDirection.HOLD

def test_confidence_tier_050_gets_half_size():
    from src.risk.risk_manager import RiskManager
    assert RiskManager.confidence_size_multiplier(0.52) == 0.50

def test_confidence_tier_058_gets_75pct():
    from src.risk.risk_manager import RiskManager
    assert RiskManager.confidence_size_multiplier(0.60) == 0.75

def test_confidence_tier_065_gets_full():
    from src.risk.risk_manager import RiskManager
    assert RiskManager.confidence_size_multiplier(0.68) == 1.0
```

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_confidence_tiering.py -v`

**Commit:** `feat: raise confidence threshold to 0.50 + add confidence-based size tiering`

---

### Task A3: Fix SL/TP Ratio

**Files:**
- Modify: `backend/src/risk/risk_manager.py` (lines 161, 193)
- Modify: `backend/src/strategy/schemas.py` (lines 48-49)
- Test: existing tests should pass (verify with full suite)

**Step 1: Update defaults in schemas.py**

```python
    stop_multiplier: float = Field(default=2.0, ge=0.5, le=5.0)     # was 3.0
    risk_reward_ratio: float = Field(default=2.5, ge=0.5, le=5.0)   # was 1.5
```

**Step 2: Update risk_manager.py base_multiplier**

Line 161: Change `base_multiplier=3.0` → `base_multiplier=2.0`
Line 193: Change `risk_reward=1.5` → `risk_reward=2.5`

**Step 3: Update dynamic_multiplier clamp range**

In `backend/src/risk/stop_manager.py`, change `min_multiplier` default from 2.0 to 1.5:
```python
def dynamic_multiplier(
    base_multiplier: float = 2.0,    # was 3.0
    ...
    min_multiplier: float = 1.5,     # was 2.0
    max_multiplier: float = 4.0,     # was 5.0
) -> float:
```

**Step 4: Verify all existing tests still pass**

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q`

**Commit:** `feat: tighten SL to 2 ATR, widen TP to 2.5x R:R`

---

### Task A4: Raise ADX Thresholds

**Files:**
- Modify: `backend/src/strategy/schemas.py` (lines 50-51)

**Step 1: Update ADX defaults**

```python
    adx_trending_threshold: float = Field(default=28.0, ge=10.0, le=50.0)  # was 25.0
    adx_ranging_threshold: float = Field(default=20.0, ge=5.0, le=40.0)    # was 15.0
    adx_confidence_boost: float = Field(default=0.08, ge=0.0, le=0.15)     # was 0.05
```

**Step 2: Verify tests pass**

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q`

**Commit:** `feat: raise ADX thresholds (ranging 15→20, trending 25→28)`

---

### Task A5: Asset Momentum Rotation

**Files:**
- Create: `backend/src/trading/asset_rotation.py`
- Modify: `backend/src/trading/paper_loop.py`
- Test: `backend/tests/trading/test_asset_rotation.py`

**Step 1: Create asset rotation module**

```python
# backend/src/trading/asset_rotation.py
"""
Asset momentum rotation.
Selects tradeable assets based on rolling momentum score.
Only assets with positive momentum and in the top 50% are traded.
"""

import polars as pl
from loguru import logger

from src.data.data_access import DataAccessLayer
from src.utils.constants import TRADABLE_ASSETS


def compute_momentum_scores(
    data_access: DataAccessLayer,
    lookback_days: int = 63,
    skip_recent_days: int = 5,
) -> dict[str, float]:
    """
    Compute risk-adjusted momentum for each tradeable asset.

    Uses (lookback - skip_recent) days of returns, skipping the most recent
    days to avoid short-term reversal effect.

    Returns: dict of {epic: momentum_score}
    """
    scores = {}
    for epic in TRADABLE_ASSETS:
        try:
            df = data_access.get_candles(epic, "1d", limit=lookback_days + skip_recent_days + 5)
            if df.is_empty() or len(df) < 20:
                continue

            # Calculate daily returns
            df = df.sort("timestamp")
            df = df.with_columns(
                (pl.col("close") / pl.col("close").shift(1) - 1).alias("return")
            ).drop_nulls("return")

            returns = df["return"].to_list()

            if len(returns) < 20:
                continue

            # Skip most recent days (reversal effect), use prior lookback days
            if len(returns) > skip_recent_days:
                momentum_window = returns[:-skip_recent_days] if skip_recent_days > 0 else returns
                momentum_window = momentum_window[-lookback_days:]
            else:
                momentum_window = returns

            if not momentum_window:
                continue

            # Momentum = cumulative return
            cum_return = 1.0
            for r in momentum_window:
                cum_return *= (1 + r)
            momentum = cum_return - 1.0

            # Volatility for risk-adjustment
            import math
            vol = (sum((r - sum(momentum_window)/len(momentum_window))**2 for r in momentum_window) / len(momentum_window)) ** 0.5

            # Risk-adjusted momentum
            scores[epic] = momentum / max(vol, 1e-8)

        except Exception as e:
            logger.warning(f"Momentum calc failed for {epic}: {e}")

    return scores


def select_active_assets(
    momentum_scores: dict[str, float],
    top_pct: float = 0.5,
    min_assets: int = 8,
) -> list[str]:
    """
    Select top assets by risk-adjusted momentum.
    Only includes assets with positive momentum.

    Returns: list of epics to trade
    """
    # Filter: only positive momentum
    positive = {k: v for k, v in momentum_scores.items() if v > 0}

    # Rank by score descending
    ranked = sorted(positive.items(), key=lambda x: x[1], reverse=True)

    # Take top N%
    n_select = max(min_assets, int(len(TRADABLE_ASSETS) * top_pct))
    selected = [epic for epic, _ in ranked[:n_select]]

    # If fewer than min_assets have positive momentum, include top by absolute score
    if len(selected) < min_assets:
        all_ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        for epic, _ in all_ranked:
            if epic not in selected:
                selected.append(epic)
            if len(selected) >= min_assets:
                break

    return selected
```

**Step 2: Integrate into PaperTradingLoop**

In `paper_loop.py`, add to `__init__`:
```python
self._active_assets: set[str] | None = None  # None = all assets
self._asset_rotation_ts: float = 0.0
self._per_asset_losses: dict[str, int] = {}  # consecutive loss counter per asset
```

Add method:
```python
def _refresh_active_assets(self) -> None:
    """Refresh asset rotation weekly."""
    import time
    now = time.monotonic()
    if self._active_assets is not None and (now - self._asset_rotation_ts) < 7 * 24 * 3600:
        return  # Refresh weekly

    try:
        from src.trading.asset_rotation import compute_momentum_scores, select_active_assets
        from src.data.storage import ParquetStorageManager
        from src.data.data_access import DataAccessLayer

        storage = ParquetStorageManager()
        data_access = DataAccessLayer(storage=storage)
        scores = compute_momentum_scores(data_access)

        if scores:
            selected = select_active_assets(scores)
            self._active_assets = set(selected)
            self._asset_rotation_ts = now
            logger.info(f"Asset rotation: {len(selected)} active assets: {selected}")
        else:
            self._active_assets = None  # Fallback to all
    except Exception as e:
        logger.warning(f"Asset rotation failed: {e}")
        self._active_assets = None
```

In `_process_epic()`, add early return:
```python
# Asset rotation check
if self._active_assets is not None and epic not in self._active_assets:
    return  # Skip non-active assets

# Per-asset circuit breaker (5 consecutive losses)
if self._per_asset_losses.get(epic, 0) >= 5:
    logger.debug(f"[{epic}] Per-asset CB: 5 consecutive losses, skipping")
    return
```

Update trade result tracking to count per-asset losses:
```python
# After a trade closes (in broker-closed detection or _update_trailing_stops):
def _record_per_asset_result(self, epic: str, is_win: bool) -> None:
    if is_win:
        self._per_asset_losses[epic] = 0
    else:
        self._per_asset_losses[epic] = self._per_asset_losses.get(epic, 0) + 1
```

Add to `get_status()`:
```python
"active_assets": len(self._active_assets) if self._active_assets else len(self._epics),
"per_asset_losses": {k: v for k, v in self._per_asset_losses.items() if v > 0},
```

**Step 3: Call rotation at loop start**

In the main `run()` method, add before the epic iteration loop:
```python
self._refresh_active_assets()
```

**Step 4: Write tests**

```python
# tests/trading/test_asset_rotation.py

def test_compute_momentum_positive():
    """Assets with uptrend have positive momentum."""
    scores = {"XAUUSD": 0.15, "BTCUSD": -0.05, "US500": 0.08}
    selected = select_active_assets(scores, top_pct=0.5, min_assets=1)
    assert "XAUUSD" in selected
    assert "BTCUSD" not in selected  # negative momentum

def test_min_assets_enforced():
    """At least min_assets are selected even if few have positive momentum."""
    scores = {"XAUUSD": 0.01, "BTCUSD": -0.05, "US500": -0.02}
    selected = select_active_assets(scores, top_pct=0.5, min_assets=2)
    assert len(selected) >= 2

def test_per_asset_circuit_breaker():
    """After 5 consecutive losses, asset is skipped."""
    losses = {"NATGAS": 5, "XAUUSD": 2}
    assert losses.get("NATGAS", 0) >= 5  # Should skip
    assert losses.get("XAUUSD", 0) < 5   # Should trade
```

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_asset_rotation.py -v`

**Commit:** `feat: add asset momentum rotation + per-asset circuit breaker`

---

### Task A6: Phase A Integration Test + Deploy

**Run full test suite:**
```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q
```

**Commit all Phase A:** `feat: Phase A — pre-trade filters (trend, confidence, SL/TP, ADX, asset rotation)`

---

## Phase B: Model Improvements (Retrain Required)

### Task B1: Fix Data Leakage (Purge Gap + Embargo)

**Files:**
- Modify: `backend/src/models/walk_forward.py` (lines 63-64)
- Modify: `backend/src/models/auto_retrain.py` (line 66)
- Test: `backend/tests/models/test_walk_forward.py`

**Step 1: Make purge_gap and embargo scale with horizon**

In `backend/src/models/auto_retrain.py`, update `_get_splitter()`:
```python
def _get_splitter(timeframe: str, epic: str, horizon_bars: int = 12) -> WalkForwardSplitter:
    """Create walk-forward splitter scaled to timeframe, asset type, and prediction horizon."""
    ...
    return WalkForwardSplitter(
        train_window=252 * scale,
        val_window=63 * scale,
        test_window=21 * scale,
        step_size=21 * scale,
        purge_gap=max(5 * scale, 2 * horizon_bars),   # At least 2x horizon
        embargo=max(2 * scale, horizon_bars),           # At least 1x horizon
    )
```

In `backend/scripts/train_models.py`, update the same pattern where splitter is created.

**Step 2: Write test**

```python
def test_purge_gap_exceeds_horizon():
    """Purge gap must be at least 2x prediction horizon."""
    horizon = 12
    splitter = _get_splitter("1h", "XAUUSD", horizon_bars=horizon)
    assert splitter.purge_gap >= 2 * horizon
    assert splitter.embargo >= horizon
```

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/models/test_walk_forward.py -v`

**Commit:** `fix: purge gap 2x prediction horizon to prevent data leakage`

---

### Task B2: Conservative XGBoost Defaults

**Files:**
- Modify: `backend/src/models/xgboost_model.py` (lines 26-34)
- Modify: `backend/src/models/auto_retrain.py` (lines 84-92)
- Modify: `backend/src/models/tuner.py` (lines 18-27, 31)

**Step 1: Update XGBoost defaults**

In `backend/src/models/xgboost_model.py`:
```python
    max_depth: int = 4,              # was 6
    learning_rate: float = 0.05,     # was 0.1
    n_estimators: int = 1000,        # was 500
    subsample: float = 0.7,          # was 0.8
    colsample_bytree: float = 0.6,   # was 0.8
    min_child_weight: int = 20,      # was 5
    reg_alpha: float = 1.0,          # was 0.1
    reg_lambda: float = 5.0,         # was 1.0
    early_stopping_rounds: int = 50,
    gamma: float = 0.5,              # NEW — minimum split loss reduction
```

**Step 2: Update auto_retrain defaults**

In `backend/src/models/auto_retrain.py` (lines 84-92), match the new defaults:
```python
        model = XGBoostClassifier(
            max_depth=4,
            learning_rate=0.05,
            n_estimators=1000,
            subsample=0.7,
            colsample_bytree=0.6,
            min_child_weight=20,
            early_stopping_rounds=50,
        )
```

**Step 3: Update Optuna search space**

In `backend/src/models/tuner.py`:
```python
PARAM_SPACE = {
    "max_depth": (3, 5),                # was (3, 8) — shallower
    "learning_rate": (0.01, 0.1),       # was (0.01, 0.3) — slower
    "n_estimators": (500, 1500),        # was (100, 800) — more trees at lower LR
    "subsample": (0.5, 0.8),            # was (0.6, 1.0)
    "colsample_bytree": (0.4, 0.7),     # was (0.5, 1.0) — more aggressive subsampling
    "min_child_weight": (10, 50),       # was (1, 20) — larger leaves
    "reg_alpha": (0.5, 10.0),           # was (1e-3, 10.0) — more L1
    "reg_lambda": (3.0, 15.0),          # was (1e-3, 10.0) — more L2
    "gamma": (0.1, 2.0),               # NEW — minimum split loss
}
```

Also update n_trials default (line 31):
```python
    n_trials: int = 80,  # was 40
```

**Step 4: Verify tests pass**

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q`

**Commit:** `feat: conservative XGBoost defaults (depth 4, heavy regularization, gamma)`

---

### Task B3: Target Builder — Longer Horizon + Higher Threshold

**Files:**
- Modify: `backend/src/models/target_builder.py` (lines 23, 25)
- Modify: `backend/src/models/auto_retrain.py` (line 54)
- Modify: `backend/scripts/train_models.py`

**Step 1: Update defaults**

In `target_builder.py`:
```python
    horizon_bars: int = 12,    # was 6 — predict 12 hours ahead
    threshold: float = 0.75,   # was 0.5 — more selective targets
```

In `auto_retrain.py`, update default:
```python
def _train_single_asset(
    epic: str,
    timeframe: str = "1h",
    horizon_bars: int = 12,    # was 6
) -> tuple[str, bool, str]:
```

Also update `retrain_all_models()`:
```python
async def retrain_all_models(
    prediction_service=None,
    timeframe: str = "1h",
    horizon_bars: int = 12,    # was 6
) -> dict[str, bool]:
```

**Step 2: Verify tests pass**

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q`

**Commit:** `feat: increase prediction horizon to 12 bars, threshold to 0.75 ATR`

---

### Task B4: Feature Reduction (Post-Train SHAP Analysis)

**Files:**
- Create: `backend/src/models/feature_selector.py`
- Modify: `backend/src/models/trainer.py`
- Test: `backend/tests/models/test_feature_selector.py`

**Step 1: Create feature selector**

```python
# backend/src/models/feature_selector.py
"""
Feature importance analysis and selection.
Keeps only top N features by XGBoost gain importance.
"""

from loguru import logger


def select_top_features(
    model,
    feature_names: list[str],
    max_features: int = 80,
) -> list[str]:
    """
    Select top features by XGBoost gain importance.

    Args:
        model: Trained XGBoostClassifier
        feature_names: All feature column names
        max_features: Maximum features to keep

    Returns:
        List of top feature names
    """
    importance = model.feature_importance()
    if not importance:
        logger.warning("No feature importance available, keeping all features")
        return feature_names

    # Sort by importance descending
    sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)

    # Keep top N
    selected = [name for name, _ in sorted_features[:max_features]]

    # Log dropped features
    dropped = len(feature_names) - len(selected)
    if dropped > 0:
        logger.info(
            f"Feature selection: kept {len(selected)}/{len(feature_names)} features "
            f"(dropped {dropped} low-importance)"
        )
        # Log bottom 10 dropped
        bottom = sorted_features[max_features:max_features + 10]
        for name, imp in bottom:
            logger.debug(f"  Dropped: {name} (importance={imp:.6f})")

    return selected


# Features to always exclude (known problematic)
EXCLUDE_FEATURES = {
    # Regime one-hot: perfectly collinear (3 binary = 2 are redundant)
    "regime_trending_up",
    "regime_trending_down",
    "regime_ranging",
    # Z-score versions too
    "regime_trending_up_z",
    "regime_trending_down_z",
    "regime_ranging_z",
}
```

**Step 2: Integrate into trainer**

In `backend/src/models/trainer.py`, after the first fold trains, extract feature importance and filter columns for subsequent folds. Also exclude `EXCLUDE_FEATURES` before training.

In the feature column selection step (where z-score columns are selected), add:
```python
from src.models.feature_selector import EXCLUDE_FEATURES
feature_cols = [c for c in feature_cols if c not in EXCLUDE_FEATURES]
```

**Step 3: Write test**

```python
def test_select_top_features():
    from src.models.feature_selector import select_top_features

    class MockModel:
        def feature_importance(self):
            return {"rsi_14": 100, "macd_line": 80, "ema_8": 60, "noise_1": 1, "noise_2": 0}

    selected = select_top_features(MockModel(), ["rsi_14", "macd_line", "ema_8", "noise_1", "noise_2"], max_features=3)
    assert selected == ["rsi_14", "macd_line", "ema_8"]
    assert "noise_1" not in selected
```

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/models/test_feature_selector.py -v`

**Commit:** `feat: feature selection — keep top 80 by importance, exclude regime one-hot`

---

### Task B5: Phase B Integration Test + Retrain

**Run full test suite:**
```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q
```

**Commit:** `feat: Phase B — model improvements (leakage fix, conservative XGBoost, horizon 12, feature selection)`

**Retrain all models:**
```bash
cd backend && .venv/Scripts/python.exe scripts/train_models.py --tune --retune --horizon 12 --tune-trials 80
```

---

## Phase C: Strategy Overhaul

### Task C1: Regime Detection with Hysteresis

**Files:**
- Modify: `backend/src/features/regime.py`
- Test: `backend/tests/features/test_regime.py`

**Step 1: Add hysteresis to RegimeDetector**

Replace the classify logic in `regime.py` to require 3 consecutive bars:

```python
class RegimeDetector:
    def __init__(
        self,
        adx_threshold: float = 25.0,
        ema_period: int = 50,
        slope_lookback: int = 5,
        hysteresis_bars: int = 3,
    ):
        self.adx_threshold = adx_threshold
        self.ema_period = ema_period
        self.slope_lookback = slope_lookback
        self.hysteresis_bars = hysteresis_bars

    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        ema_col = f"ema_{self.ema_period}"
        if "adx" not in df.columns or ema_col not in df.columns:
            raise ValueError(...)

        # EMA slope
        df = df.with_columns(
            (pl.col(ema_col) - pl.col(ema_col).shift(self.slope_lookback)).alias("_ema_slope")
        )

        # Raw regime per bar
        df = df.with_columns(
            pl.when(
                (pl.col("adx") > self.adx_threshold) & (pl.col("_ema_slope") > 0)
            )
            .then(pl.lit(MarketRegime.TRENDING_UP.value))
            .when(
                (pl.col("adx") > self.adx_threshold) & (pl.col("_ema_slope") <= 0)
            )
            .then(pl.lit(MarketRegime.TRENDING_DOWN.value))
            .otherwise(pl.lit(MarketRegime.RANGING.value))
            .alias("_raw_regime")
        )

        # Hysteresis: require N consecutive bars for regime change
        if self.hysteresis_bars > 1:
            regimes = df["_raw_regime"].to_list()
            stable = [regimes[0]] if regimes else []
            current_regime = regimes[0] if regimes else MarketRegime.RANGING.value
            streak = 1
            candidate = current_regime

            for i in range(1, len(regimes)):
                if regimes[i] == candidate:
                    streak += 1
                else:
                    candidate = regimes[i]
                    streak = 1

                if streak >= self.hysteresis_bars:
                    current_regime = candidate

                stable.append(current_regime)

            df = df.with_columns(
                pl.Series("regime", stable)
            )
        else:
            df = df.rename({"_raw_regime": "regime"})

        df = df.drop(["_ema_slope"] + (["_raw_regime"] if "_raw_regime" in df.columns else []))
        return df
```

**Step 2: Write test**

```python
def test_regime_hysteresis_prevents_whipsaw():
    """Regime doesn't change on a single-bar flip."""
    # Create data where ADX flips for 1 bar then returns
    # ... (construct DataFrame with ADX=30 for 5 bars, then ADX=10 for 1 bar, then ADX=30 again)
    # The single ranging bar should NOT change the regime
    detector = RegimeDetector(hysteresis_bars=3)
    result = detector.detect(df)
    regimes = result["regime"].to_list()
    # The single dip should be smoothed out
    assert regimes[-1] == "trending_up"
```

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/features/test_regime.py -v`

**Commit:** `feat: regime detection with 3-bar hysteresis`

---

### Task C2: Trend-Following Strategy

**Files:**
- Create: `backend/src/strategy/trend_following_strategy.py`
- Modify: `backend/src/strategy/strategy_router.py`
- Test: `backend/tests/strategy/test_trend_following.py`

**Step 1: Create TrendFollowingStrategy**

```python
# backend/src/strategy/trend_following_strategy.py
"""
Trend-following strategy.
Entry on EMA crossover in direction of macro trend (SMA50).
ML model acts as confirmation filter (must agree with direction).
"""

from loguru import logger

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal


class TrendFollowingStrategy:
    """
    Trend-following with ML confirmation.

    Entry rules:
    1. Macro trend: Price above SMA(50) = bullish, below = bearish
    2. EMA crossover: EMA(8) crosses EMA(21) in trend direction
    3. ADX confirmation: ADX > 20 (trend has strength)
    4. ML confirmation: Model predicts same direction (BUY or SELL, not HOLD)

    All 4 must agree for a signal.
    """

    name = "trend_following"
    applicable_regimes = ["trending_up", "trending_down"]

    @staticmethod
    def generate_signal(
        current_bar: dict,
        config: StrategyConfig | None = None,
    ) -> TradingSignal:
        cfg = config or StrategyConfig()
        epic = current_bar.get("epic", "")
        price = current_bar.get("close", 0.0)

        sma_50 = current_bar.get("sma_50")
        ema_8 = current_bar.get("ema_8")
        ema_21 = current_bar.get("ema_21")
        ema_8_prev = current_bar.get("ema_8_prev")
        ema_21_prev = current_bar.get("ema_21_prev")
        adx = current_bar.get("adx")
        atr = current_bar.get("atr_14", 0.0)

        prediction: PredictionResult | None = current_bar.get("prediction")

        # Default HOLD
        hold = TradingSignal(
            epic=epic, direction=SignalDirection.HOLD, confidence=0.0,
            signal_class=SignalClass.HOLD, entry_price=price,
            strategy_name="trend_following",
        )

        # Need all data
        if any(v is None for v in [sma_50, ema_8, ema_21, ema_8_prev, ema_21_prev, adx]):
            return hold

        if atr <= 0:
            return hold

        # 1. Macro trend direction
        if price > sma_50:
            macro_direction = SignalDirection.BUY
        elif price < sma_50:
            macro_direction = SignalDirection.SELL
        else:
            return hold

        # 2. EMA crossover in trend direction
        ema_cross_up = ema_8_prev <= ema_21_prev and ema_8 > ema_21
        ema_cross_down = ema_8_prev >= ema_21_prev and ema_8 < ema_21

        if macro_direction == SignalDirection.BUY and not ema_cross_up:
            # Also accept already-crossed (ema_8 > ema_21) for continuation
            if ema_8 <= ema_21:
                return hold
        elif macro_direction == SignalDirection.SELL and not ema_cross_down:
            if ema_8 >= ema_21:
                return hold

        # 3. ADX confirmation (trend has strength)
        if adx < 20.0:
            return hold

        # 4. ML confirmation (must agree with direction)
        ml_confidence = 0.0
        if prediction is not None:
            ml_class = prediction.signal_class
            ml_confidence = prediction.confidence

            if macro_direction == SignalDirection.BUY and ml_class != SignalClass.BUY:
                return hold  # ML disagrees
            elif macro_direction == SignalDirection.SELL and ml_class != SignalClass.SELL:
                return hold  # ML disagrees
        else:
            return hold  # No ML prediction = no trade

        # All 4 agree — generate signal
        # Confidence = blend of ADX strength + ML confidence
        adx_factor = min(adx / 50.0, 1.0)  # 0-1 scale
        blended_confidence = 0.4 * adx_factor + 0.6 * ml_confidence

        logger.info(
            f"[{epic}] TREND signal: {macro_direction.value} "
            f"(ADX={adx:.1f}, ML_conf={ml_confidence:.2f}, blended={blended_confidence:.2f})"
        )

        return TradingSignal(
            epic=epic,
            direction=macro_direction,
            confidence=blended_confidence,
            signal_class=SignalClass.BUY if macro_direction == SignalDirection.BUY else SignalClass.SELL,
            entry_price=price,
            strategy_name="trend_following",
            technical_confirmation=True,
        )
```

**Step 2: Update StrategyRouter**

In `backend/src/strategy/strategy_router.py`, update `DEFAULT_REGIME_MAP`:
```python
DEFAULT_REGIME_MAP = {
    "trending_up": ["trend_following", "ml_ensemble"],
    "trending_down": ["trend_following", "ml_ensemble"],
    "ranging": ["squeeze_breakout", "vwap_reversion", "ml_ensemble"],
}
```

Register the new strategy in the router initialization.

**Step 3: Write tests**

```python
# tests/strategy/test_trend_following.py

def test_buy_signal_all_conditions_met():
    """BUY when price > SMA50, EMA8 crosses EMA21, ADX > 20, ML agrees."""
    bar = {
        "epic": "XAUUSD", "close": 110.0, "sma_50": 105.0,
        "ema_8": 109.0, "ema_21": 108.0, "ema_8_prev": 107.0, "ema_21_prev": 108.0,
        "adx": 30.0, "atr_14": 2.0,
        "prediction": PredictionResult(signal_class=SignalClass.BUY, confidence=0.65, probabilities=[0.1, 0.25, 0.65]),
    }
    signal = TrendFollowingStrategy.generate_signal(bar)
    assert signal.direction == SignalDirection.BUY
    assert signal.confidence > 0.5

def test_hold_when_ml_disagrees():
    """HOLD when macro says BUY but ML says SELL."""
    bar = {
        "epic": "XAUUSD", "close": 110.0, "sma_50": 105.0,
        "ema_8": 109.0, "ema_21": 108.0, "ema_8_prev": 107.0, "ema_21_prev": 108.0,
        "adx": 30.0, "atr_14": 2.0,
        "prediction": PredictionResult(signal_class=SignalClass.SELL, confidence=0.70, probabilities=[0.7, 0.2, 0.1]),
    }
    signal = TrendFollowingStrategy.generate_signal(bar)
    assert signal.direction == SignalDirection.HOLD

def test_hold_when_adx_low():
    """HOLD when ADX < 20 (no trend)."""
    bar = {
        "epic": "XAUUSD", "close": 110.0, "sma_50": 105.0,
        "ema_8": 109.0, "ema_21": 108.0, "ema_8_prev": 107.0, "ema_21_prev": 108.0,
        "adx": 15.0, "atr_14": 2.0,
        "prediction": PredictionResult(signal_class=SignalClass.BUY, confidence=0.65, probabilities=[0.1, 0.25, 0.65]),
    }
    signal = TrendFollowingStrategy.generate_signal(bar)
    assert signal.direction == SignalDirection.HOLD
```

**Run:** `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_trend_following.py -v`

**Commit:** `feat: trend-following strategy with ML confirmation`

---

### Task C3: Phase C Integration Test

**Run full test suite:**
```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q
```

**Commit:** `feat: Phase C — trend-following strategy + regime hysteresis`

---

### Task C4: Final Commit

```bash
git add -A
git commit -m "feat: 3-level ML overhaul — trend filters, model improvements, strategy architecture

Phase A: SMA/EMA trend filters, confidence tiering (0.50+), SL 2 ATR / TP 2.5x R:R,
         ADX thresholds (20/28), asset momentum rotation, per-asset circuit breaker
Phase B: Purge gap 2x horizon, conservative XGBoost (depth 4, lambda 5),
         horizon 12 bars, threshold 0.75 ATR, feature selection (top 80)
Phase C: Trend-following strategy (EMA cross + SMA50 + ADX + ML confirmation),
         regime hysteresis (3-bar), updated strategy routing"
```

---

## Post-Deploy: Retrain + Validate

1. **Retrain all models** with new settings:
   ```bash
   cd backend && .venv/Scripts/python.exe scripts/train_models.py --tune --retune --horizon 12 --tune-trials 80
   ```

2. **Restart backend** and verify:
   - Models loaded with new features/params
   - Trend filter active (check logs for SMA/EMA penalties)
   - Asset rotation active (check `GET /api/trading/status` → `active_assets`)
   - Confidence tiering active (check for "Confidence tier" in adjustments)

3. **Monitor for 48 hours**:
   - Target: WR > 33%, Kelly fraction > 0
   - Fewer but higher-quality trades
   - No crypto SELL in uptrend
   - Active assets < 20 (rotation working)

---

## Success Criteria

| Metric | Before | Target |
|--------|--------|--------|
| Win Rate | 27.4% | >35% |
| Kelly Fraction | 0.0 (negative) | >0.02 |
| Avg R:R | 2.0:1 | >2.5:1 |
| Trades/Day | ~15 | ~5-8 (fewer, better) |
| Equity Curve | Below SMA | Above SMA |
| Active Assets | 20 (all) | 10-12 (momentum filtered) |
