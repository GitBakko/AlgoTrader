# Full Retrain + Scalp Tuning + DEMO Validation — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Retrain all 20 XGBoost models with Optuna, soften scalp strategy penalties, and prepare for 2-week DEMO validation.

**Architecture:** Three sequential phases: (1) Download fresh data + full Optuna retrain, (2) Tune ScalpScoreStrategy penalties/thresholds in code + .env, (3) Run tests, commit, restart DEMO. The retrain runs as a long background process (~10-12h); scalp tuning is code changes with TDD.

**Tech Stack:** Python 3.12, XGBoost, Optuna, pytest, Capital.com API

---

## Task 1: Download Fresh Market Data

**Files:**
- Run: `backend/scripts/train_models.py` (uses DataAccessLayer internally)
- Data output: `backend/data/historical/`

**Step 1: Verify current data freshness**

```bash
cd backend && .venv/Scripts/python.exe -c "
from src.data.storage import ParquetStorageManager
from src.utils.constants import TRADABLE_ASSETS
s = ParquetStorageManager()
for epic in sorted(TRADABLE_ASSETS):
    try:
        df = s.load(epic, '1h')
        if df is not None and len(df) > 0:
            last = df['datetime'].max()
            print(f'{epic}: {len(df)} bars, last={last}')
        else:
            print(f'{epic}: NO DATA')
    except Exception as e:
        print(f'{epic}: ERROR - {e}')
"
```

Expected: List of 20+ assets with last bar dates. Note which assets have stale data (< March 3, 2026).

**Step 2: Download fresh data for all assets**

```bash
cd backend && .venv/Scripts/python.exe -c "
import asyncio
from src.data.collector import DataCollector
from src.utils.constants import TRADABLE_ASSETS

async def download():
    collector = DataCollector()
    await collector.initialize()
    for epic in sorted(TRADABLE_ASSETS):
        try:
            count = await collector.download_historical(epic, '1h', bars=500)
            print(f'[OK] {epic}: {count} bars downloaded')
        except Exception as e:
            print(f'[FAIL] {epic}: {e}')
    await collector.close()

asyncio.run(download())
"
```

Expected: All 20 assets download successfully. Some may have fewer bars (NAS100 = limited hours).

**Step 3: Verify data freshness after download**

Re-run Step 1 command. All assets should now have data through March 3-4, 2026.

---

## Task 2: Full Retrain with Optuna Tuning

**Files:**
- Run: `backend/scripts/train_models.py`
- Output: `backend/data/models/*/` (new model directories)
- Output: `backend/data/tuned_params/*.json` (new tuned hyperparameters)

**Step 1: Launch full retrain with Optuna (background, long-running)**

```bash
cd backend && .venv/Scripts/python.exe scripts/train_models.py --tune --retune --horizon 12 2>&1 | tee data/retrain_$(date +%Y%m%d_%H%M%S).log
```

Expected: Runs for ~10-12 hours. Output shows per-asset:
- Optuna tuning: `[TUNE] XAUUSD: Best F1=0.54, params={...}`
- Walk-forward training: `[OK] XAUUSD: Trained 8 folds, avg F1=0.5623`
- Final summary: `20/20 assets trained successfully`

**Step 2: Verify results after completion**

```bash
cd backend && .venv/Scripts/python.exe -c "
import json, os
from pathlib import Path

models_dir = Path('data/models')
for epic_dir in sorted(models_dir.iterdir()):
    if not epic_dir.is_dir():
        continue
    versions = sorted(epic_dir.iterdir(), key=lambda p: p.name)
    if versions:
        latest = versions[-1]
        meta_path = latest / 'metadata.json'
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            print(f'{epic_dir.name}: {latest.name} — features={len(meta.get(\"feature_names\", []))}, created={meta.get(\"created_at\", \"?\")}')
        else:
            print(f'{epic_dir.name}: {latest.name} — NO METADATA')
"
```

Expected: All 20 assets have new model directories with today's date. Feature count ~177.

---

## Task 3: Write Failing Tests for New Scalp Thresholds

**Files:**
- Modify: `backend/tests/strategy/test_scalp_score_strategy.py`

**Step 1: Add tests for softened thresholds**

Add this test class at the end of the file:

```python
class TestScalpScoreSoftenedThresholds:
    """Tests for softened penalty multipliers (2026-03-04 tuning)."""

    def test_default_entry_threshold_is_55(self):
        """Entry threshold lowered from 60 to 55."""
        from src.strategy.scalp_score_strategy import DEFAULT_ENTRY_THRESHOLD
        assert DEFAULT_ENTRY_THRESHOLD == 55

    def test_default_full_size_threshold_is_70(self):
        """Full size threshold lowered from 75 to 70."""
        from src.strategy.scalp_score_strategy import DEFAULT_FULL_SIZE_THRESHOLD
        assert DEFAULT_FULL_SIZE_THRESHOLD == 70

    def test_vwap_penalty_is_0_7(self, strategy, recent_bars, config):
        """VWAP penalty softened from 0.4 to 0.7.

        A strong buy signal with price below VWAP should still produce a
        BUY (not HOLD) thanks to the softer penalty.
        """
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,     # bullish
            rsi_14=35.0,                     # oversold bounce
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=32.0,                     # strong trend
            volume=1500, volume_sma_20=1000,
            vwap=106.0,                      # price BELOW vwap (penalty applies)
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        # With 0.7 penalty (not 0.4), a strong buy should still pass threshold
        assert signal.direction == SignalDirection.BUY

    def test_htf_bearish_penalty_is_0_5(self, strategy, recent_bars, config):
        """HTF penalty softened from 0.3 to 0.5.

        A strong buy signal against bearish HTF should still produce BUY
        with the softer penalty, where before it would HOLD.
        """
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=32.0,
            volume=1500, volume_sma_20=1000,
            htf_bias="bearish",              # counter-trend penalty
        )
        signal = strategy.generate_signal("XAUUSD", bar, recent_bars, config)
        # With 0.5 penalty (not 0.3), strong signals should still pass
        assert signal.direction == SignalDirection.BUY

    def test_high_vol_threshold_is_65(self, strategy, recent_bars, config):
        """High vol effective threshold lowered from 70 to 65."""
        bar = _make_bar(
            ema_9=105.5, ema_21=104.8,
            rsi_14=35.0,
            macd_histogram=0.5, macd=0.6, macd_signal=0.1,
            adx_14=32.0,
            volume=1500, volume_sma_20=1000,
        )
        # Create high-vol recent bars (ATR > 2× rolling mean)
        high_vol_bars = pl.DataFrame({
            "close": [100.0 + i * 0.1 for i in range(20)],
            "high": [100.5 + i * 0.1 for i in range(20)],
            "low": [99.5 + i * 0.1 for i in range(20)],
            "volume": [1000 + i * 10 for i in range(20)],
            "atr_14": [0.5] * 15 + [3.0] * 5,  # spike in last 5 bars
        })
        signal = strategy.generate_signal("XAUUSD", bar, high_vol_bars, config)
        # Should produce a signal (threshold 65, not 70)
        assert signal.direction in (SignalDirection.BUY, SignalDirection.SELL)
```

**Step 2: Run tests to verify they fail**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_strategy.py::TestScalpScoreSoftenedThresholds -v
```

Expected: 5 FAILED — thresholds still at 60/75, penalties at 0.4/0.3.

---

## Task 4: Implement Scalp Strategy Threshold Changes

**Files:**
- Modify: `backend/src/strategy/scalp_score_strategy.py`

**Step 1: Update default thresholds (lines 28-29)**

Change:
```python
DEFAULT_ENTRY_THRESHOLD = 60
DEFAULT_FULL_SIZE_THRESHOLD = 75
```
To:
```python
DEFAULT_ENTRY_THRESHOLD = 55
DEFAULT_FULL_SIZE_THRESHOLD = 70
```

**Step 2: Soften VWAP penalty (lines 281, 283)**

Change:
```python
                buy_total *= 0.4   # 60% penalty for buying below VWAP
            elif price > vwap:
                sell_total *= 0.4  # 60% penalty for selling above VWAP
```
To:
```python
                buy_total *= 0.7   # 30% penalty for buying below VWAP
            elif price > vwap:
                sell_total *= 0.7  # 30% penalty for selling above VWAP
```

**Step 3: Soften HTF penalty (lines 304, 307)**

Change:
```python
            buy_total *= 0.3   # 70% penalty — fighting the trend
            sell_total *= 1.1  # 10% bonus — aligned
        elif htf_bias == "bullish":
            sell_total *= 0.3  # 70% penalty — fighting the trend
```
To:
```python
            buy_total *= 0.5   # 50% penalty — fighting the trend
            sell_total *= 1.1  # 10% bonus — aligned
        elif htf_bias == "bullish":
            sell_total *= 0.5  # 50% penalty — fighting the trend
```

**Step 4: Soften high volatility penalty (lines 297-299)**

Change:
```python
            buy_total *= 0.8   # 20% penalty — need stronger conviction
            sell_total *= 0.8
            effective_threshold = max(self.entry_threshold, 70)  # Raise threshold
