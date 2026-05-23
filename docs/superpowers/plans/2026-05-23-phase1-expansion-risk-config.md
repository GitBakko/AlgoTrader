# Phase 1 Expansion — Risk Config + Dynamic Correlation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconfigure the risk stack to support a 19-asset paper-trading basket (post Phase 0 ri-val 2026-05-23).

**Architecture:** Schema default cap changes (`max_position_pct` 0.20→0.10, `max_total_open_positions` 5→10), single-line semantic guard fix in risk_manager.py to activate the default total-exposure cap, split the correlation refresh in paper_loop.py into matrix-update + regime-classification (matrix gated by new `DYNAMIC_CORRELATION_ENABLED` flag, full-basket epic iteration, NaN/Inf validation), delete dead `max_correlated_exposure` field.

**Tech Stack:** Python 3.12, Pydantic v2 (settings + schemas), pytest, asyncio, numpy, loguru. Backend: `cd backend && .venv/Scripts/python.exe …`.

**Spec:** `docs/superpowers/specs/2026-05-23-phase1-expansion-risk-config-design.md`.

---

## File Structure

**Production files modified (5):**
- `backend/src/risk/schemas.py` — `RiskLimits` defaults + remove `max_correlated_exposure`
- `backend/src/risk/risk_manager.py` — guard fix `<1.0` → `<=1.0` at line 212
- `backend/src/risk/correlation_guard.py` — NaN/Inf validation in `update_matrix`
- `backend/src/utils/config.py` — new `DYNAMIC_CORRELATION_ENABLED` + `DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS` settings
- `backend/src/trading/paper_loop.py` — split `_refresh_correlation_regime`; add `_refresh_correlation_matrix`; lift `[:10]` epic cap; insert call into `_run_iteration`

**Production files unchanged but adjacent:**
- `backend/.env` — runtime overrides (`MAX_TOTAL_OPEN_POSITIONS=10`, `DYNAMIC_CORRELATION_ENABLED=true`)

**Test files modified (3):**
- `backend/tests/risk/test_risk_manager.py` — no asserts on `RiskLimits()` defaults break, but verify
- `backend/tests/trading/test_reconciler_lifecycle.py:152,170` — add `_refresh_correlation_matrix = AsyncMock()` mock alongside existing `_refresh_correlation_regime` mock

**Test files created (4):**
- `backend/tests/risk/test_risk_limits_defaults.py` — RiskLimits new defaults + field removal
- `backend/tests/risk/test_max_total_exposure_guard.py` — guard active at 1.0
- `backend/tests/risk/test_correlation_guard_validation.py` — `update_matrix` NaN/Inf rejection
- `backend/tests/trading/test_correlation_matrix_refresh.py` — full-basket epic iteration, flag gating, throttle

---

## Task 1: Capture pytest baseline

Pre-implementation green snapshot. Surface any pre-existing test fails so post-implementation diff is clean.

**Files:**
- None (read-only step)

- [ ] **Step 1: Run baseline pytest on risk + trading scopes**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/ tests/trading/ -q --tb=no 2>&1 | tail -30
```

Expected: green or short list of pre-existing failures. Record them — anything not in this list after our changes is a regression.

- [ ] **Step 2: Run full suite (lighter check)**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/ -q --tb=no 2>&1 | tail -20
```

Expected: same baseline. Per `project_test_baseline_clean_2026-05-06.md`, baseline is 0 failures. Confirm.

- [ ] **Step 3: No commit (read-only step)**

---

## Task 2: RiskLimits new defaults (TDD)

Schema-level default change. Defaults are the contract — pin them with tests.

**Files:**
- Create: `backend/tests/risk/test_risk_limits_defaults.py`
- Modify: `backend/src/risk/schemas.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/risk/test_risk_limits_defaults.py`:

```python
"""Phase 1 expansion (2026-05-23): pin new RiskLimits defaults so
schema changes are visible in code review."""

from src.risk.schemas import RiskLimits


def test_default_max_position_pct_is_010() -> None:
    """Per-position cap halved 0.20 → 0.10 to keep 100 % gross at 10 slots."""
    assert RiskLimits().max_position_pct == 0.10


def test_default_max_total_open_positions_is_10() -> None:
    """Concurrent slot cap raised 5 → 10 for 19-asset basket diversification."""
    assert RiskLimits().max_total_open_positions == 10


def test_max_correlated_exposure_field_removed() -> None:
    """Dead config — was declared but never enforced in risk_manager.py.

    Removed to avoid confusion; dynamic correlation matrix multiplier
    enforces equivalent intent.
    """
    assert "max_correlated_exposure" not in RiskLimits.model_fields


def test_default_max_total_exposure_unchanged() -> None:
    """Total-exposure cap default unchanged at 1.0 — guard fix in
    risk_manager.py activates enforcement at this default."""
    assert RiskLimits().max_total_exposure == 1.0


def test_default_max_risk_per_trade_unchanged() -> None:
    """Per-trade risk cap untouched by Phase 1 expansion."""
    assert RiskLimits().max_risk_per_trade == 0.02
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_limits_defaults.py -v
```

Expected:
- `test_default_max_position_pct_is_010` FAIL (currently 0.20)
- `test_default_max_total_open_positions_is_10` FAIL (currently 5)
- `test_max_correlated_exposure_field_removed` FAIL (field still present)
- two unchanged-default tests PASS

- [ ] **Step 3: Patch `backend/src/risk/schemas.py`**

Replace the `RiskLimits` class body (lines 28-47 approx):

