# Phase 1 Expansion — Risk Config + Dynamic Correlation Design

**Date:** 2026-05-23
**Status:** Approved (brainstorming session)
**Approach:** B (Recommended) — see §Background

## Background

Phase 0 ri-validation (2026-05-23) expanded the tradable basket from 5
to 19 assets after the 74h spread audit recalibrated `ASSET_SPREADS`.
Phase 3 cost re-run confirmed top-5 PASS post-recalib (mean Sharpe
3.95). AMZN was excluded after a dedicated Optuna 100-trial deep-dive
(Sharpe −1.07, MC p=0.91 — see `project_amzn_excluded_2026-05-23.md`).

The Kelly/correlation review note
(`docs/handoff/kelly_correlation_review_2026-05-23.md`) identified five
risk-stack adjustments needed before enabling the 19-asset basket in
paper trading. This spec lands those adjustments.

The dynamic correlation infrastructure already exists
(`paper_loop._refresh_correlation_regime` + `CorrelationGuard.update_matrix`)
but is gated by the Phase 2 `correlation_regime_enabled` flag (currently
False) and capped at `self.epics[:10]`. Both must change.

## Goals

1. Lift the concurrent-position cap so 19 candidates can compete:
   `MAX_TOTAL_OPEN_POSITIONS` 5 → 10.
2. Lower the per-position notional cap to preserve 100 % gross
   exposure ceiling: `max_position_pct` 0.20 → 0.10.
3. Activate the always-skipped total-exposure guard at default
   `MAX_TOTAL_EXPOSURE=1.0` (semantic fix in `risk_manager.py:212`).
4. Decouple the dynamic correlation matrix from the Phase 2 regime
   gate; bootstrap on backend startup; remove the `[:10]` epic cap.
5. Remove dead config (`max_correlated_exposure` field, unused).

## Non-Goals

- Per-asset Kelly stats (`epic → deque`). Deferred to Phase 2 of the
  Kelly/correlation review per the note's §6.
- Static correlation pair extension (USD-forex, tech megacap). The
  dynamic matrix supersedes; static pairs remain as legacy fallback.
- Wire `max_correlated_exposure` as a cluster cap. The dynamic matrix
  multiplier already enforces the same intent on a per-pair basis.
- Phase 2 regime gate behavior (`correlation_regime_enabled` flag).
  Untouched — that's a separate experiment that failed at its own gate.
- LIVE deploy of the expanded basket. This spec lands the infra;
  validation is a 2-week paper soak in a subsequent milestone.

## Architecture

Risk-stack reconfiguration spanning 5 production files. Boundary
between the components:

- **`RiskLimits` schema** (`backend/src/risk/schemas.py`) — Pydantic
  defaults that drive `RiskManager` construction. Changes here flow
  to every production and test instantiation that uses the default
  constructor.
- **`RiskManager.check_trade` flow** (`backend/src/risk/risk_manager.py`)
  — sequential gate stack. Single-line semantic fix at line 212 so
  the total-exposure guard runs when `MAX_TOTAL_EXPOSURE` is 1.0.
- **Application settings** (`backend/src/utils/config.py`) — single
  new flag `DYNAMIC_CORRELATION_ENABLED` decouples the matrix
  refresher from the Phase 2 regime gate.
- **Paper-trading loop** (`backend/src/trading/paper_loop.py`) — split
  the existing `_refresh_correlation_regime` into two concerns: matrix
  population (always-on when flag enabled) and regime classification
  (still gated by the old flag). Add a bootstrap call inside
  `start()` / `_initialize_state` so the matrix is populated before
  the first signal tick instead of waiting 30 minutes.
- **Tests** (`backend/tests/risk/`, `backend/tests/trading/`) — adjust
  existing fixtures to new defaults; add coverage for bootstrap +
  full-basket usage + matrix validation.

## Components

### `backend/src/risk/schemas.py` (RiskLimits)

```python
class RiskLimits(BaseModel):
    max_risk_per_trade: float = Field(default=0.02, ...)
    max_daily_drawdown: float = Field(default=0.05, ...)
    max_total_drawdown: float = Field(default=0.15, ...)
    max_position_pct: float = Field(
        default=0.10,  # was 0.20 — Phase 1 expansion 2026-05-23
        ge=0.01, le=1.0,
        description="Max per-position notional as fraction of equity.",
    )
    # max_correlated_exposure REMOVED (dead config)
    max_total_open_positions: int = Field(
        default=10,  # was 5 — Phase 1 expansion 2026-05-23 (19-asset basket)
        ge=1, le=50,
        description="Max concurrent open positions across all assets.",
    )
    max_total_exposure: float = Field(default=1.0, ...)
```