```
To:
```python
            buy_total *= 0.85  # 15% penalty — need stronger conviction
            sell_total *= 0.85
            effective_threshold = max(self.entry_threshold, 65)  # Raise threshold
```

**Step 5: Run the new tests to verify they pass**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_strategy.py::TestScalpScoreSoftenedThresholds -v
```

Expected: 5 PASSED.

---

## Task 5: Update .env Config Defaults

**Files:**
- Modify: `backend/.env` (lines 110-111)

**Step 1: Update scalp thresholds in .env**

Change:
```
SCALP_SCORE_THRESHOLD=60
SCALP_SCORE_FULL_THRESHOLD=75
```
To:
```
SCALP_SCORE_THRESHOLD=55
SCALP_SCORE_FULL_THRESHOLD=70
```

**Step 2: Update config.py defaults to match (lines 218-219)**

Change:
```python
    scalp_score_threshold: int = Field(default=60, alias="SCALP_SCORE_THRESHOLD")
    scalp_score_full_threshold: int = Field(default=75, alias="SCALP_SCORE_FULL_THRESHOLD")
```
To:
```python
    scalp_score_threshold: int = Field(default=55, alias="SCALP_SCORE_THRESHOLD")
    scalp_score_full_threshold: int = Field(default=70, alias="SCALP_SCORE_FULL_THRESHOLD")
```

---

## Task 6: Run Full Test Suite

**Files:**
- All test files in `backend/tests/`

**Step 1: Run the complete test suite**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: ~1199 tests, 0 failures. Some tests may need threshold adjustments if they assert exact values of 60 or 75.

**Step 2: Fix any regressions**

If tests fail due to old threshold assertions:
- Check `tests/strategy/test_scalp_score_strategy.py` — update any hardcoded 60/75 references
- Check `tests/strategy/test_strategy_manager_scalp.py` — update any threshold-dependent assertions
- Re-run failed tests individually until all pass

**Step 3: Verify zero failures**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -q 2>&1 | tail -5
```

Expected: `XXXX passed, 0 failed`

---

## Task 7: Commit and Push

**Step 1: Stage and commit scalp tuning changes**

```bash
cd backend && git add -A && git commit -m "feat: soften scalp strategy thresholds for more trade generation

- VWAP penalty: 0.4 → 0.7 (less punitive for consolidation)
- HTF penalty: 0.3 → 0.5 (allow strong counter-trend scalps)
- Entry threshold: 60 → 55 (include borderline signals)
- Full threshold: 75 → 70 (full position more achievable)
- High vol penalty: 0.8 → 0.85, threshold 70 → 65
- Added 5 tests for new thresholds

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

**Step 2: Push to remote**

```bash
git push origin master
```

---

## Task 8: Restart DEMO and Verify Signal Generation

**Step 1: Kill any running backend processes**

```bash
netstat -ano | grep 8000
# Kill the PID if running
taskkill /F /PID <PID>
```

**Step 2: Start backend with new models**

```bash
cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --reload --port 8000
```

**Step 3: Start the trading loop**

```bash
curl -X POST http://localhost:8000/api/trading/start
```

**Step 4: Monitor logs for ScalpScore signals (not just HOLD)**

```bash
tail -f backend/logs/algotrader_*.log | grep -i "scalpscore\|scalp_score\|BUY\|SELL"
```

Expected: Within 15-60 minutes, should see ScalpScore generating BUY/SELL signals (not only HOLD). Look for:
- `ScalpScore XAUUSD: score=XX direction=BUY` lines
- Signals with scores in the 55-70 range (previously filtered out)

**Step 5: Check trading status after 1 hour**

```bash
curl http://localhost:8000/api/trading/status | python -m json.tool
```

Expected: `is_running: true`, `signals_generated > 0`, `scalp_mode: true`

---

## Task 9: DEMO Validation Monitoring (2+ weeks)

This is an ongoing monitoring task, not a code task.

**Daily Checks:**
1. Check logs for errors: `grep -i "error\|exception\|traceback" backend/logs/algotrader_*.log`
2. Check open positions: `curl http://localhost:8000/api/positions/open`
3. Check performance: `curl http://localhost:8000/api/trading/performance`
4. Check ScalpScore signal distribution: `grep "ScalpScore" backend/logs/algotrader_*.log | tail -50`

**Weekly Review:**
1. Win Rate target: > 40%
2. Sharpe Ratio target: > 0.5
3. Max Drawdown target: < 10%
4. Avg trade duration: < 4 hours (scalp)
5. If KPIs are poor, adjust thresholds in .env (no code change needed)

**Go/No-Go Decision (after 2 weeks):**
- All KPI targets met → proceed to live (0.5% risk/trade)
- Missed targets → iterate on parameters, extend DEMO