```python
class RiskLimits(BaseModel):
    """Configurable risk limits for the trading system."""

    max_risk_per_trade: float = Field(default=0.02, ge=0.001, le=0.10)
    max_daily_drawdown: float = Field(default=0.05, ge=0.01, le=0.50)
    max_total_drawdown: float = Field(default=0.15, ge=0.01, le=0.50)
    max_position_pct: float = Field(
        default=0.10,
        ge=0.01,
        le=1.0,
        description=(
            "Max per-position notional as fraction of equity. "
            "Phase 1 expansion 2026-05-23: lowered 0.20 → 0.10 to keep "
            "100% gross exposure ceiling at the new 10-slot cap."
        ),
    )
    max_total_open_positions: int = Field(
        default=10,
        ge=1,
        le=50,
        description=(
            "Maximum total open positions across all assets (hard cap). "
            "Phase 1 expansion 2026-05-23: raised 5 → 10 for 19-asset basket."
        ),
    )
    max_total_exposure: float = Field(
        default=1.0,
        ge=0.01,
        le=1.0,
        description="Maximum total exposure as fraction of equity (1.0 = 100% cap, enforced).",
    )
```

Note: `max_correlated_exposure` field deleted entirely.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_limits_defaults.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Run the existing risk-manager suite to surface schema-shift fallout**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/ -q --tb=short 2>&1 | tail -40
```

Expected: no new failures. Tests in `test_risk_manager.py` that use `RiskLimits()` bare constructor (lines 495, 509) currently pass; verify still pass with new defaults (those tests assert on R:R logic, not on cap values).

If any test asserts on the old defaults (e.g. `assert limits.max_position_pct == 0.20`), patch the assertion to the new value in the same commit.

- [ ] **Step 6: Commit**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add backend/src/risk/schemas.py backend/tests/risk/test_risk_limits_defaults.py && git commit -m "feat(risk): Phase 1 expansion — RiskLimits defaults (10 slots, 0.10 pos cap)

- max_position_pct: 0.20 → 0.10
- max_total_open_positions: 5 → 10
- removed dead max_correlated_exposure field (unused in risk_manager)

Spec: docs/superpowers/specs/2026-05-23-phase1-expansion-risk-config-design.md"
```

---

## Task 3: Activate total-exposure guard at default 1.0 (TDD)

Single-line semantic fix in `risk_manager.py:212`. The guard at `< 1.0` skips the entire enforcement branch when the default is 1.0 — making the cap a no-op at the production default.

**Files:**
- Create: `backend/tests/risk/test_max_total_exposure_guard.py`
- Modify: `backend/src/risk/risk_manager.py:212`

- [ ] **Step 1: Write the failing test**

`backend/tests/risk/test_max_total_exposure_guard.py`:

```python
"""Phase 1 expansion (2026-05-23): activate the total-exposure guard
at the default MAX_TOTAL_EXPOSURE=1.0 by changing the gate from `< 1.0`
to `<= 1.0` in risk_manager.py:212."""

from unittest.mock import patch

from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.schemas import SignalDirection, TradingSignal


def _signal(epic: str = "EURUSD", entry: float = 1.10, direction: str = "BUY") -> TradingSignal:
    """Minimal BUY signal with a sane SL/TP pair (R:R = 1.0)."""
    sl = entry - 0.005 if direction == "BUY" else entry + 0.005
    tp = entry + 0.005 if direction == "BUY" else entry - 0.005
    return TradingSignal(
        epic=epic,
        timestamp=0,
        direction=getattr(SignalDirection, direction),
        confidence=0.80,
        signal_class=2 if direction == "BUY" else 0,
        entry_price=entry,
        suggested_stop=sl,
        suggested_tp=tp,
    )


def _settings_with_min_rr(min_rr: float = 0.0):
    """Settings stub with R:R floor disabled so guard alone decides."""
    from src.utils.config import Settings

    s = Settings()
    s.min_signal_rr_threshold = min_rr
    return s


def test_guard_active_at_default_1_0() -> None:
    """At MAX_TOTAL_EXPOSURE=1.0 (default), sum of open notionals beyond
    equity must be rejected. Before the fix the branch was skipped."""
    rm = RiskManager(initial_equity=10_000.0, limits=RiskLimits())  # default 1.0
    # Existing open position with notional = 10001 (just over 100% of equity)
    open_positions = [{"epic": "BTCUSD", "size": 0.1, "level": 100_010.0, "direction": "BUY"}]
    signal = _signal(epic="EURUSD")
    with patch("src.risk.risk_manager.get_settings", return_value=_settings_with_min_rr()):
        result = rm.check_trade(
            signal=signal,
            equity=10_000.0,
            atr=0.001,
            open_positions=open_positions,
        )
    assert result.approved is False
    assert "exposure" in (result.rejection_reason or "").lower()


def test_guard_passes_below_cap_at_default_1_0() -> None:
    """Sum of open notionals under equity must pass through to the next gate."""
    rm = RiskManager(initial_equity=10_000.0, limits=RiskLimits())
    open_positions = [{"epic": "BTCUSD", "size": 0.05, "level": 100_000.0, "direction": "BUY"}]
    # 0.05 * 100k = 5000 notional, well below 10k equity cap
    signal = _signal(epic="EURUSD")
    with patch("src.risk.risk_manager.get_settings", return_value=_settings_with_min_rr()):
        result = rm.check_trade(
            signal=signal,
            equity=10_000.0,
            atr=0.001,
            open_positions=open_positions,
        )
    # Not necessarily approved (other gates), but must NOT be rejected for exposure
    if not result.approved:
        assert "exposure" not in (result.rejection_reason or "").lower()


def test_guard_at_099_still_works() -> None:
    """Back-compat: users who set MAX_TOTAL_EXPOSURE=0.99 expect the same
    rejection at sum ≥ 9900."""
    rm = RiskManager(
        initial_equity=10_000.0, limits=RiskLimits(max_total_exposure=0.99)
    )
    open_positions = [{"epic": "BTCUSD", "size": 0.1, "level": 99_500.0, "direction": "BUY"}]
    signal = _signal(epic="EURUSD")
    with patch("src.risk.risk_manager.get_settings", return_value=_settings_with_min_rr()):
        result = rm.check_trade(
            signal=signal,
            equity=10_000.0,
            atr=0.001,
            open_positions=open_positions,
        )
    assert result.approved is False
    assert "exposure" in (result.rejection_reason or "").lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_max_total_exposure_guard.py -v
```