### `backend/src/risk/risk_manager.py` (line 212 guard fix)

```python
# Was:  if self.limits.max_total_exposure < 1.0 and open_positions and equity > 0:
# Now:  if self.limits.max_total_exposure <= 1.0 and open_positions and equity > 0:
```

The semantic intent of `MAX_TOTAL_EXPOSURE=1.0` is "100 % cap enforced",
not "disabled". The fix activates the existing enforcement branch
without changing the threshold.

### `backend/src/utils/config.py` (new flags)

```python
dynamic_correlation_enabled: bool = Field(
    default=True, alias="DYNAMIC_CORRELATION_ENABLED"
)
dynamic_correlation_bootstrap_min_assets: int = Field(
    default=5, alias="DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS"
)
```

### `backend/src/trading/paper_loop.py` (split refresh)

The existing `_refresh_correlation_regime` (line 955-1012) is split
into two methods:

```python
async def _refresh_correlation_matrix(self, force: bool = False) -> None:
    """Recompute pairwise correlation matrix every 30 min.

    Gated by DYNAMIC_CORRELATION_ENABLED. Uses full self.epics
    (no [:10] truncation). Pushes result to risk_manager.correlation_guard.

    When force=True, throttle is bypassed — used for bootstrap on startup.
    """
    now = _time.monotonic()
    if not force and now - self._correlation_matrix_ts < 1800:
        return
    self._correlation_matrix_ts = now

    _settings = get_settings()
    if not _settings.dynamic_correlation_enabled:
        return

    try:
        all_dfs = {}
        for epic in self.epics:  # FULL basket
            try:
                df = self.data_access.get_candles(epic, self._candle_resolution)
                if df is not None and len(df) >= 100:
                    all_dfs[epic] = df
            except Exception:
                pass

        min_assets = _settings.dynamic_correlation_bootstrap_min_assets
        if len(all_dfs) < min_assets:
            logger.info(
                f"Correlation matrix update skipped: "
                f"{len(all_dfs)} < {min_assets} epics with data"
            )
            return

        epics_list = sorted(all_dfs.keys())
        common_len = min(len(df) for df in all_dfs.values())
        returns = np.array([
            np.diff(np.log(np.maximum(all_dfs[e]["close"].tail(common_len).to_numpy(), 1e-10)))
            for e in epics_list
        ])
        corr_matrix = np.corrcoef(returns)

        # Validate finite (new — pushed down into update_matrix for reuse)
        self.risk_manager.correlation_guard.update_matrix(epics_list, corr_matrix)
        logger.info(
            f"Correlation matrix updated: {len(epics_list)} epics, "
            f"shape={corr_matrix.shape}, "
            f"mean_abs_corr={np.abs(corr_matrix[np.triu_indices_from(corr_matrix, k=1)]).mean():.3f}"
        )
    except Exception as e:
        logger.debug(f"Correlation matrix refresh failed: {e}")


async def _refresh_correlation_regime(self) -> None:
    """Classify panic vs normal regime — gated by CORRELATION_REGIME_ENABLED.

    Phase 2 feature, separate from matrix population.
    """
    now = _time.monotonic()
    if now - self._correlation_regime_ts < 1800:
        return
    self._correlation_regime_ts = now

    _settings = get_settings()
    if not _settings.correlation_regime_enabled:
        return

    try:
        from src.features.cross_asset import CrossAssetEngine
        engine = CrossAssetEngine()
        all_dfs = {}
        for epic in self.epics[:10]:  # regime classification stays at 10 (legacy)
            try:
                df = self.data_access.get_candles(epic, self._candle_resolution)
                if df is not None and len(df) >= 100:
                    all_dfs[epic] = df
            except Exception:
                pass

        if len(all_dfs) >= 5:
            regime_df = engine.compute_correlation_regime(all_dfs, window=50)
            if len(regime_df) > 0:
                last = regime_df.row(-1, named=True)
                self._correlation_regime = last.get("correlation_regime") or "normal"
                mean_corr = last.get("mean_correlation", 0)
                logger.info(
                    f"Correlation regime: {self._correlation_regime} (mean={mean_corr:.3f})"
                )
    except Exception as e:
        logger.debug(f"Correlation regime update failed: {e}")
```

Bootstrap is invoked at startup. New state var `_correlation_matrix_ts`
tracks throttle independently from `_correlation_regime_ts`.

In `start()` (or `_initialize_state` — final location determined by
the implementation plan):

```python
# After broker positions reconciled, before loop begins:
await self._refresh_correlation_matrix(force=True)
```

Both methods are called every `_run_iteration` tick (legacy pattern at
line 2391). The throttle inside each guards CPU.

