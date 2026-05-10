# Models / Prediction Audit — 2026-05-10

**Files reviewed:** `backend/src/models/` (all), `backend/src/features/` (all), `backend/scripts/train_models.py`, tests.

---

## CRITICAL

### C1 — `last_split = None` unguarded dereference crashes training on edge data sizes
`backend/src/models/trainer.py:233, 311, 323`

**What**: `last_split` initialized None at 233, assigned only inside `for split in self.splitter.split(n_samples):`. After loop, line 323 does `last_split.val_indices` unconditionally. The guard at 223 only checks `n_samples < min_samples`; splitter loop can yield 0 iterations on rounding-boundary data.

**Why it matters**: Silent training abort. No model saved, PredictionService keeps stale model.

**Fix**: `if last_split is not None: ...` guard + warning log.

---

### C2 — Calibrator fitted on last-fold val with best-fold model — leakage
`backend/src/models/trainer.py:321-330`

**What**: Best-fold model loaded at 311. Calibrator fitted at 327 on `X_cal = X[last_split.val_indices]`. In rolling walk-forward (default step=21, train=252), best-fold's training window can overlap last-fold's val window. Calibrator sees data the best model partially trained on.

**Why it matters**: Over-confident calibrated probabilities. Every traded `signal.confidence` is biased; effective threshold lowered, more false-entry trades.

**Fix**: Track `best_val_indices` during fold loop, use those for calibration.

---

## HIGH

### H1 — `asyncio.get_event_loop()` deprecated, breaks Python 3.12+
`backend/src/models/training_orchestrator.py:273`

**Fix**: `asyncio.get_running_loop()`.

---

### H2 — `TrainingJob.progress: float` violated by string assignment
`backend/src/models/training_orchestrator.py:178, 241, 265`

**What**: `job.progress = "Complete"` (string) assigned to field annotated `float`. Frontend WS consumer parsing as number fails.

**Fix**: Numeric values throughout (0.1/0.5/1.0) OR change annotation to `str | float`.

---

### H3 — Hot-reload non-atomic: new model + stale calibrator window
`backend/src/models/prediction_service.py:435-448`

**What**: Writes to `self._loaded_models[epic]` (line 436), then `self._calibrators[epic]` (line 444). asyncio scheduler can resume `predict()` between assignments → new XGBoost weights + old isotonic calibrator.

**Fix**: Build `(new_model, new_calibrator)` first, assign both in two consecutive statements with no `await` between.

---

### H4 — `datetime.now()` naive — silently drops sentiment data via swallowed TypeError
`backend/src/features/builder.py:63`

**What**: Naive datetime → comparison with tz-aware datetime in client raises TypeError → caught by outer `except Exception` → NVDA/TSLA sentiment training data replaced with `0.0` placeholders.

**Fix**: `datetime.now(timezone.utc)`.

---

### H5 — `atr_14=0` produces `inf` future-return → spurious BUY/SELL label
`backend/src/models/target_builder.py:60-61`

**What**: `_atr_relative_return = _future_change / atr_column` no zero guard. Polars produces `inf` for non-zero/0. `inf > threshold` → BUY; `-inf` → SELL. ATR=0 occurs on first bar before Wilder smoothing initializes.

**Fix**: `.fill_inf(None)` after division, or pre-filter `df.filter(pl.col(atr_col) > 0)`.

---

## MEDIUM

### M1 — `n_classes = len(np.unique(y))` wrong if class absent in training set
`backend/src/models/trainer.py:329`

**Fix**: Use fixed `n_classes = 3` from `SignalClass`.

---

### M2 — Walk-forward docstring claims "expanding/rolling", code is rolling-only
`backend/src/models/walk_forward.py:3-4`

**Fix**: Add `expanding` parameter or correct docstring.

---

### M3 — `train_models.py` parallel BARS_PER_DAY table diverges from `asset_metadata.py`
`backend/scripts/train_models.py:39-58`

**What**: Script uses 10 bars/day for stocks; production uses 10.5 (`asset_metadata.py`). Walk-forward windows differ between manual training and production retraining.

**Fix**: Call `compute_walk_forward_windows(epic, timeframe)` from `asset_metadata.py`.

---

### M4 — Dead expression `y_proba.shape[0]`
`backend/src/models/calibration.py:108`

**Fix**: Delete or restore `n_samples = ...` assignment.

---

## Coverage Gaps

- `last_split=None` crash path untested
- Calibrator-leakage detection untested
- Concurrent `predict()` + `reload_model()` untested
- `atr_14=0` input untested
- Naive datetime sentinel untested
- `TrainingJob.progress` type assert missing
- `CrossAssetEngine.compute_correlation_regime()` no dedicated tests
- `ConfidenceCalibrator.transform()` n_classes mismatch untested

---

## Summary

| Pri | ID | Location | Issue |
|-----|-----|----------|-------|
| CRITICAL | C1 | trainer.py:323 | `last_split=None` AttributeError crash |
| CRITICAL | C2 | trainer.py:321 | Calibrator leakage on best/last fold overlap |
| HIGH | H1 | training_orchestrator.py:273 | get_event_loop deprecated |
| HIGH | H2 | training_orchestrator.py:178 | progress field type violation |
| HIGH | H3 | prediction_service.py:435 | non-atomic hot-reload |
| HIGH | H4 | features/builder.py:63 | naive datetime drops sentiment |
| HIGH | H5 | target_builder.py:60 | ATR=0 → inf label |
| MEDIUM | M1-M4 | various | n_classes hardcode, BARS table drift, dead expr |