Expected:
- `test_guard_active_at_default_1_0` FAIL (currently guard is skipped at 1.0 → signal approved through this gate)
- `test_guard_passes_below_cap_at_default_1_0` PASS (covered by `_settings_with_min_rr()` neutralizing R:R floor)
- `test_guard_at_099_still_works` PASS (existing `< 1.0` already handles 0.99)

- [ ] **Step 3: Patch `backend/src/risk/risk_manager.py:212`**

Read existing context first:

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && grep -n "max_total_exposure" src/risk/risk_manager.py
```

Apply edit at the line where the guard is gated:

```python
# Before:
if self.limits.max_total_exposure < 1.0 and open_positions and equity > 0:

# After:
if self.limits.max_total_exposure <= 1.0 and open_positions and equity > 0:
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_max_total_exposure_guard.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Run adjacent risk tests to confirm no regression**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_manager.py -v --tb=short 2>&1 | tail -30
```

Expected: no new failures. Existing tests at `test_risk_manager.py` lines 210, 229, 251, 279 use `max_total_exposure=0.50` which is unaffected by `< 1.0` → `<= 1.0`.

- [ ] **Step 6: Commit**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add backend/src/risk/risk_manager.py backend/tests/risk/test_max_total_exposure_guard.py && git commit -m "fix(risk): activate MAX_TOTAL_EXPOSURE guard at default 1.0

The guard at risk_manager.py:212 was gated by '< 1.0', so the default
value 1.0 caused the entire enforcement branch to be skipped. Changed
to '<= 1.0' so the cap activates at the production default.

Existing tests using max_total_exposure=0.50 unaffected.

Spec: docs/superpowers/specs/2026-05-23-phase1-expansion-risk-config-design.md"
```

---

## Task 4: CorrelationGuard.update_matrix validation (TDD)

Reject matrices with NaN or Inf. Without validation, a downstream `1.0 - |corr|` on a NaN entry propagates to a NaN size multiplier and the trade silently sizes to zero.

**Files:**
- Create: `backend/tests/risk/test_correlation_guard_validation.py`
- Modify: `backend/src/risk/correlation_guard.py` (`update_matrix` method)

- [ ] **Step 1: Write the failing test**

`backend/tests/risk/test_correlation_guard_validation.py`:

```python
"""Phase 1 expansion (2026-05-23): CorrelationGuard.update_matrix
must reject matrices containing NaN/Inf entries. A constant-price
epic in the basket produces NaN in `np.corrcoef`; without rejection
the dynamic exposure check propagates a NaN multiplier into the
position-sizing chain (silent zero-size trade)."""

import numpy as np

from src.risk.correlation_guard import CorrelationGuard


def _baseline_matrix() -> tuple[list[str], np.ndarray]:
    epics = ["BTCUSD", "ETHUSD", "XAUUSD"]
    matrix = np.array(
        [
            [1.0, 0.7, 0.2],
            [0.7, 1.0, 0.3],
            [0.2, 0.3, 1.0],
        ],
        dtype=float,
    )
    return epics, matrix


def test_update_matrix_accepts_valid() -> None:
    guard = CorrelationGuard()
    epics, mat = _baseline_matrix()
    guard.update_matrix(epics, mat)
    assert guard.get_dynamic_correlation("BTCUSD", "ETHUSD") == 0.7


def test_update_matrix_rejects_nan() -> None:
    guard = CorrelationGuard()
    epics, mat = _baseline_matrix()
    guard.update_matrix(epics, mat)  # prime with valid matrix
    bad = mat.copy()
    bad[0, 1] = np.nan
    bad[1, 0] = np.nan
    guard.update_matrix(epics, bad)
    # Prior matrix preserved
    assert guard.get_dynamic_correlation("BTCUSD", "ETHUSD") == 0.7


def test_update_matrix_rejects_inf() -> None:
    guard = CorrelationGuard()
    epics, mat = _baseline_matrix()
    guard.update_matrix(epics, mat)
    bad = mat.copy()
    bad[2, 0] = np.inf
    bad[0, 2] = np.inf
    guard.update_matrix(epics, bad)
    assert guard.get_dynamic_correlation("BTCUSD", "XAUUSD") == 0.2


def test_update_matrix_first_call_with_nan_leaves_matrix_unset() -> None:
    """If the very first update has NaN, the matrix stays None and
    `get_dynamic_correlation` returns None (static fallback path)."""
    guard = CorrelationGuard()
    epics, mat = _baseline_matrix()
    mat[1, 2] = np.nan
    mat[2, 1] = np.nan
    guard.update_matrix(epics, mat)
    assert guard.get_dynamic_correlation("ETHUSD", "XAUUSD") is None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_correlation_guard_validation.py -v
```

Expected:
- `test_update_matrix_accepts_valid` PASS
- `test_update_matrix_rejects_nan` FAIL (matrix overwritten with NaN)
- `test_update_matrix_rejects_inf` FAIL (Inf accepted)
- `test_update_matrix_first_call_with_nan_leaves_matrix_unset` FAIL

- [ ] **Step 3: Patch `backend/src/risk/correlation_guard.py` `update_matrix`**