### `backend/src/risk/correlation_guard.py` (`update_matrix` validation)

```python
def update_matrix(self, epics: list[str], matrix: np.ndarray) -> None:
    """Store an NxN correlation matrix for the given epics."""
    matrix_arr = np.asarray(matrix, dtype=float)
    if not np.isfinite(matrix_arr).all():
        logger.error(
            f"Correlation matrix rejected: non-finite values "
            f"(NaN/Inf count {np.sum(~np.isfinite(matrix_arr))})"
        )
        return  # keep prior matrix
    self._epic_index = {_normalize_epic(e): i for i, e in enumerate(epics)}
    self._matrix = matrix_arr
    logger.info(f"Correlation matrix updated: {len(epics)} epics, shape={self._matrix.shape}")
```

### `backend/.env` (runtime override)

Append:

```
MAX_TOTAL_OPEN_POSITIONS=10
DYNAMIC_CORRELATION_ENABLED=true
```

`max_position_pct` covered by schema default. `MAX_TOTAL_EXPOSURE`
already 1.0 by default (guard fix in `risk_manager.py` activates it).

## Data Flow

```
[paper_loop._run_iteration] (60 s legacy / 4 h bar-aligned)
   ↓
[strategy.generate_signal(epic)] → TradingSignal
   ↓
[risk_manager.check_trade(signal, equity, open_positions, trade_history)]
   1. CircuitBreakers (DD daily/total)
   2. max_total_open_positions check (≥ 10 → REJECT)            ← updated cap
   3. max_total_exposure check (≥ 1.0 → REJECT)                 ← now active
   4. SL/TP paired-pair rule (R:R ≥ 0.40)
   5. correlation_guard.check_exposure_dynamic(...)              ← uses fresh matrix
        → size_multiplier (1.0 - |corr|) for in-matrix epics
        → static CORRELATION_PAIRS fallback for missing epics
   6. PositionSizer / KellySizer (max_position_pct=0.10)         ← updated cap
   7. Apply multipliers (correlation × confidence × equity-curve)
   7-bis. MIN_RISK_AMOUNT_USD floor (lift + cap-fallback)
   8. EpicSLCooldown / SpreadFilter
   → RiskCheckResult(approved, size, sl, tp, audit)

[paper_loop._refresh_correlation_matrix] (bootstrap on start + every 30 min)
   ↓
   gate: dynamic_correlation_enabled
   ↓
   collect candles for self.epics (full basket, no [:10])
   ↓
   log-returns → np.corrcoef → NxN matrix
   ↓
   correlation_guard.update_matrix(epics, matrix) — validated np.isfinite
```

Bootstrap timing:

```
paper_loop.start()
   ↓
_initialize_state()  (load broker positions, restore trailing stops)
   ↓
_refresh_correlation_matrix(force=True)   ← NEW: hot matrix before first signal
   ↓
loop tick 1+ — strategy generates signals, check_trade has fresh matrix
   ↓
(matrix refreshed every 30 min thereafter via the same method)
```

## Error Handling

| Failure | Detection | Behavior |
|---|---|---|
| `_refresh_correlation_matrix` raises (data access, math) | `try/except` wrap | Log DEBUG, keep prior matrix, retry next 30 min tick |
| Bootstrap on `start()` fails | `try/except` in `_initialize_state` | Log WARN, continue startup (graceful degradation per CLAUDE.md), first tick retries |
| Matrix contains NaN/Inf | `np.isfinite(matrix).all()` pre-check in `update_matrix` | Reject update, log ERROR, prior matrix preserved |
| Fewer than `bootstrap_min_assets` epics with data | `len(all_dfs) < min` check | Skip update, log INFO once per refresh cycle |
| Exposure guard at 1.0 rejects unexpected trades | Audit trail in `RiskCheckResult.audit` | Reason `"max_total_exposure_reached: X.XX >= 1.00"`; surface via `/api/risk/audit-trail` |
| Tests fail on default-value change | pytest collection | Patch fixtures in same commit |

## Testing

**Baseline:** pytest baseline from MEMORY.md is clean (0 failures,
coverage 70.59 %). Target: no regression + new coverage on bootstrap +
lifted cap + matrix validation.

### Existing tests — audit + patch

| File | Risk | Action |
|---|---|---|
| `tests/risk/test_risk_manager.py` | High | Grep for `RiskLimits(` and `max_position_pct\s*=` / `max_total_open_positions\s*=`. Patch assertions tied to old defaults. |
| `tests/risk/test_correlation_guard.py` | Low | Static-pair only — verify no `max_correlated_exposure` references. |
| `tests/trading/test_paper_loop*.py` | Medium | Verify renamed method references. Patch `_refresh_correlation_regime` mocks → split between matrix + regime methods. |
| `tests/risk/test_schemas.py` (if exists) | High | Update default-value assertions. |

