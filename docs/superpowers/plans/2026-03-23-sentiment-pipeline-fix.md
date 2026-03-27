# Sentiment Pipeline Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire SIL sentiment data (Fear&Greed, FRED yields, Alpha Vantage sentiment, COT positioning, Social sentiment) through the full prediction pipeline so that ML models and ScalpScore actually USE sentiment when making trade entry decisions.

**Architecture:** Three-layer fix: (1) Plumb `sil_data` from paper_loop through predict() → build_features, so the 12 SIL feature columns contain real values instead of zeros. (2) Add a 7th "sentiment" directional vote group to ScalpScore that uses the SIL composite score to bias trade direction. (3) Retrain all models with `include_sentiment=True` so XGBoost learns sentiment patterns. All changes are backwards-compatible — `sil_data=None` defaults to zeros (graceful degradation).

**Tech Stack:** Python 3.12+, Polars, XGBoost, Pydantic v2

**Branch:** `feature/evolution-multi-agent` (current)

---

## File Structure

### Files to Modify

| File | Change | Responsibility |
|------|--------|---------------|
| `backend/src/models/prediction_service.py` | Add `sil_data` param to `predict()` | Pass SIL data to feature builder |
| `backend/src/features/builder.py` | Add `sil_data` param to `build_features_from_df()` | Compute SIL features in single-TF path |
| `backend/src/trading/paper_loop.py` | Pass `self._sil_data` to `predict()` | Wire SIL data into prediction call |
| `backend/src/strategy/scalp_score_strategy.py` | Add 7th sentiment vote group | Direct sentiment influence on signal |
| `backend/src/strategy/strategy_manager.py` | Pass `sil_data` through to ScalpScore | Wire SIL to strategy layer |
| `backend/src/models/trainer.py` | Pass `sil_data` to `build_features()` during training | Models learn sentiment patterns |

### Files to Create

| File | Responsibility |
|------|---------------|
| `backend/tests/features/test_sil_pipeline_integration.py` | End-to-end test: SIL data → features → non-zero values |
| `backend/tests/strategy/test_scalp_sentiment_vote.py` | Test 7th sentiment vote group |

---

## Task 1: Wire `sil_data` Through Prediction Service

**Files:**
- Modify: `backend/src/models/prediction_service.py:96-133`
- Modify: `backend/src/features/builder.py:273-340`
- Test: `backend/tests/features/test_sil_pipeline_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/features/test_sil_pipeline_integration.py
"""Test that SIL data flows through the prediction pipeline to non-zero features."""
import polars as pl
import pytest
from src.external.sil_schemas import SILData, FearGreedData, FREDData, AlphaVantageData, COTData, SocialSentimentData
from src.features.builder import FeatureBuilder
from src.features.sil_features import SIL_FEATURE_COLS


def _make_sil_data() -> SILData:
    """Create SIL data with non-zero values for all 5 sources."""
    return SILData(
        fear_greed=FearGreedData(normalized=0.65, gold_bias=0.3, value=65),
        fred=FREDData(real_yield_10y=-0.5, breakeven_inflation=2.3),
        alpha_vantage=AlphaVantageData(average_sentiment_score=0.4, bullish_ratio=0.6),
        cot=COTData(net_position_normalized=0.25, z_score_4w=1.2, is_institutional_bullish=True),
        social=SocialSentimentData(combined_bullish_ratio=0.55),
    )


def _make_ohlcv_df(n: int = 100) -> pl.DataFrame:
    """Create minimal OHLCV DataFrame for feature building."""
    import numpy as np
    np.random.seed(42)
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    return pl.DataFrame({
        "timestamp": pl.datetime_range(
            pl.lit("2026-01-01").cast(pl.Datetime),
            periods=n, interval="1h", eager=True,
        ),
        "open": close - np.random.rand(n) * 0.3,
        "high": close + np.random.rand(n) * 0.5,
        "low": close - np.random.rand(n) * 0.5,
        "close": close,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    })


class TestSILPipelineIntegration:
    """Verify SIL features are non-zero when sil_data is provided."""

    def test_build_features_from_df_with_sil_data(self):
        """SIL features should be non-zero when sil_data is provided."""
        builder = FeatureBuilder()
        df = _make_ohlcv_df()
        sil = _make_sil_data()

        result_df, meta = builder.build_features_from_df(
            df, "XAUUSD", "1h", normalize=False, sil_data=sil,
        )

        # At least some SIL features should be non-zero
        for col in SIL_FEATURE_COLS:
            assert col in result_df.columns, f"Missing SIL column: {col}"

        sil_values = result_df.select(SIL_FEATURE_COLS).to_numpy()
        non_zero = (sil_values != 0.0).sum()
        assert non_zero > 0, "All SIL features are zero — data not flowing through"

    def test_build_features_from_df_without_sil_defaults_to_zero(self):
        """Without sil_data, SIL features should be zero (graceful degradation)."""
        builder = FeatureBuilder()
        df = _make_ohlcv_df()

        result_df, meta = builder.build_features_from_df(
            df, "XAUUSD", "1h", normalize=False,
        )

        for col in SIL_FEATURE_COLS:
            assert col in result_df.columns

        sil_values = result_df.select(SIL_FEATURE_COLS).to_numpy()
        assert (sil_values == 0.0).all(), "SIL features should be zero without sil_data"

    def test_sil_composite_score_populated(self):
        """The composite score should be a meaningful value when SIL data is provided."""
        builder = FeatureBuilder()
        df = _make_ohlcv_df()
        sil = _make_sil_data()

        result_df, _ = builder.build_features_from_df(
            df, "XAUUSD", "1h", normalize=False, sil_data=sil,
        )

        composite = result_df["sil_composite_score"].to_list()[-1]
        assert composite > 0.0, f"Composite score should be >0 with bullish SIL data, got {composite}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/features/test_sil_pipeline_integration.py -v`