Read existing method at lines 59-68 first:

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && grep -n "def update_matrix" src/risk/correlation_guard.py
```

Replace the method body so the array is validated before assignment:

```python
def update_matrix(self, epics: list[str], matrix: np.ndarray) -> None:
    """Store an NxN correlation matrix for the given epics.

    Rejects matrices containing NaN or Inf entries: such values
    typically come from a constant-price epic in `np.corrcoef`
    (zero variance → divide-by-zero in the correlation formula).
    Accepting them would propagate a NaN multiplier into the
    position-sizing chain and silently zero out the trade.

    Args:
        epics: Ordered list of epic names (canonical form preferred).
        matrix: NxN numpy array of pairwise correlations.
    """
    matrix_arr = np.asarray(matrix, dtype=float)
    if not np.isfinite(matrix_arr).all():
        bad_count = int(np.sum(~np.isfinite(matrix_arr)))
        logger.error(
            f"Correlation matrix rejected: {bad_count} non-finite values "
            f"(NaN/Inf) — prior matrix preserved"
        )
        return
    self._epic_index = {_normalize_epic(e): i for i, e in enumerate(epics)}
    self._matrix = matrix_arr
    logger.info(
        f"Correlation matrix updated: {len(epics)} epics, shape={self._matrix.shape}"
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_correlation_guard_validation.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Run existing correlation-guard tests to confirm no regression**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_correlation_guard.py -v --tb=short 2>&1 | tail -20
```

Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add backend/src/risk/correlation_guard.py backend/tests/risk/test_correlation_guard_validation.py && git commit -m "fix(risk): reject NaN/Inf in CorrelationGuard.update_matrix

Constant-price epics in the 19-asset basket can produce NaN entries
in np.corrcoef (zero variance → 0/0). Without rejection the NaN
propagates to a NaN size multiplier in check_exposure_dynamic and
silently zeros out the trade with a misleading 'size zero' downstream
error. Now logs ERROR and keeps the prior matrix.

Spec: docs/superpowers/specs/2026-05-23-phase1-expansion-risk-config-design.md"
```

---

## Task 5: Settings — new DYNAMIC_CORRELATION flags (TDD)

Add the two new settings fields. Tests pin the defaults so flag drift is caught in code review.

**Files:**
- Modify: `backend/src/utils/config.py` (Settings class — append after line 224 `correlation_regime_size_reduction`)
- Add to: `backend/tests/risk/test_risk_limits_defaults.py` (extend existing file)

- [ ] **Step 1: Append failing tests to `backend/tests/risk/test_risk_limits_defaults.py`**

```python
# --- Phase 1 expansion: dynamic correlation settings ---


def test_dynamic_correlation_enabled_default_true() -> None:
    """Independent of CORRELATION_REGIME_ENABLED (Phase 2 regime gate)."""
    from src.utils.config import Settings

    assert Settings().dynamic_correlation_enabled is True


def test_dynamic_correlation_bootstrap_min_assets_default_5() -> None:
    """Need ≥5 epics with data to compute a meaningful NxN matrix."""
    from src.utils.config import Settings

    assert Settings().dynamic_correlation_bootstrap_min_assets == 5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_limits_defaults.py::test_dynamic_correlation_enabled_default_true tests/risk/test_risk_limits_defaults.py::test_dynamic_correlation_bootstrap_min_assets_default_5 -v
```

Expected: both FAIL (`AttributeError`: Settings has no attribute `dynamic_correlation_enabled`).

- [ ] **Step 3: Patch `backend/src/utils/config.py`**

Add the two new fields immediately after `correlation_regime_size_reduction` (line ~224, just before the `close_reconciliation_timeout_seconds` field at line 227):

```python
    # Phase 1 expansion 2026-05-23: dynamic correlation matrix flag,
    # decoupled from `correlation_regime_enabled` (Phase 2 panic regime).
    # When True, paper_loop refreshes the NxN correlation matrix in
    # `CorrelationGuard` every 30 min using the full self.epics basket
    # (no `[:10]` cap). Used by `RiskManager.check_trade` step 5 to
    # downsize correlated exposures via `check_exposure_dynamic`.
    dynamic_correlation_enabled: bool = Field(
        default=True, alias="DYNAMIC_CORRELATION_ENABLED"
    )
    # Minimum number of epics with sufficient candle data (>=100 bars)
    # required before computing the correlation matrix. Below this floor
    # the refresh is skipped and the prior matrix (or static-pair fallback)
    # is used.
    dynamic_correlation_bootstrap_min_assets: int = Field(
        default=5, alias="DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS"
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_limits_defaults.py -v
```

Expected: all tests in the file PASS (7 total — 5 from Task 2 + 2 new).

- [ ] **Step 5: Commit**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add backend/src/utils/config.py backend/tests/risk/test_risk_limits_defaults.py && git commit -m "feat(config): DYNAMIC_CORRELATION_ENABLED + bootstrap_min_assets

Decouples the dynamic correlation matrix refresh from the Phase 2
CORRELATION_REGIME_ENABLED flag (which stays disabled because Phase 2
failed at its own gate).

Defaults: DYNAMIC_CORRELATION_ENABLED=true,
DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS=5.

Spec: docs/superpowers/specs/2026-05-23-phase1-expansion-risk-config-design.md"
```

---

## Task 6: Split correlation refresh in paper_loop (TDD)

Introduce `_refresh_correlation_matrix` (new) and slim down
`_refresh_correlation_regime` to regime classification only. The new
method gated by `dynamic_correlation_enabled`, uses full
`self.epics`, applies the `bootstrap_min_assets` floor, and lives
next to the existing regime refresh in `_run_iteration`.

**Files:**
- Modify: `backend/src/trading/paper_loop.py`
  - Add new method `_refresh_correlation_matrix` (insert above existing `_refresh_correlation_regime` at line 955)
  - Slim `_refresh_correlation_regime` (lines 955-1012): drop the matrix-update block (lines 989-1010), keep only regime classification
  - Add new state var `self._correlation_matrix_ts: float = 0.0` in `__init__` next to `self._correlation_regime_ts` (line 320)
  - Insert `await self._refresh_correlation_matrix()` call in `_run_iteration` immediately before `await self._refresh_correlation_regime()` (line 2391)
- Create: `backend/tests/trading/test_correlation_matrix_refresh.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/trading/test_correlation_matrix_refresh.py`:

```python
"""Phase 1 expansion (2026-05-23): paper_loop._refresh_correlation_matrix
populates CorrelationGuard's dynamic matrix.

Test surface:
- Gated by DYNAMIC_CORRELATION_ENABLED flag (independent of regime gate).
- Uses full self.epics (no [:10] truncation, the old regime path's cap).
- Skips when fewer than DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS epics
  have ≥100 bars of data.
- Throttles to one refresh per 30 min unless force=True.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import polars as pl
import pytest


def _make_loop_stub(epics: list[str], candle_count: int = 200):
    """Build a minimal stub mimicking PaperTradingLoop fields used by
    _refresh_correlation_matrix.

    Returns a SimpleNamespace-like object with the attributes the method
    reads. The point is to test the method in isolation from the rest of
    the loop machinery.
    """
    from types import SimpleNamespace

    # Synthetic candles: linear trend per epic so np.corrcoef is well-defined
    def _candles(seed: int) -> pl.DataFrame:
        rng = np.random.default_rng(seed)
        close = 100.0 + np.cumsum(rng.normal(0, 1, candle_count))
        return pl.DataFrame({"close": close})

    candles_map = {epic: _candles(seed=i) for i, epic in enumerate(epics)}
    data_access = MagicMock()
    data_access.get_candles = lambda epic, *_a, **_kw: candles_map.get(epic)

    correlation_guard = MagicMock()
    risk_manager = SimpleNamespace(correlation_guard=correlation_guard)

    loop = SimpleNamespace(
        epics=epics,
        data_access=data_access,
        risk_manager=risk_manager,
        _candle_resolution="4h",
        _correlation_matrix_ts=0.0,
    )
    return loop, correlation_guard


@pytest.mark.asyncio
async def test_matrix_refresh_uses_full_basket() -> None:
    """No [:10] cap — all 19 epics with data feed the matrix."""
    from src.trading.paper_loop import PaperTradingLoop

    epics = [f"EPIC{i:02d}" for i in range(19)]
    loop, guard = _make_loop_stub(epics)

    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = True
        mock_settings.return_value.dynamic_correlation_bootstrap_min_assets = 5
        await PaperTradingLoop._refresh_correlation_matrix(loop)

    assert guard.update_matrix.called
    epics_arg, matrix_arg = guard.update_matrix.call_args[0]
    assert len(epics_arg) == 19  # full basket, not [:10]
    assert matrix_arg.shape == (19, 19)


@pytest.mark.asyncio
async def test_matrix_refresh_skips_when_flag_disabled() -> None:
    from src.trading.paper_loop import PaperTradingLoop

    loop, guard = _make_loop_stub(["BTCUSD", "ETHUSD", "XAUUSD"])
    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = False
        await PaperTradingLoop._refresh_correlation_matrix(loop)

    assert not guard.update_matrix.called


@pytest.mark.asyncio
async def test_matrix_refresh_skips_below_min_assets() -> None:
    """Only 3 epics with data, floor is 5 → no update."""
    from src.trading.paper_loop import PaperTradingLoop

    loop, guard = _make_loop_stub(["BTCUSD", "ETHUSD", "XAUUSD"])
    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = True
        mock_settings.return_value.dynamic_correlation_bootstrap_min_assets = 5
        await PaperTradingLoop._refresh_correlation_matrix(loop)

    assert not guard.update_matrix.called


@pytest.mark.asyncio
async def test_matrix_refresh_throttle_30_min() -> None:
    """Second consecutive call within 30 min must skip the update."""
    import time as _time

    from src.trading.paper_loop import PaperTradingLoop

    epics = [f"EPIC{i:02d}" for i in range(6)]
    loop, guard = _make_loop_stub(epics)

    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = True
        mock_settings.return_value.dynamic_correlation_bootstrap_min_assets = 5

        await PaperTradingLoop._refresh_correlation_matrix(loop)
        first_calls = guard.update_matrix.call_count

        # Immediate second call — must throttle
        await PaperTradingLoop._refresh_correlation_matrix(loop)
        assert guard.update_matrix.call_count == first_calls


@pytest.mark.asyncio
async def test_matrix_refresh_force_bypasses_throttle() -> None:
    """force=True bypasses the 30-min throttle (used for startup bootstrap)."""
    from src.trading.paper_loop import PaperTradingLoop

    epics = [f"EPIC{i:02d}" for i in range(6)]
    loop, guard = _make_loop_stub(epics)

    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = True
        mock_settings.return_value.dynamic_correlation_bootstrap_min_assets = 5

        await PaperTradingLoop._refresh_correlation_matrix(loop)
        await PaperTradingLoop._refresh_correlation_matrix(loop, force=True)

        assert guard.update_matrix.call_count == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/trading/test_correlation_matrix_refresh.py -v
```

Expected: all 5 tests FAIL (`AttributeError: type object 'PaperTradingLoop' has no attribute '_refresh_correlation_matrix'`).

- [ ] **Step 3: Patch `backend/src/trading/paper_loop.py` — add state var**

In `__init__`, find the line `self._correlation_regime_ts: float = 0.0` (line 320). Add immediately after:

```python
        self._correlation_matrix_ts: float = 0.0
```

- [ ] **Step 4: Patch `backend/src/trading/paper_loop.py` — add new method**

Insert this method immediately ABOVE `async def _refresh_correlation_regime` (line 955). Mind the indentation (4 spaces, inside the `PaperTradingLoop` class):

```python
    async def _refresh_correlation_matrix(self, force: bool = False) -> None:
        """Recompute pairwise correlation matrix for the full epic basket.

        Runs at most every 30 min unless ``force=True`` (used for startup
        bootstrap so the matrix is hot before the first signal tick).
        Gated by ``DYNAMIC_CORRELATION_ENABLED`` — independent from the
        Phase 2 ``CORRELATION_REGIME_ENABLED`` flag.

        Pushes the matrix into ``risk_manager.correlation_guard`` for use by
        ``check_exposure_dynamic``. On failure (data access, math, NaN/Inf)
        the prior matrix is preserved.
        """
        now = _time.monotonic()
        if not force and now - self._correlation_matrix_ts < 1800:
            return
        self._correlation_matrix_ts = now

        _settings = get_settings()
        if not _settings.dynamic_correlation_enabled:
            return

        try:
            all_dfs: dict[str, "pl.DataFrame"] = {}
            for epic in self.epics:  # full basket — no [:10]
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
                    f"{len(all_dfs)} < {min_assets} epics with sufficient data"
                )
                return

            epics_list = sorted(all_dfs.keys())
            common_len = min(len(df) for df in all_dfs.values())
            returns = np.array(
                [
                    np.diff(
                        np.log(
                            np.maximum(
                                all_dfs[e]["close"].tail(common_len).to_numpy(),
                                1e-10,
                            )
                        )
                    )
                    for e in epics_list
                ]
            )
            corr_matrix = np.corrcoef(returns)
            self.risk_manager.correlation_guard.update_matrix(epics_list, corr_matrix)

            triu = corr_matrix[np.triu_indices_from(corr_matrix, k=1)]
            mean_abs = float(np.abs(triu).mean()) if triu.size else 0.0
            logger.info(
                f"Correlation matrix refreshed: {len(epics_list)} epics, "
                f"mean|corr|={mean_abs:.3f}"
            )
        except Exception as exc:
            logger.debug(f"Correlation matrix refresh failed: {exc}")
```

- [ ] **Step 5: Patch `backend/src/trading/paper_loop.py` — slim `_refresh_correlation_regime`**

The original method at lines 955-1012 contains both the regime classification AND the matrix update (lines 989-1010 inside the try block). Delete the matrix-update block from `_refresh_correlation_regime` so it only does regime classification. New body:

```python
    async def _refresh_correlation_regime(self) -> None:
        """Classify cross-asset correlation regime (panic vs normal).

        Gated by ``CORRELATION_REGIME_ENABLED`` (Phase 2 flag, currently
        disabled in production). Matrix population was moved to
        ``_refresh_correlation_matrix``.
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
            all_dfs: dict[str, "pl.DataFrame"] = {}
            for epic in self.epics[:10]:
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
                        f"Correlation regime: {self._correlation_regime} "
                        f"(mean={mean_corr:.3f})"
                    )
        except Exception as exc:
            logger.debug(f"Correlation regime update failed: {exc}")