### New tests

**`tests/risk/test_risk_limits_defaults.py`**
- `test_default_max_position_pct_is_010()` — `RiskLimits().max_position_pct == 0.10`
- `test_default_max_total_open_positions_is_10()` — `RiskLimits().max_total_open_positions == 10`
- `test_max_correlated_exposure_field_removed()` — `not hasattr(RiskLimits(), 'max_correlated_exposure')`

**`tests/risk/test_max_total_exposure_guard.py`**
- `test_guard_active_at_default_1_0()` — equity=10k, open pos notional=10001 → REJECT
- `test_guard_passes_below_cap()` — equity=10k, sum notional=5k → APPROVE
- `test_guard_at_099_still_works()` — back-compat for users who set 0.99

**`tests/trading/test_correlation_matrix_bootstrap.py`**
- `test_bootstrap_calls_update_matrix_once()` — mock data, assert `update_matrix` called once before first iteration
- `test_bootstrap_skips_when_flag_disabled()` — `DYNAMIC_CORRELATION_ENABLED=false`, no update
- `test_matrix_uses_full_basket()` — `self.epics` length 19, asserted `len(epics_list) == 19`
- `test_matrix_skips_when_min_assets_not_met()` — only 3 epics with data, no update

**`tests/risk/test_correlation_guard_validation.py`**
- `test_update_matrix_rejects_nan()` — matrix with NaN → not updated, prior preserved
- `test_update_matrix_rejects_inf()` — same for Inf

### Validation commands

```bash
# Baseline (capture green state pre-implementation)
cd backend && .venv/Scripts/python.exe -m pytest tests/risk/ tests/trading/ -q --tb=no

# Post-implementation
cd backend && .venv/Scripts/python.exe -m pytest tests/risk/ tests/trading/ -v
cd backend && .venv/Scripts/python.exe -m pytest tests/ -q --tb=short  # full suite confidence

# Lint / format
cd backend && .venv/Scripts/python.exe -m ruff check src/risk/ src/trading/paper_loop.py src/utils/config.py
cd backend && .venv/Scripts/python.exe -m black --check src/risk/ src/trading/paper_loop.py src/utils/config.py

# Smoke (manual, post-merge)
cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
# In log within 30 s of startup:
#   "Correlation matrix updated: N epics, shape=(N, N), mean_abs_corr=…"
```

### Pre-commit gate (superpowers:verification-before-completion)

- pytest green (0 failures, coverage ≥ 70 %)
- ruff + black clean
- Backend startup log shows matrix bootstrap
- `phase1_optuna_full_basket.py` run completes (separate background job;
  result feeds the next paper-soak milestone but is not blocking on
  this spec landing)

## Rollout

1. Land all code changes in a single commit (or stacked PR per CLAUDE.md
   git rules) on `main`. Branch prefix `feat:` per convention.
2. Backend restart picks up new defaults; matrix bootstrap runs at
   startup.
3. Manual smoke: open `/api/risk/audit-trail` after first signal tick;
   confirm `correlation.multiplier` present + `max_total_exposure`
   audit reason appears under stress test.
4. Optuna full-basket run (parallel to implementation) produces
   `optimal_thresholds_phase1_expanded_2026-05-23.json`. Review per-asset
   KEEP gate.
5. Enable expanded basket in DEMO paper trading for 14 days; monitor
   concurrent-position count distribution, correlation guard
   rejections, Kelly fraction drift, realized vs expected DD.
6. Promote to LIVE only if above gates pass.

## Open Questions / Deferred

- Per-asset Kelly stats — deferred to Phase 2 of Kelly/correlation note.
- Static correlation pair extension — deferred; dynamic matrix
  supersedes.
- `max_correlated_exposure` cluster-cap wiring — deferred; matrix
  multiplier already enforces equivalent intent.
- Portfolio heat metric (sum of risk_amount across open trades) —
  deferred; revisit before raising the position cap beyond 10.

## Artifacts

- Sibling docs: `docs/handoff/kelly_correlation_review_2026-05-23.md`,
  `docs/handoff/NEXT_SESSION_PROMPT.md`
- Phase 0 + 3 reports: `backend/docs/reports/2026-05-23_phase{0_revalidate_excluded,3_rerun}.md`
- Memory: `project_amzn_excluded_2026-05-23.md`,
  `project_spread_recalibration_2026-05-23.md`
- Optuna runner: `backend/scripts/phase1_optuna_full_basket.py`