Expected: FAIL — `build_features_from_df() got unexpected keyword argument 'sil_data'`

- [ ] **Step 3: Implement — Add `sil_data` to `build_features_from_df()`**

In `backend/src/features/builder.py`, modify `build_features_from_df()` (line 273):

```python
def build_features_from_df(
    self,
    df: pl.DataFrame,
    epic: str,
    timeframe: str,
    config: AssetFeatureConfig | None = None,
    include_regime: bool = True,
    normalize: bool = True,
    sil_data: "SILData | None" = None,  # NEW
) -> tuple[pl.DataFrame, FeatureMatrix]:
```

Add SIL feature computation after regime detection (after line 311, before normalization):

```python
        # SIL features (sentiment/macro from Signal Intelligence Layer)
        from src.features.sil_features import compute_sil_features
        df = compute_sil_features(df, sil_data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/features/test_sil_pipeline_integration.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/features/builder.py backend/tests/features/test_sil_pipeline_integration.py
git commit -m "feat(features): add sil_data param to build_features_from_df for sentiment pipeline"
```

---

## Task 2: Wire `sil_data` Through predict() and paper_loop

**Files:**
- Modify: `backend/src/models/prediction_service.py:96-133`
- Modify: `backend/src/trading/paper_loop.py:1135`

- [ ] **Step 1: Modify `prediction_service.predict()` to accept and pass `sil_data`**

In `backend/src/models/prediction_service.py`, change signature (line 96):

```python
def predict(self, epic: str, timeframe: str = "1h", sil_data=None) -> PredictionResult | None:
```

Pass `sil_data` to both build_features calls:

Line 121 (multi-TF path):
```python
df_features, matrix = self.feature_builder.build_features(
    epic=epic, timeframe=timeframe,
    normalize=True, include_regime=True, multi_timeframe=True,
    sil_data=sil_data,  # NEW
)
```

Line 131 (single-TF path):
```python
df_features, matrix = self.feature_builder.build_features_from_df(
    df, epic, timeframe, normalize=True, include_regime=True,
    sil_data=sil_data,  # NEW
)
```

- [ ] **Step 2: Wire `sil_data` in paper_loop `_process_epic()`**

In `backend/src/trading/paper_loop.py`, modify line 1135:

```python
# BEFORE:
prediction = self.prediction_service.predict(epic, timeframe=self._candle_resolution)

# AFTER:
prediction = self.prediction_service.predict(
    epic, timeframe=self._candle_resolution,
    sil_data=self._sil_data if self._sil_clients_initialized else None,
)
```

- [ ] **Step 3: Verify existing tests still pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/models/ tests/features/ -v --tb=short -q`
Expected: All existing tests PASS (sil_data defaults to None)

- [ ] **Step 4: Commit**

```bash
git add backend/src/models/prediction_service.py backend/src/trading/paper_loop.py
git commit -m "feat(pipeline): wire sil_data from paper_loop through predict() to features"
```

---

## Task 3: Add Sentiment Vote Group to ScalpScore

**Files:**
- Modify: `backend/src/strategy/scalp_score_strategy.py:159-275`
- Modify: `backend/src/strategy/strategy_manager.py:102-131`
- Test: `backend/tests/strategy/test_scalp_sentiment_vote.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/strategy/test_scalp_sentiment_vote.py
"""Test the 7th sentiment vote group in ScalpScore."""
import pytest
from src.strategy.scalp_score_strategy import ScalpScoreStrategy