```

- [ ] **Step 6: Patch `backend/src/trading/paper_loop.py` — add call in `_run_iteration`**

At line 2391, the existing code is:

```python
        await self._refresh_spread_blocks()
        await self._refresh_correlation_regime()
        self._init_regime_gate()
```

Replace with:

```python
        await self._refresh_spread_blocks()
        await self._refresh_correlation_matrix()
        await self._refresh_correlation_regime()
        self._init_regime_gate()
```

- [ ] **Step 7: Run new tests to verify they pass**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/trading/test_correlation_matrix_refresh.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 8: Patch reconciler-lifecycle test mocks**

Edit `backend/tests/trading/test_reconciler_lifecycle.py` lines 151-153 and 169-171. Add a `_refresh_correlation_matrix` mock alongside the existing `_refresh_correlation_regime` mock so the new call doesn't try real data access:

```python
    loop.get_positions_async = AsyncMock(return_value=[])
    loop._refresh_spread_blocks = AsyncMock()
    loop._refresh_correlation_matrix = AsyncMock()  # NEW
    loop._refresh_correlation_regime = AsyncMock()
    loop._init_regime_gate = MagicMock()
```

Apply to BOTH `test_strategy_loop_skips_reconciler_calls_when_enabled` and `test_strategy_loop_calls_reconciler_methods_when_disabled`.

- [ ] **Step 9: Run reconciler-lifecycle tests + full trading suite**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/trading/test_reconciler_lifecycle.py tests/trading/test_correlation_matrix_refresh.py -v
```

Expected: all PASS.

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/trading/ -q --tb=short 2>&1 | tail -30
```

Expected: no new failures vs Task 1 baseline.

- [ ] **Step 10: Commit**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add backend/src/trading/paper_loop.py backend/tests/trading/test_correlation_matrix_refresh.py backend/tests/trading/test_reconciler_lifecycle.py && git commit -m "feat(paper_loop): split correlation refresh — matrix decoupled from regime

Introduces _refresh_correlation_matrix gated by DYNAMIC_CORRELATION_ENABLED,
using the full self.epics basket (no [:10] cap that was carried over from
the legacy regime path). Slims _refresh_correlation_regime down to its
classification role (Phase 2 panic regime, still gated by the same legacy
flag).

Hooked into _run_iteration immediately after _refresh_spread_blocks so
the matrix is hot before signal generation on every tick (and on first
iteration acts as the startup bootstrap — _correlation_matrix_ts=0).

Reconciler-lifecycle tests updated with the new AsyncMock.

Spec: docs/superpowers/specs/2026-05-23-phase1-expansion-risk-config-design.md"
```

---

## Task 7: Backend .env runtime overrides

Persist the new caps + flag in the runtime env so a stale `.env` doesn't
silently downgrade behavior on the next backend restart.

**Files:**
- Modify: `backend/.env`