class TestSentimentVote:
    """Test _vote_sentiment method."""

    def test_bullish_sentiment(self):
        """High composite score → +1 (bullish)."""
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(composite_score=0.7)
        assert vote == 1
        assert details["composite"] == 0.7

    def test_bearish_sentiment(self):
        """Low composite score → -1 (bearish)."""
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(composite_score=0.25)
        assert vote == -1

    def test_neutral_sentiment(self):
        """Mid-range composite score → 0 (neutral)."""
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(composite_score=0.5)
        assert vote == 0

    def test_zero_composite_neutral(self):
        """Zero composite (no SIL data) → 0 (neutral, doesn't break anything)."""
        strategy = ScalpScoreStrategy()
        vote, details = strategy._vote_sentiment(composite_score=0.0)
        assert vote == 0

    def test_sentiment_in_directional_votes(self):
        """Sentiment vote should appear in votes_data when sil_data provided."""
        strategy = ScalpScoreStrategy()
        # We can't easily test the full generate_signal here because it needs
        # market data, but we verify the method exists and has correct interface
        assert hasattr(strategy, '_vote_sentiment')
        vote, details = strategy._vote_sentiment(0.8)
        assert isinstance(vote, int)
        assert isinstance(details, dict)
        assert "composite" in details
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_sentiment_vote.py -v`
Expected: FAIL — `ScalpScoreStrategy has no attribute '_vote_sentiment'`

- [ ] **Step 3: Implement `_vote_sentiment()` method**

In `backend/src/strategy/scalp_score_strategy.py`, add after the `_vote_bb_squeeze` method (around line 148):

```python
    @staticmethod
    def _vote_sentiment(
        composite_score: float, bullish_threshold: float = 0.6, bearish_threshold: float = 0.35,
    ) -> tuple[int, dict]:
        """Sentiment vote based on SIL composite score.

        Thresholds:
        - composite > 0.6 → BULLISH (+1)
        - composite < 0.35 → BEARISH (-1)
        - otherwise → NEUTRAL (0)
        - composite == 0.0 → NEUTRAL (no SIL data available)
        """
        details = {"composite": composite_score}
        if composite_score <= 0.0:
            return 0, details  # No data — don't influence
        if composite_score > bullish_threshold:
            return 1, details
        elif composite_score < bearish_threshold:
            return -1, details
        return 0, details
```

- [ ] **Step 4: Wire sentiment vote into `generate_signal()`**

In `generate_signal()`, the method signature needs `sil_data` (or just `sil_composite`). The simplest approach: pass `sil_composite_score` via `current_bar` dict (which already comes from `market_data`).

In `backend/src/strategy/scalp_score_strategy.py`, after the bb_vote (line 235), add:

```python
        # 7th vote: Sentiment (SIL composite score)
        sil_composite = float(current_bar.get("sil_composite_score", 0.0))
        sentiment_vote, sentiment_details = self._vote_sentiment(sil_composite)
```

Update `votes_data` dict (after line 244):
```python
        votes_data = {
            "ema": {"value": ema_vote, **ema_details},
            "rsi": {"value": rsi_vote, **rsi_details},
            "macd": {"value": macd_vote, **macd_details},
            "volume": {"value": vol_vote, **vol_details},
            "adx": {"value": adx_vote, **adx_details},
            "bb_keltner": {"value": bb_vote, **bb_details},
            "sentiment": {"value": sentiment_vote, **sentiment_details},  # NEW
        }
```

Add sentiment as a **directional vote** (line 249):
```python
        directional_votes = [ema_vote, rsi_vote, macd_vote, bb_vote, sentiment_vote]
```

- [ ] **Step 5: Inject SIL composite into `market_data` dict**

In `backend/src/strategy/strategy_manager.py`, modify `process_prediction()` — it receives `market_data` dict and passes it to `generate_signal()`. The SIL composite needs to be in `market_data`.

In `backend/src/trading/paper_loop.py`, in `_process_epic()` around line 1137 (after market_data is loaded), inject SIL composite:

```python
        # Inject SIL composite score into market_data for ScalpScore sentiment vote
        if self._sil_data and self._sil_clients_initialized:
            market_data["sil_composite_score"] = self._sil_data.composite_score