- [ ] **Step 1: Inspect current `.env` to find existing risk section**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && grep -nE "MAX_TOTAL_OPEN_POSITIONS|MAX_TOTAL_EXPOSURE|MAX_POSITION_PCT|MAX_RISK_PER_TRADE|CORRELATION" backend/.env || true
```

Expected: existing risk-management entries visible (some likely set, some at default).

- [ ] **Step 2: Append (or update in place) the following keys**

In `backend/.env`, ensure these lines exist (add or replace existing values):

```
# Phase 1 expansion 2026-05-23 — 19-asset basket
MAX_TOTAL_OPEN_POSITIONS=10
DYNAMIC_CORRELATION_ENABLED=true
# DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS=5  (uses default)
# MAX_POSITION_PCT=0.10  (uses RiskLimits default)
# MAX_TOTAL_EXPOSURE=1.0 (uses RiskLimits default — now enforced after guard fix)
```

If a previous `MAX_TOTAL_OPEN_POSITIONS=` line is already present with a different value, replace it. Same for `DYNAMIC_CORRELATION_ENABLED=` if present.

- [ ] **Step 3: Verify Settings picks up the new values**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -c "from src.utils.config import get_settings; s = get_settings(); print('dyn_corr=', s.dynamic_correlation_enabled); print('regime=', s.correlation_regime_enabled)"
```

Expected: `dyn_corr= True` and `regime=` matches existing value (likely False).

- [ ] **Step 4: No commit yet — `.env` is gitignored**

Per CLAUDE.md "Never commit: `.env`". This step is operational only.

---

## Task 8: Full-suite regression check

Run the complete backend pytest after all code changes. Compare to Task 1 baseline.

**Files:**
- None (validation only)

- [ ] **Step 1: Run full pytest**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/ -q --tb=short 2>&1 | tail -40
```

Expected: 0 new failures vs Task 1 baseline. If any new failure appears, fix in the same task it belongs to (Task 2-6) before continuing.

- [ ] **Step 2: Coverage threshold check (CI gate is 70 %)**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m pytest tests/ --cov=src --cov-report=term-missing -q --tb=no 2>&1 | tail -15
```

Expected: `TOTAL` coverage line shows ≥ 70 %.

- [ ] **Step 3: Lint + format**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m ruff check src/risk/ src/trading/paper_loop.py src/utils/config.py 2>&1 | tail -20
```

Expected: 0 errors. If any, fix in place.

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m black --check src/risk/ src/trading/paper_loop.py src/utils/config.py
```

Expected: "All done!" / "would be left unchanged". If black wants reformat, run without `--check` and commit any diff under a `style:` prefix.

- [ ] **Step 4: No commit unless lint produced diffs**

If `black` reformatted files in Step 3, commit:

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add backend/src/ && git commit -m "style: black auto-format after Phase 1 expansion code changes"
```

---

## Task 9: Manual smoke — backend startup + matrix bootstrap

Confirm the matrix refresh actually fires when the backend starts.

**Files:**
- None (operational check)

- [ ] **Step 1: Check backend already running on :8000**

```bash
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
```

If listening, kill it (the user controls this — confirm before kill):

```bash
# Only if user authorises restart
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "uvicorn" } | Stop-Process
```

- [ ] **Step 2: Start backend in background and read the log file**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader/backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > D:/tmp/algotrader/backend_smoke.log 2>&1 &
```

Wait ~60 s for the loop to fire once (the matrix refresh runs inside `_run_iteration`):

```bash
sleep 60 && grep -E "Correlation matrix (refreshed|update skipped)" D:/tmp/algotrader/backend_smoke.log
```

Expected one of:
- `Correlation matrix refreshed: N epics, mean|corr|=…` — bootstrap fired and matrix hot.
- `Correlation matrix update skipped: M < 5 epics with sufficient data` — graceful degradation, expected if local parquet history is sparse on dev box.

A silent startup (no match for either pattern) is the failure mode — means the new method never ran.

Kill the smoke backend after the check:

```bash
Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match "uvicorn" } | Stop-Process
```

- [ ] **Step 3: Hit risk endpoint to surface the new exposure-cap audit reason**

```bash
curl -s http://localhost:8000/api/risk/audit-trail?limit=5 | python -m json.tool 2>&1 | head -30
```

Optional — only useful once paper trading is started and signals flow.

- [ ] **Step 4: No commit (operational)**

---

## Task 10: Update handoff doc with discovered state

The Kelly/correlation review note (`docs/handoff/kelly_correlation_review_2026-05-23.md`) was written before discovering the dynamic correlation infra already existed. Adjust §5 to reflect the actual decoupling.

**Files:**
- Modify: `docs/handoff/kelly_correlation_review_2026-05-23.md` (§5)

- [ ] **Step 1: Locate the existing §5 block**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && grep -n "## 5\." docs/handoff/kelly_correlation_review_2026-05-23.md
```

- [ ] **Step 2: Replace §5 body with the implemented behavior**

In `docs/handoff/kelly_correlation_review_2026-05-23.md`, the section currently proposes adding a new flag. After implementation the actual state is: a new flag was added (`DYNAMIC_CORRELATION_ENABLED`) AND the matrix population was split out of `_refresh_correlation_regime` (which previously gated EVERYTHING under `correlation_regime_enabled`) AND the `[:10]` cap was lifted.

Update the note's §5 to reflect:

```markdown
## 5. Correlation guard — dynamic matrix (IMPLEMENTED 2026-05-23)

The dynamic correlation matrix is now populated by
`paper_loop._refresh_correlation_matrix` (split out of the legacy
`_refresh_correlation_regime`) and consumed by
`RiskManager.check_trade` step 5 via
`correlation_guard.check_exposure_dynamic`.

Flags:
- `DYNAMIC_CORRELATION_ENABLED=true` (default, new) — gates the matrix
  refresh. Decoupled from `CORRELATION_REGIME_ENABLED` (Phase 2 panic
  regime gate, separate experiment).
- `DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS=5` (default, new) — floor on
  how many epics with ≥100 bars are needed before refresh runs.

Coverage: full `self.epics` basket (was `[:10]` in the legacy path).

Validation: `CorrelationGuard.update_matrix` now rejects matrices with
NaN/Inf entries (constant-price epic in `np.corrcoef`). Prior matrix
preserved on rejection.

See `docs/superpowers/plans/2026-05-23-phase1-expansion-risk-config.md`
Task 5 + Task 6 for implementation detail.
```

- [ ] **Step 3: Commit**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add docs/handoff/kelly_correlation_review_2026-05-23.md && git commit -m "docs(kelly-review): §5 reflect implemented dynamic correlation split

Initial note proposed adding a new flag; implementation also split
matrix population from regime classification and lifted [:10] cap."
```

---

## Task 11: Optuna full-basket result review

The 19-asset Optuna run was launched in parallel during implementation. By now it should have produced the thresholds file. Review per-asset KEEP gate.

**Files:**
- Read: `backend/data/config/optimal_thresholds_phase1_expanded_2026-05-23.json`
- Read: `D:/tmp/algotrader/phase1_expanded.log`

- [ ] **Step 1: Confirm Optuna run completed**

```bash
tail -50 D:/tmp/algotrader/phase1_expanded.log
```

Expected: `Phase 1 expansion gate:` block at the end with `Per-asset KEEP gate: N / 19 pass`, `Median Sharpe`, `Mean Sharpe`, `Top-5 mean Sharpe vs Phase 3 re-run`, and `Aggregate verdict: PASS|FAIL`.

If still running, wait (`tail -f` until "All backtests complete." or aggregate verdict line). If FAILED, capture the failed epic from the log and decide: re-run with adjusted prune-pct, or KEEP-by-exception with a note in the next handoff.

- [ ] **Step 2: Verify thresholds JSON exists**

```bash
ls -la D:/Develop/AI/_ClaudeCode/AlgoTrader/backend/data/config/optimal_thresholds_phase1_expanded_2026-05-23.json
```

Expected: file exists, non-zero size.

- [ ] **Step 3: Read aggregate verdict + per-asset KEEP count**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && grep -E "Per-asset KEEP|Median Sharpe|Mean Sharpe|Top-5 mean Sharpe|Aggregate verdict" D:/tmp/algotrader/phase1_expanded.log | tail -10
```

- [ ] **Step 4: If aggregate PASS, write a result handoff snapshot**

Create `backend/docs/reports/2026-05-23_phase1_expansion_optuna.md` with:
- Date, command, basket (19 assets), tune-trials 100, prune-pct 0.25
- Per-asset scorecard table (sourced from log)
- Aggregate gate verdict (Per-asset KEEP %, median Sharpe, mean Sharpe, top-5 regression vs 3.95)
- Next-step recommendation (enable expanded basket in paper trading? defer per-asset Kelly?)

- [ ] **Step 5: Commit (if Step 4 ran)**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add backend/data/config/optimal_thresholds_phase1_expanded_2026-05-23.json backend/docs/reports/2026-05-23_phase1_expansion_optuna.md && git commit -m "docs(phase1): expansion Optuna 100-trial result report (19-asset basket)"
```

---

## Task 12: Update NEXT_SESSION_PROMPT with new state

Close the loop on the handoff prompt so a fresh session can pick up at the next milestone (paper soak / Binance migration prep).

**Files:**
- Modify: `docs/handoff/NEXT_SESSION_PROMPT.md`

- [ ] **Step 1: Edit `docs/handoff/NEXT_SESSION_PROMPT.md`**

Update the "Stato roadmap evolution" section: change `⏳ Phase 1 expansion 19-asset basket — NEXT` to `✅ Phase 1 expansion 19-asset basket (2026-05-23) — DONE + risk-config landed`. Add a new `⏳ NEXT` item for the 2-week paper soak validation milestone.

Update "Priorità prossima sessione" to reflect the soak + Kelly per-asset (Phase 2 of the Kelly review note) being the new ALTA.

- [ ] **Step 2: Commit**

```bash
cd D:/Develop/AI/_ClaudeCode/AlgoTrader && git add docs/handoff/NEXT_SESSION_PROMPT.md && git commit -m "docs(handoff): Phase 1 expansion DONE — paper soak now NEXT"
```

---

## Done criteria (all green to claim completion)

- [ ] Task 1 baseline captured (pre-implementation)
- [ ] Tasks 2-6 each green: new tests pass + adjacent tests unchanged
- [ ] Task 7 `.env` reflects new flag + cap
- [ ] Task 8 full pytest = 0 new failures vs baseline; coverage ≥ 70 %; ruff + black clean
- [ ] Task 9 backend startup log shows matrix refresh attempt (success or graceful skip)
- [ ] Task 10 handoff doc reflects implemented state
- [ ] Task 11 Optuna run reviewed + report saved (PASS or documented fail)
- [ ] Task 12 NEXT_SESSION_PROMPT updated

If any "Done criteria" item flips off between tasks, that's a regression — fix before continuing.