```

Note: Need to check if `SILData` has a `composite_score` property. If not, compute it from the sub-fields or use the `sil_composite_score` from `compute_sil_features`.

- [ ] **Step 6: Run tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_sentiment_vote.py tests/strategy/test_scalp_score.py -v --tb=short`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add backend/src/strategy/scalp_score_strategy.py backend/src/trading/paper_loop.py backend/tests/strategy/test_scalp_sentiment_vote.py
git commit -m "feat(strategy): add 7th sentiment vote group to ScalpScore using SIL composite"
```

---

## Task 4: Enable Sentiment in Model Training

**Files:**
- Modify: `backend/src/models/trainer.py:82`
- Modify: `backend/scripts/train_models.py` (or equivalent retrain script)

- [ ] **Step 1: Pass `sil_data` to `build_features()` during training**

In `backend/src/models/trainer.py`, the `train()` method calls `build_features()` at line 82. Add `sil_data` parameter:

First, add `sil_data` to the `train()` signature:
```python
def train(
    self,
    model: BaseMLModel,
    epic: str,
    timeframe: str,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    save_best: bool = True,
    multi_timeframe: bool = False,
    include_sentiment: bool = False,
    sil_data=None,  # NEW: pass SIL data for training with sentiment context
) -> TrainingResult:
```

Then pass it through to `build_features()`:
```python
df, feature_meta = self.feature_builder.build_features(
    epic=epic,
    timeframe=timeframe,
    start_date=start_date,
    end_date=end_date,
    normalize=True,
    include_regime=True,
    multi_timeframe=multi_timeframe,
    include_sentiment=include_sentiment,
    sil_data=sil_data,  # NEW
)
```

- [ ] **Step 2: Update retrain-all endpoint to pass current SIL data**

In `backend/src/api/routers/models.py`, find the retrain endpoint and check if it can access `sil_data` from the paper_loop. If the paper_loop has `self._sil_data`, pass it to the trainer.

Check the retrain flow and add `sil_data=loop._sil_data` to the training call.

- [ ] **Step 3: Verify existing trainer tests still pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/models/ -v --tb=short -q`
Expected: All PASS (sil_data defaults to None)

- [ ] **Step 4: Commit**

```bash
git add backend/src/models/trainer.py
git commit -m "feat(training): enable SIL sentiment data in model training pipeline"
```

---

## Task 5: Retrain All Models With Sentiment

- [ ] **Step 1: Trigger retrain with sentiment enabled**

After all code changes are committed and the backend is restarted:

```bash
curl -X POST http://127.0.0.1:8000/api/models/retrain-all
```

The retrain will now use the current SIL data (fear&greed, FRED, sentiment, COT, social) as features. Models will learn patterns like:
- High fear + declining price → likely to continue falling
- Bullish COT positioning + bullish technicals → stronger signal
- Extreme social sentiment → potential contrarian signal

- [ ] **Step 2: Verify retrained models include SIL features**

After retrain completes, check that the new model's feature list includes SIL columns:

```bash
curl -s http://127.0.0.1:8000/api/models/ | python -c "
import sys, json
models = json.load(sys.stdin)['data']
# Check if newest model has SIL features
for m in models[:1]:
    print(m.get('id'), m.get('num_features'))
"
```

Expected: Feature count should increase from ~187 to ~199 (187 + 12 SIL features).

- [ ] **Step 3: Commit retrain results note**

```bash
git commit --allow-empty -m "chore: retrained all 20 models with SIL sentiment features"
```

---

## Task 6: Full Integration Verification

- [ ] **Step 1: Run ALL tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short --ignore=tests/test_full_system.py --ignore=tests/strategy/test_orb_fvg.py -q
```
Expected: 2250+ passed, 0 new failures

- [ ] **Step 2: Verify SIL features are non-zero in live prediction**

With backend running and SIL enabled, check that predictions include sentiment:

```bash
curl -s http://127.0.0.1:8000/api/trading/status | python -c "
import sys, json
d = json.load(sys.stdin)['data']
for epic, sig in d.get('last_signals', {}).items():
    if sig.get('status') not in ('market_closed', 'hold'):
        print(epic, sig.get('status'), sig.get('direction'))
        break
"
```

- [ ] **Step 3: Final commit and push**

```bash
git push origin feature/evolution-multi-agent
```

---

## Summary

| Task | What Changes | Impact |
|------|-------------|--------|
| 1 | `build_features_from_df()` gets `sil_data` param | 12 SIL features no longer zero |
| 2 | `predict()` passes `sil_data` from paper_loop | ML model sees real sentiment |
| 3 | ScalpScore gets 7th sentiment vote | Direct sentiment influence on entry |
| 4 | Trainer passes `sil_data` to training | Models learn sentiment patterns |
| 5 | Retrain all 20 models | Models optimized for sentiment |
| 6 | Integration verification | Confirm no regressions |

**Expected outcome:** Models trained on 187+12=199 features including real-time sentiment. ScalpScore uses 7 vote groups (5 directional including sentiment + 2 confirming). Trade entries now consider macro/geopolitical sentiment, not just technical indicators.
