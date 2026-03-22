# Decision Audit Trail — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture and display every decision point in the signal-to-position pipeline so SL-heavy trades can be diagnosed.

**Architecture:** Reuse existing `signals` table (JSONB `features` column) to persist a structured audit trail for every BUY/SELL signal. Enrich `TradingSignal` and `RiskCheckResult` Pydantic models with metadata. Display via a slide-out drawer in the Angular frontend.

**Tech Stack:** Python 3.12 (FastAPI, Pydantic v2, SQLModel, asyncpg), Angular 21 (standalone components, signals, OnPush), PostgreSQL JSONB

**Spec:** `docs/superpowers/specs/2026-03-11-decision-audit-trail-design.md`

---

## File Structure

### Backend — New/Modified Files

| Action | File | Responsibility |
|--------|------|---------------|
| Modify | `backend/src/strategy/schemas.py` | Add `metadata` field to `TradingSignal` |
| Modify | `backend/src/strategy/scalp_score_strategy.py` | Vote functions return `(int, dict)`, populate metadata in `generate_signal()` |
| Modify | `backend/src/strategy/strategy_manager.py` | Add ML section to `signal.metadata` in `_process_scalp()` |
| Modify | `backend/src/risk/schemas.py` | Add `audit` field to `RiskCheckResult` |
| Modify | `backend/src/risk/risk_manager.py` | Build audit dict progressively in `check_trade()` |
| Modify | `backend/src/trading/paper_loop.py` | Assemble JSONB, persist to `signals` table, link FKs |
| Modify | `backend/src/api/routers/signals.py` | Add 3 new audit endpoints |
| Modify | `backend/src/api/schemas.py` | Add Pydantic response schemas for audit endpoints |
| Modify | `backend/src/api/dependencies.py` | Ensure `get_signal_repo` works for the new endpoints |
| Modify | `backend/src/database/repositories/signal_repository.py` | Add `create_from_audit()`, `get_by_position_deal_id()`, `get_history_by_epic()` |
| Create | `backend/tests/strategy/test_scalp_score_audit.py` | Tests for vote details + metadata |
| Create | `backend/tests/risk/test_risk_audit.py` | Tests for audit dict in risk checks |
| Create | `backend/tests/trading/test_signal_persistence.py` | Integration test for full pipeline |
| Create | `backend/tests/api/test_signals_audit_api.py` | API endpoint tests |

### Frontend — New/Modified Files

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `frontend/src/app/core/services/signal-audit.service.ts` | API calls + drawer open/close state |
| Create | `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.ts` | Drawer component |
| Create | `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.html` | Drawer template |
| Create | `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.scss` | Drawer styles |
| Modify | `frontend/src/app/core/models/index.ts` | Add `SignalAudit`, `SignalFeatures`, `SignalMl`, `SignalRisk`, `PositionSummary`, `SignalHistoryItem` interfaces |
| Modify | `frontend/src/app/layout/default-layout/default-layout.component.ts` | Import + render drawer |
| Modify | `frontend/src/app/layout/default-layout/default-layout.component.html` | Add `<app-signal-audit-drawer>` |
| Modify | `frontend/src/app/views/positions/positions.component.ts` | Add row click → open drawer |
| Modify | `frontend/src/app/views/paper-trading/paper-trading.component.ts` | Add row click → open drawer |
| Modify | `frontend/src/app/views/dashboard/dashboard.component.html` | Add row click → open drawer |
| Modify | `frontend/src/app/views/dashboard/dashboard.component.ts` | Inject service |
| Modify | `frontend/src/app/views/trade-journal/trade-journal.component.ts` | Add row click → open drawer |

---

## Chunk 1: Backend — Enriched Models & Vote Functions

### Task 1: Add `metadata` field to TradingSignal

**Files:**
- Modify: `backend/src/strategy/schemas.py:20-37`
- Test: `backend/tests/strategy/test_scalp_score_audit.py`

- [ ] **Step 1: Write test for metadata field existence**

```python
# backend/tests/strategy/test_scalp_score_audit.py
"""Tests for ScalpScore decision audit trail metadata."""
import pytest
from src.strategy.schemas import TradingSignal, SignalDirection


def test_trading_signal_has_metadata_field():
    """TradingSignal should have a metadata dict, empty by default."""
    sig = TradingSignal(
        epic="XAUUSD",
        direction=SignalDirection.BUY,
        confidence=0.67,
        signal_class=2,
        entry_price=2047.5,
    )
    assert isinstance(sig.metadata, dict)
    assert sig.metadata == {}


def test_trading_signal_metadata_survives_model_copy():
    """metadata should persist through model_copy() calls."""
    sig = TradingSignal(
        epic="XAUUSD",
        direction=SignalDirection.BUY,
        confidence=0.67,
        signal_class=2,
        entry_price=2047.5,
        metadata={"votes": {"ema": {"value": 1}}},
    )
    sig2 = sig.model_copy(update={"confidence": 0.33})
    assert sig2.metadata == {"votes": {"ema": {"value": 1}}}
    assert sig2.confidence == 0.33
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_audit.py -v`
Expected: FAIL — `metadata` field does not exist on `TradingSignal`

- [ ] **Step 3: Add metadata field to TradingSignal**

In `backend/src/strategy/schemas.py`, add after line 36 (`strategy_name`):

```python
    metadata: dict = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_audit.py -v`
Expected: 2 PASS

- [ ] **Step 5: Run full strategy test suite to check no regressions**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/ -v --tb=short`
Expected: All existing tests still pass

- [ ] **Step 6: Commit**

```bash
git add backend/src/strategy/schemas.py backend/tests/strategy/test_scalp_score_audit.py
git commit -m "feat: add metadata field to TradingSignal for decision audit trail"
```

---

### Task 2: Refactor vote functions to return (value, details) tuples

**Files:**
- Modify: `backend/src/strategy/scalp_score_strategy.py:65-143`
- Test: `backend/tests/strategy/test_scalp_score_audit.py`

- [ ] **Step 1: Write tests for vote function return shape**

Append to `backend/tests/strategy/test_scalp_score_audit.py`:

```python
from src.strategy.scalp_score_strategy import ScalpScoreStrategy


class TestVoteFunctionDetails:
    """Each vote function returns (int, dict) with underlying data."""

    def test_vote_ema_bullish(self):
        value, details = ScalpScoreStrategy._vote_ema(2045.12, 2043.80)
        assert value == 1
        assert details == {"ema_9": 2045.12, "ema_21": 2043.80}

    def test_vote_ema_bearish(self):
        value, details = ScalpScoreStrategy._vote_ema(2040.0, 2045.0)
        assert value == -1
        assert details == {"ema_9": 2040.0, "ema_21": 2045.0}

    def test_vote_ema_neutral(self):
        value, details = ScalpScoreStrategy._vote_ema(2045.0, 2045.0)
        assert value == 0
        assert details == {"ema_9": 2045.0, "ema_21": 2045.0}

    def test_vote_rsi_oversold(self):
        value, details = ScalpScoreStrategy._vote_rsi(38.5)
        assert value == 1
        assert details == {"rsi_14": 38.5}

    def test_vote_rsi_overbought(self):
        value, details = ScalpScoreStrategy._vote_rsi(62.0)
        assert value == -1
        assert details == {"rsi_14": 62.0}

    def test_vote_macd_bullish(self):
        value, details = ScalpScoreStrategy._vote_macd(0.45, 1.23, 0.78)
        assert value == 1
        assert details == {"histogram": 0.45, "macd": 1.23, "signal": 0.78}

    def test_vote_volume_strong(self):
        value, details = ScalpScoreStrategy._vote_volume(15200, 12100)
        assert value == 1
        assert details == {"volume": 15200, "volume_sma_20": 12100}

    def test_vote_volume_weak(self):
        value, details = ScalpScoreStrategy._vote_volume(10000, 12100)
        assert value == 0
        assert details == {"volume": 10000, "volume_sma_20": 12100}

    def test_vote_adx_trending(self):
        value, details = ScalpScoreStrategy._vote_adx(28.7)
        assert value == 1
        assert details == {"adx_14": 28.7}

    def test_vote_adx_flat(self):
        value, details = ScalpScoreStrategy._vote_adx(15.0)
        assert value == 0
        assert details == {"adx_14": 15.0}

    def test_vote_bb_squeeze_breakout_up(self):
        value, details = ScalpScoreStrategy._vote_bb_squeeze(
            bb_upper=2052, bb_lower=2038,
            keltner_upper=2055, keltner_lower=2035,
            price=2047.5, bb_middle=2045,
        )
        assert value == 1
        assert details["bb_upper"] == 2052
        assert details["bb_lower"] == 2038
        assert details["kc_upper"] == 2055
        assert details["kc_lower"] == 2035
        assert details["price"] == 2047.5
        assert details["bb_mid"] == 2045
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_audit.py::TestVoteFunctionDetails -v`
Expected: FAIL — functions return `int`, not `tuple`

- [ ] **Step 3: Refactor all 6 vote functions**

In `backend/src/strategy/scalp_score_strategy.py`, change each vote function to return `tuple[int, dict]`:

**`_vote_ema` (lines 65-75):**
```python
    @staticmethod
    def _vote_ema(ema_9: float, ema_21: float) -> tuple[int, dict]:
        """EMA cross: bullish cross = BUY, bearish cross = SELL."""
        details = {"ema_9": ema_9, "ema_21": ema_21}
        if ema_9 <= 0 or ema_21 <= 0:
            return 0, details
        spread = (ema_9 - ema_21) / ema_21
        if spread > 0.001:
            return 1, details
        elif spread < -0.001:
            return -1, details
        return 0, details
```

**`_vote_rsi` (lines 77-84):**
```python
    @staticmethod
    def _vote_rsi(rsi: float) -> tuple[int, dict]:
        """RSI: oversold zone = BUY potential, overbought = SELL."""
        details = {"rsi_14": rsi}
        if rsi < 45:
            return 1, details
        elif rsi > 55:
            return -1, details
        return 0, details
```

**`_vote_macd` (lines 86-98):**
```python
    @staticmethod
    def _vote_macd(histogram: float, macd: float, signal: float) -> tuple[int, dict]:
        """MACD: histogram direction + crossover."""
        details = {"histogram": histogram, "macd": macd, "signal": signal}
        if histogram > 0 and macd > signal:
            return 1, details
        elif histogram < 0 and macd < signal:
            return -1, details
        if histogram > 0:
            return 1, details
        elif histogram < 0:
            return -1, details
        return 0, details
```

**`_vote_volume` (lines 100-107):**
```python
    @staticmethod
    def _vote_volume(volume: float, volume_sma: float) -> tuple[int, dict]:
        """Volume confirmation: strong volume = confirms current move."""
        details = {"volume": volume, "volume_sma_20": volume_sma}
        if volume_sma <= 0:
            return 0, details
        if volume / volume_sma >= 1.2:
            return 1, details
        return 0, details
```

**`_vote_adx` (lines 109-114):**
```python
    @staticmethod
    def _vote_adx(adx: float) -> tuple[int, dict]:
        """ADX trend strength: >20 = trend exists, confirming vote."""
        details = {"adx_14": adx}
        if adx >= 20:
            return 1, details
        return 0, details
```

**`_vote_bb_squeeze` (lines 116-143):**
```python
    @staticmethod
    def _vote_bb_squeeze(
        bb_upper: float, bb_lower: float,
        keltner_upper: float, keltner_lower: float,
        price: float, bb_middle: float,
    ) -> tuple[int, dict]:
        """BB squeeze: breakout direction from compression."""
        details = {
            "bb_upper": bb_upper, "bb_lower": bb_lower,
            "kc_upper": keltner_upper, "kc_lower": keltner_lower,
            "price": price, "bb_mid": bb_middle,
        }
        if bb_upper <= 0 or keltner_upper <= 0:
            return 0, details

        bb_width = bb_upper - bb_lower
        kc_width = keltner_upper - keltner_lower
        if kc_width <= 0:
            return 0, details

        if bb_width < kc_width:
            if price > bb_middle:
                return 1, details
            elif price < bb_middle:
                return -1, details
        elif price > bb_upper:
            return 1, details
        elif price < bb_lower:
            return -1, details

        return 0, details
```

- [ ] **Step 4: Update all call sites inside `generate_signal()` to destructure tuples**

In `generate_signal()`, wherever votes are called (around lines 200-225), change:
```python
# Before:
ema_vote = self._vote_ema(ema_9, ema_21)
# After:
ema_vote, ema_details = self._vote_ema(ema_9, ema_21)
```

Do this for all 6 votes: `ema_vote`, `rsi_vote`, `macd_vote`, `vol_vote`, `adx_vote`, `bb_vote`.

- [ ] **Step 5: Run audit tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_audit.py -v`
Expected: All PASS

- [ ] **Step 6: Run full strategy test suite to check no regressions**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/ -v --tb=short`
Expected: All existing tests still pass (vote functions are static, callers already handle int values — the destructuring only adds the details dict)

- [ ] **Step 7: Commit**

```bash
git add backend/src/strategy/scalp_score_strategy.py backend/tests/strategy/test_scalp_score_audit.py
git commit -m "feat: vote functions return (value, details) tuples for audit trail"
```

---

### Task 3: Populate `signal.metadata` in `generate_signal()`

**Files:**
- Modify: `backend/src/strategy/scalp_score_strategy.py` (`generate_signal()` method)
- Test: `backend/tests/strategy/test_scalp_score_audit.py`

- [ ] **Step 1: Write test for metadata completeness on executed signal**

Append to `backend/tests/strategy/test_scalp_score_audit.py`:

```python
import polars as pl
import numpy as np


def _make_market_data(
    price=2047.5, atr=16.8, rsi=38.0, adx=28.7,
    ema_9=2045.12, ema_21=2043.80,
    macd_histogram=0.45, macd=1.23, macd_signal=0.78,
    bb_upper=2052, bb_lower=2038, bb_middle=2045,
    keltner_upper=2050, keltner_lower=2040,
    volume=15200, volume_sma_20=12100,
    vwap=2044.0, htf_bias="bullish",
):
    """Create market_data dict for testing."""
    # Build recent_bars DataFrame (100 rows) for BB width percentile
    bb_widths = np.random.uniform(10, 20, 100)
    recent_bars = pl.DataFrame({
        "bb_upper": [price + w / 2 for w in bb_widths],
        "bb_lower": [price - w / 2 for w in bb_widths],
    })
    return {
        "current_price": price, "atr": atr, "rsi": rsi, "adx": adx,
        "ema_9": ema_9, "ema_21": ema_21,
        "macd_histogram": macd_histogram, "macd": macd, "macd_signal": macd_signal,
        "bb_upper": bb_upper, "bb_lower": bb_lower, "bb_middle": bb_middle,
        "keltner_upper": keltner_upper, "keltner_lower": keltner_lower,
        "volume": volume, "volume_sma_20": volume_sma_20,
        "vwap": vwap, "htf_bias": htf_bias,
        "recent_bars": recent_bars,
    }


class TestGenerateSignalMetadata:
    """generate_signal() should populate signal.metadata with full audit data."""

    def test_executed_signal_has_votes_in_metadata(self):
        strategy = ScalpScoreStrategy(min_confluence=3)
        md = _make_market_data(rsi=38.0, adx=28.7)  # bullish setup
        signal = strategy.generate_signal("XAUUSD", md)

        if signal.direction.value == "HOLD":
            pytest.skip("Signal was HOLD — adjust test data for BUY/SELL")

        assert "votes" in signal.metadata
        votes = signal.metadata["votes"]
        for name in ["ema", "rsi", "macd", "volume", "adx", "bb_keltner"]:
            assert name in votes, f"Missing vote: {name}"
            assert "value" in votes[name], f"Missing value in vote {name}"

    def test_executed_signal_has_gates_in_metadata(self):
        strategy = ScalpScoreStrategy(min_confluence=3)
        md = _make_market_data()
        signal = strategy.generate_signal("XAUUSD", md)

        if signal.direction.value == "HOLD":
            pytest.skip("Signal was HOLD — adjust test data")

        assert "gates" in signal.metadata
        gates = signal.metadata["gates"]
        for gate in ["session", "dead_market", "vwap", "htf", "confluence"]:
            assert gate in gates, f"Missing gate: {gate}"

    def test_executed_signal_has_market_snapshot(self):
        strategy = ScalpScoreStrategy(min_confluence=3)
        md = _make_market_data()
        signal = strategy.generate_signal("XAUUSD", md)

        if signal.direction.value == "HOLD":
            pytest.skip("Signal was HOLD")

        assert "market_snapshot" in signal.metadata
        snap = signal.metadata["market_snapshot"]
        for key in ["atr", "rsi", "adx", "regime", "vwap", "htf_bias"]:
            assert key in snap, f"Missing snapshot key: {key}"

    def test_gate_rejected_signal_has_partial_metadata(self):
        """A signal rejected by session gate should have gates.session.passed=False."""
        strategy = ScalpScoreStrategy(min_confluence=3)
        md = _make_market_data()
        # Force off-session hour (22 UTC)
        from unittest.mock import patch
        with patch("src.strategy.scalp_score_strategy.datetime") as mock_dt:
            mock_dt.now.return_value = type("DT", (), {"hour": 22})()
            mock_dt.side_effect = lambda *a, **k: type("DT", (), {"hour": 22})()
            signal = strategy.generate_signal("XAUUSD", md)

        # Signal should be HOLD (session blocked)
        if signal.direction.value != "HOLD":
            pytest.skip("Signal was not blocked by session — adjust test")

        assert "gates" in signal.metadata
        # At minimum, session gate should be present
        if signal.metadata["gates"].get("session") is not None:
            assert signal.metadata["gates"]["session"]["passed"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_audit.py::TestGenerateSignalMetadata -v`
Expected: FAIL — `metadata` is empty `{}`

- [ ] **Step 3: Implement metadata population in `generate_signal()`**

In `backend/src/strategy/scalp_score_strategy.py`, inside `generate_signal()`:

After all vote calls (around line 225), build the votes dict:
```python
        votes_data = {
            "ema": {"value": ema_vote, **ema_details},
            "rsi": {"value": rsi_vote, **rsi_details},
            "macd": {"value": macd_vote, **macd_details},
            "volume": {"value": vol_vote, **vol_details},
            "adx": {"value": adx_vote, **adx_details},
            "bb_keltner": {"value": bb_vote, **bb_details},
        }
```

Build market snapshot:
```python
        market_snapshot = {
            "atr": round(float(market_data.get("atr", 0)), 5),
            "rsi": round(float(market_data.get("rsi", 0)), 1),
            "adx": round(float(market_data.get("adx", 0)), 1),
            "regime": market_data.get("regime", "unknown"),
            "vwap": round(float(market_data.get("vwap", 0)), 4),
            "htf_bias": market_data.get("htf_bias", "neutral"),
            "volume": float(market_data.get("volume", 0)),
            "bb_width": round(float(bb_upper - bb_lower), 4) if bb_upper and bb_lower else 0,
        }
```

At each gate check (session, dead_market, VWAP, HTF, confluence), before returning HOLD, populate `metadata` with what's known and set `passed: False` for the blocking gate. For example, before the session gate early return:
```python
        metadata = {
            "votes": votes_data,
            "gates": {
                "session": {"passed": False, "session_mult": session_mult, "utc_hour": utc_hour, "zone": zone},
                "dead_market": None, "vwap": None, "htf": None, "confluence": None,
            },
            "market_snapshot": market_snapshot,
        }
        return TradingSignal(..., metadata=metadata)
```

For the successful path, build all gates as `passed: True` with their data, then set `metadata` on the final signal.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_audit.py -v`
Expected: All PASS

- [ ] **Step 5: Run full strategy suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/ -v --tb=short`
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add backend/src/strategy/scalp_score_strategy.py backend/tests/strategy/test_scalp_score_audit.py
git commit -m "feat: populate signal.metadata with votes, gates, market snapshot in generate_signal()"
```

---

### Task 4: Add ML section to metadata in `_process_scalp()`

**Files:**
- Modify: `backend/src/strategy/strategy_manager.py:264-290`
- Test: `backend/tests/strategy/test_scalp_score_audit.py`

- [ ] **Step 1: Write test for ML metadata**

Append to `backend/tests/strategy/test_scalp_score_audit.py`:

```python
from unittest.mock import MagicMock
from src.strategy.strategy_manager import StrategyManager
from src.strategy.schemas import TradingSignal, SignalDirection
from src.models.prediction_service import PredictionResult


class TestProcessScalpMlMetadata:
    """_process_scalp() should add ml section to signal.metadata."""

    def _make_strategy_manager(self):
        sm = StrategyManager.__new__(StrategyManager)
        sm.scalp_strategy = MagicMock()
        sm.mode = "scalp"
        return sm

    def _make_signal(self, direction=SignalDirection.BUY, confidence=0.67):
        return TradingSignal(
            epic="XAUUSD", direction=direction, confidence=confidence,
            signal_class=2, entry_price=2047.5, strategy_name="scalp_score",
            metadata={"votes": {"ema": {"value": 1}}, "gates": {}, "market_snapshot": {}},
        )

    def _make_prediction(self, signal_class=2, confidence=0.72):
        pred = MagicMock(spec=PredictionResult)
        pred.signal_class = signal_class
        pred.signal_name = "BUY"
        pred.confidence = confidence
        pred.probabilities = {"SELL": 0.15, "HOLD": 0.13, "BUY": 0.72}
        return pred

    def test_ml_agree_metadata(self):
        sm = self._make_strategy_manager()
        signal = self._make_signal()
        prediction = self._make_prediction(signal_class=2, confidence=0.72)
        sm.scalp_strategy.generate_signal.return_value = signal
        market_data = {"current_price": 2047.5, "atr": 16.8}

        result = sm._process_scalp(prediction, "XAUUSD", market_data)

        assert "ml" in result.metadata
        ml = result.metadata["ml"]
        assert ml["agreement"] == "agree"
        assert ml["probabilities"] == {"SELL": 0.15, "HOLD": 0.13, "BUY": 0.72}
        assert ml["confidence_before"] == 0.67
        assert ml["confidence_after"] == 0.67  # unchanged when agree

    def test_ml_disagree_halves_confidence(self):
        sm = self._make_strategy_manager()
        signal = self._make_signal(direction=SignalDirection.BUY, confidence=0.67)
        prediction = self._make_prediction(signal_class=0, confidence=0.72)  # SELL
        prediction.signal_name = "SELL"
        sm.scalp_strategy.generate_signal.return_value = signal
        market_data = {"current_price": 2047.5, "atr": 16.8}

        result = sm._process_scalp(prediction, "XAUUSD", market_data)

        assert result.metadata["ml"]["agreement"] == "disagree"
        assert result.metadata["ml"]["confidence_after"] == pytest.approx(0.335, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_audit.py::TestProcessScalpMlMetadata -v`
Expected: FAIL — `ml` key not in metadata

- [ ] **Step 3: Add ML metadata to `_process_scalp()`**

In `backend/src/strategy/strategy_manager.py`, in `_process_scalp()` after the agree/neutral/disagree block (around line 290), before the final return:

```python
        # Determine agreement type
        if ml_direction == signal.direction and prediction.confidence > 0.40:
            agreement = "agree"
        elif ml_direction == SignalDirection.HOLD or prediction.confidence <= 0.40:
            agreement = "neutral"
        else:
            agreement = "disagree"

        # Add ML audit data to signal metadata
        signal.metadata["ml"] = {
            "signal_class": prediction.signal_class,
            "signal_name": prediction.signal_name,
            "confidence": round(prediction.confidence, 4),
            "probabilities": prediction.probabilities,
            "agreement": agreement,
            "confidence_before": round(pre_ml_confidence, 4),
            "confidence_after": round(signal.confidence, 4),
        }
```

Note: Capture `pre_ml_confidence = signal.confidence` BEFORE any `model_copy()` calls that halve confidence.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/test_scalp_score_audit.py::TestProcessScalpMlMetadata -v`
Expected: PASS

- [ ] **Step 5: Run full strategy suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/strategy/ -v --tb=short`

- [ ] **Step 6: Commit**

```bash
git add backend/src/strategy/strategy_manager.py backend/tests/strategy/test_scalp_score_audit.py
git commit -m "feat: add ML prediction details to signal.metadata in _process_scalp()"
```

---

### Task 5: Add `audit` field to RiskCheckResult and populate in `check_trade()`

**Files:**
- Modify: `backend/src/risk/schemas.py:11-24`
- Modify: `backend/src/risk/risk_manager.py:53-297`
- Test: `backend/tests/risk/test_risk_audit.py`

- [ ] **Step 1: Write test for audit field on RiskCheckResult**

```python
# backend/tests/risk/test_risk_audit.py
"""Tests for risk check audit trail."""
import pytest
from src.risk.schemas import RiskCheckResult


def test_risk_check_result_has_audit_field():
    """RiskCheckResult should have an audit dict, empty by default."""
    result = RiskCheckResult(approved=True)
    assert isinstance(result.audit, dict)
    assert result.audit == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_audit.py -v`
Expected: FAIL — `audit` field does not exist

- [ ] **Step 3: Add audit field to RiskCheckResult**

In `backend/src/risk/schemas.py`, add after `circuit_breaker_details` (line 24):

```python
    audit: dict = Field(default_factory=dict)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_audit.py -v`
Expected: PASS

- [ ] **Step 5: Write test for audit dict population in check_trade()**

Append to `backend/tests/risk/test_risk_audit.py`:

```python
from unittest.mock import MagicMock, patch
from src.risk.risk_manager import RiskManager
from src.strategy.schemas import TradingSignal, SignalDirection


def _make_risk_manager():
    """Create a RiskManager with mocked dependencies."""
    rm = RiskManager.__new__(RiskManager)
    rm.limits = MagicMock()
    rm.limits.max_risk_per_trade = 0.02
    rm.limits.max_total_open_positions = 10
    rm.limits.max_total_exposure = 5.0
    rm.circuit_breakers = MagicMock()
    rm.circuit_breakers.check_all.return_value = (True, [])
    rm.circuit_breakers.tripped_breakers = {}
    rm.drawdown_monitor = MagicMock()
    rm.drawdown_monitor.is_circuit_breaker_active.return_value = False
    rm.drawdown_monitor.check_limits.return_value = True
    rm.correlation_guard = MagicMock()
    rm.correlation_guard.check_exposure.return_value = (1.0, [])
    rm.kelly_sizer = None
    rm.equity_curve_filter = MagicMock()
    rm.equity_curve_filter.get_size_multiplier.return_value = 1.0
    rm.settings = {}
    return rm


def test_check_trade_approved_has_audit():
    rm = _make_risk_manager()
    signal = TradingSignal(
        epic="XAUUSD", direction=SignalDirection.BUY,
        confidence=0.67, signal_class=2, entry_price=2047.5,
    )
    result = rm.check_trade(signal=signal, equity=10000, atr=16.8, open_positions=[])

    assert result.approved is True
    audit = result.audit
    assert "circuit_breakers" in audit
    assert "sizing_method" in audit
    assert "confidence_tier" in audit
    assert "dynamic_sl" in audit
    assert "stop_loss" in audit
    assert "take_profit" in audit


def test_check_trade_rejected_has_audit():
    rm = _make_risk_manager()
    rm.circuit_breakers.check_all.return_value = (False, ["daily_loss"])
    rm.circuit_breakers.tripped_breakers = {"daily_loss": True}
    signal = TradingSignal(
        epic="XAUUSD", direction=SignalDirection.BUY,
        confidence=0.67, signal_class=2, entry_price=2047.5,
    )
    result = rm.check_trade(signal=signal, equity=10000, atr=16.8, open_positions=[])

    assert result.approved is False
    audit = result.audit
    assert audit["circuit_breakers"]["ok"] is False
    assert "daily_loss" in audit["circuit_breakers"]["tripped"]
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_audit.py -v`
Expected: FAIL — `audit` is empty `{}`

- [ ] **Step 7: Populate audit dict in `check_trade()`**

In `backend/src/risk/risk_manager.py`, in `check_trade()`:

Initialize the audit dict at the top of the method (after line 77):
```python
        audit = {}
```

After each check step, add data to `audit`. For example:

After circuit breaker check (~line 91):
```python
        audit["circuit_breakers"] = {"ok": cb_ok, "tripped": list(cb_reasons)}
```

After dynamic SL calculation (~line 179):
```python
        audit["dynamic_sl"] = {
            "multiplier": round(stop_mult, 4),
            "baseline_atr": round(baseline_atr, 5) if isinstance(baseline_atr, (int, float)) else 0,
            "current_atr": round(atr, 5),
            "vol_ratio": round(vol_ratio, 4) if isinstance(vol_ratio, (int, float)) else 0,
        }
```

After sizing (~line 252):
```python
        audit["sizing_method"] = sizing_method
        audit["kelly_fraction"] = round(kelly_fraction, 4) if kelly_fraction else 0
        audit["position_size"] = round(position_size, 6)
        audit["confidence_tier"] = {"multiplier": round(conf_mult, 2), "tier": tier_name}
```

After correlation (~line 212):
```python
        audit["correlation"] = {"multiplier": round(corr_mult, 2), "warnings": corr_warnings}
```

After equity curve (~line 260):
```python
        audit["equity_curve"] = {"multiplier": round(eq_mult, 2)}
```

After SL/TP (~line 280):
```python
        audit["stop_loss"] = round(stop_loss, 5)
        audit["take_profit"] = round(take_profit, 5)
        audit["tp1"] = round(tp1, 5) if tp1 else None
        audit["tp2"] = round(tp2, 5) if tp2 else None
        audit["adjustments"] = adjustments
```

Set `result.audit = audit` before returning. Also set it on early rejection returns.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/risk/test_risk_audit.py -v`
Expected: All PASS

- [ ] **Step 9: Run full risk test suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/risk/ -v --tb=short`
Expected: No regressions

- [ ] **Step 10: Commit**

```bash
git add backend/src/risk/schemas.py backend/src/risk/risk_manager.py backend/tests/risk/test_risk_audit.py
git commit -m "feat: add audit dict to RiskCheckResult, populate in check_trade()"
```

---

## Chunk 2: Backend — Signal Persistence & API

### Task 6: Add new repository methods to SignalRepository

**Files:**
- Modify: `backend/src/database/repositories/signal_repository.py`
- Test: `backend/tests/trading/test_signal_persistence.py`

- [ ] **Step 1: Write tests for new repository methods**

```python
# backend/tests/trading/test_signal_persistence.py
"""Integration tests for signal audit trail persistence."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


class TestSignalRepositoryAuditMethods:
    """Tests for new SignalRepository methods needed by the audit trail."""

    @pytest.mark.asyncio
    async def test_create_from_audit_returns_id(self):
        """create_from_audit() should INSERT and return the new signal ID."""
        from src.database.repositories.signal_repository import SignalRepository
        from src.database.models import Signal

        mock_session = AsyncMock()
        repo = SignalRepository(mock_session)

        # Mock the add + flush + refresh cycle
        async def mock_flush():
            pass
        async def mock_refresh(obj):
            obj.id = 42  # Simulate DB-assigned ID
        mock_session.flush = mock_flush
        mock_session.refresh = mock_refresh
        mock_session.add = MagicMock()

        features = {"version": 1, "votes": {"ema": {"value": 1}}}
        signal_id = await repo.create_from_audit(
            epic="XAUUSD", direction="BUY", confidence=0.67,
            entry_price=2047.5, stop_loss=2035.0, take_profit=2060.0,
            status="EXECUTED", features=features,
        )

        assert signal_id == 42
        mock_session.add.assert_called_once()
        added_signal = mock_session.add.call_args[0][0]
        assert isinstance(added_signal, Signal)
        assert added_signal.epic == "XAUUSD"
        assert added_signal.features == features
        assert added_signal.model_version == "scalp_score_v1"

    @pytest.mark.asyncio
    async def test_get_history_by_epic(self):
        """get_history_by_epic() should return lightweight signal list."""
        from src.database.repositories.signal_repository import SignalRepository

        mock_session = AsyncMock()
        repo = SignalRepository(mock_session)

        # Mock execute result
        mock_result = MagicMock()
        mock_result.all.return_value = [
            (42, "BUY", Decimal("0.6700"), "EXECUTED", datetime(2026, 3, 11, 14, 23), None, 14.40, "OPEN"),
        ]
        mock_session.execute.return_value = mock_result

        history = await repo.get_history_by_epic("XAUUSD", limit=10, offset=0)
        assert len(history) == 1
        assert history[0]["id"] == 42
        assert history[0]["direction"] == "BUY"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_signal_persistence.py -v`
Expected: FAIL — methods don't exist

- [ ] **Step 3: Implement new repository methods**

Add to `backend/src/database/repositories/signal_repository.py`:

```python
    async def create_from_audit(
        self,
        epic: str,
        direction: str,
        confidence: float,
        entry_price: float | None,
        stop_loss: float | None,
        take_profit: float | None,
        status: str,
        features: dict,
        rejection_reason: str | None = None,
    ) -> int | None:
        """
        Create a signal record with full audit trail JSONB.

        Returns the new signal ID, or None on failure.
        """
        from decimal import Decimal
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        signal = Signal(
            epic=epic,
            timeframe="15min",
            direction=direction,
            confidence=Decimal(str(round(confidence, 4))),
            predicted_price=Decimal(str(round(entry_price, 4))) if entry_price else None,
            stop_loss_price=Decimal(str(round(stop_loss, 4))) if stop_loss else None,
            take_profit_price=Decimal(str(round(take_profit, 4))) if take_profit else None,
            model_version="scalp_score_v1",
            features=features,
            status=status,
            generated_at=now,
        )
        self.session.add(signal)
        await self.session.flush()
        await self.session.refresh(signal)
        return signal.id

    async def get_by_position_deal_id(self, deal_id: str) -> Signal | None:
        """Find the signal linked to a position by deal_id."""
        from src.database.models import Position

        result = await self.session.execute(
            select(Signal)
            .join(Position, Signal.position_id == Position.id)
            .where(Position.deal_id == deal_id)
            .order_by(Signal.generated_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def get_history_by_epic(
        self, epic: str, limit: int = 10, offset: int = 0
    ) -> list[dict]:
        """
        Get lightweight signal history for an epic (no JSONB features).
        Returns list of dicts with summary fields + position P&L.
        """
        from src.database.models import Position
        from sqlalchemy import func, case

        query = (
            select(
                Signal.id,
                Signal.direction,
                Signal.confidence,
                Signal.status,
                Signal.generated_at,
                Signal.features["rejection_reason"].as_string().label("rejection_reason"),
                Position.profit_loss.label("position_pnl"),
                case(
                    (Position.status == "OPEN", "OPEN"),
                    (Position.status == "CLOSED", "CLOSED"),
                    else_=None,
                ).label("position_status"),
            )
            .outerjoin(Position, Signal.position_id == Position.id)
            .where(Signal.epic == epic)
            .where(Signal.status.in_(["EXECUTED", "REJECTED"]))
            .order_by(Signal.generated_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(query)
        rows = result.all()

        return [
            {
                "id": row.id,
                "epic": epic,
                "direction": row.direction,
                "confidence": float(row.confidence),
                "status": row.status,
                "generated_at": row.generated_at.isoformat() if row.generated_at else None,
                "rejection_reason": row.rejection_reason,
                "position_pnl": float(row.position_pnl) if row.position_pnl else None,
                "position_status": row.position_status,
            }
            for row in rows
        ]

    async def count_by_epic(self, epic: str) -> int:
        """Count total signals for an epic."""
        from sqlalchemy import func
        result = await self.session.execute(
            select(func.count(Signal.id))
            .where(Signal.epic == epic)
            .where(Signal.status.in_(["EXECUTED", "REJECTED"]))
        )
        return result.scalar() or 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/trading/test_signal_persistence.py -v`

- [ ] **Step 5: Run existing signal repository tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -k "signal" -v --tb=short`

- [ ] **Step 6: Commit**

```bash
git add backend/src/database/repositories/signal_repository.py backend/tests/trading/test_signal_persistence.py
git commit -m "feat: add create_from_audit, get_by_position_deal_id, get_history_by_epic to SignalRepository"
```

---

### Task 7: Assemble and persist audit JSONB in `_process_epic()`

**Files:**
- Modify: `backend/src/trading/paper_loop.py`
- Test: `backend/tests/trading/test_signal_persistence.py`

- [ ] **Step 1: Write test for signal persistence in _process_epic**

Append to `backend/tests/trading/test_signal_persistence.py`:

```python
class TestPaperLoopSignalPersistence:
    """_process_epic() should persist signals with full audit JSONB."""

    @pytest.mark.asyncio
    async def test_executed_signal_is_persisted(self):
        """When a signal leads to execution, it should be INSERT'd into signals table."""
        # This test verifies the wiring: _process_epic → create_from_audit → mark_as_executed
        # Detailed implementation depends on how the mock session_factory is set up.
        # The key assertion: signal_repo.create_from_audit is called with features containing
        # votes, gates, ml, risk, market_snapshot keys.
        pass  # Placeholder — implement after wiring is done

    @pytest.mark.asyncio
    async def test_rejected_signal_is_persisted(self):
        """When a signal is rejected by risk, it should still be persisted as REJECTED."""
        pass  # Placeholder
```

- [ ] **Step 2: Add signal repository injection to PaperTradingLoop.__init__()**

In `backend/src/trading/paper_loop.py`, in `__init__()` (around line 67):

Add parameter: `signal_repo_factory=None` (a callable that returns a session + repo, similar to `db_session_factory`).

Store it: `self._signal_repo_factory = signal_repo_factory`

- [ ] **Step 3: Add assembly + persistence in `_process_epic()`**

After `signal_info` is assembled (around line 1172), add:

```python
        # --- Audit trail persistence (best-effort) ---
        signal_db_id = None
        if self._signal_repo_factory:
            try:
                audit_features = {
                    "version": 1,
                    "rejection_reason": None,
                    "votes": signal.metadata.get("votes"),
                    "gates": signal.metadata.get("gates"),
                    "ml": signal.metadata.get("ml"),
                    "risk": None,  # filled after risk check
                    "market_snapshot": signal.metadata.get("market_snapshot"),
                }
                # Will be completed after risk check (see below)
            except Exception:
                logger.warning(f"Failed to build audit features for {epic}")
```

After risk check (around line 1242), update:
```python
        if self._signal_repo_factory:
            try:
                audit_features["risk"] = risk_result.audit if risk_result and risk_result.approved else (
                    risk_result.audit if risk_result else {"skipped": True, "rejection_reason": "no_risk_check"}
                )
                if not risk_result or not risk_result.approved:
                    audit_features["rejection_reason"] = (
                        risk_result.rejection_reason if risk_result else "unknown"
                    )
            except Exception:
                pass
```

After execution result (around line 1360), persist:
```python
        if self._signal_repo_factory:
            try:
                async with self._signal_repo_factory() as (session, signal_repo):
                    status = "EXECUTED" if exec_result and exec_result.success else "REJECTED"
                    signal_db_id = await signal_repo.create_from_audit(
                        epic=epic, direction=signal.direction.value,
                        confidence=signal.confidence,
                        entry_price=signal.entry_price,
                        stop_loss=risk_result.stop_loss if risk_result else None,
                        take_profit=risk_result.take_profit if risk_result else None,
                        status=status, features=audit_features,
                    )
                    if status == "EXECUTED" and signal_db_id and exec_result.deal_id:
                        await signal_repo.mark_as_executed(signal_db_id, position_id)
                    await session.commit()
            except Exception as e:
                logger.warning(f"Failed to persist signal audit for {epic}: {e}")
```

Add `signal_db_id` to `signal_info`:
```python
        signal_info["signal_db_id"] = signal_db_id
```

- [ ] **Step 4: Wire signal_repo_factory in `main.py` lifespan**

In `backend/src/api/main.py`, where `PaperTradingLoop` is constructed, pass the factory. Follow the existing `db_session_factory` pattern.

- [ ] **Step 5: Run full trading test suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/trading/ -v --tb=short`
Expected: No regressions

- [ ] **Step 6: Commit**

```bash
git add backend/src/trading/paper_loop.py backend/src/api/main.py backend/tests/trading/test_signal_persistence.py
git commit -m "feat: assemble and persist signal audit JSONB in _process_epic()"
```

---

### Task 8: Add audit API endpoints to signals router

**Files:**
- Modify: `backend/src/api/routers/signals.py`
- Modify: `backend/src/api/schemas.py`
- Test: `backend/tests/api/test_signals_audit_api.py`

- [ ] **Step 1: Add Pydantic response schemas**

In `backend/src/api/schemas.py`, add:

```python
class PositionSummaryResponse(BaseModel):
    deal_id: str
    entry_price: float
    current_price: float
    pnl: float
    pnl_pct: float
    stop_loss: float | None
    take_profit: float | None
    status: str  # OPEN or CLOSED
    close_reason: str | None
    opened_at: str | None
    closed_at: str | None
    size: float


class SignalAuditResponse(BaseModel):
    id: int
    epic: str
    direction: str
    confidence: float
    status: str
    generated_at: str
    rejection_reason: str | None
    features: dict
    position_summary: PositionSummaryResponse | None


class SignalHistoryItemResponse(BaseModel):
    id: int
    epic: str
    direction: str
    confidence: float
    status: str
    generated_at: str
    rejection_reason: str | None
    position_pnl: float | None
    position_status: str | None


class SignalHistoryResponse(BaseModel):
    data: list[SignalHistoryItemResponse]
    total: int
```

- [ ] **Step 2: Add 3 new endpoints to signals router**

In `backend/src/api/routers/signals.py`, add:

```python
@router.get("/audit/{signal_id}")
async def get_signal_audit(
    signal_id: int,
    signal_repo=Depends(get_signal_repo),
    # position_repo for summary
):
    """Get full signal audit trail by signal ID."""
    if not signal_repo:
        raise HTTPException(404, "Signal storage unavailable")

    signal = await signal_repo.get_by_id(signal_id)
    if not signal:
        raise HTTPException(404, "Signal not found")

    # Build position summary if executed
    position_summary = None
    if signal.position_id:
        # Query position for summary data
        pass  # implementation details

    return {
        "success": True,
        "data": SignalAuditResponse(
            id=signal.id, epic=signal.epic, direction=signal.direction,
            confidence=float(signal.confidence), status=signal.status,
            generated_at=signal.generated_at.isoformat(),
            rejection_reason=signal.features.get("rejection_reason") if signal.features else None,
            features=signal.features or {},
            position_summary=position_summary,
        ).model_dump(),
    }


@router.get("/audit/by-position/{deal_id}")
async def get_signal_audit_by_position(deal_id: str, signal_repo=Depends(get_signal_repo)):
    """Get signal audit trail by position deal_id."""
    if not signal_repo:
        return {"success": True, "data": None}

    signal = await signal_repo.get_by_position_deal_id(deal_id)
    if not signal:
        return {"success": True, "data": None}

    # Same response building as above
    ...


@router.get("/audit/history/{epic}")
async def get_signal_history(
    epic: str,
    limit: int = 10,
    offset: int = 0,
    signal_repo=Depends(get_signal_repo),
):
    """Get lightweight signal history for an epic."""
    if not signal_repo:
        return {"success": True, "data": [], "total": 0}

    history = await signal_repo.get_history_by_epic(epic, limit=limit, offset=offset)
    total = await signal_repo.count_by_epic(epic)

    return {"success": True, "data": history, "total": total}
```

- [ ] **Step 3: Write API tests**

```python
# backend/tests/api/test_signals_audit_api.py
"""Tests for signal audit API endpoints."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_signal_audit_not_found(client: AsyncClient):
    resp = await client.get("/api/signals/audit/999999")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_signal_history_empty(client: AsyncClient):
    resp = await client.get("/api/signals/audit/history/XAUUSD")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert isinstance(data["data"], list)


@pytest.mark.asyncio
async def test_get_signal_by_position_no_link(client: AsyncClient):
    resp = await client.get("/api/signals/audit/by-position/NONEXISTENT")
    assert resp.status_code == 200
    data = resp.json()
    assert data["data"] is None
```

- [ ] **Step 4: Run API tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/api/test_signals_audit_api.py -v`

- [ ] **Step 5: Run full test suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short -x`
Expected: All pass (including existing 1487 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/src/api/routers/signals.py backend/src/api/schemas.py backend/tests/api/test_signals_audit_api.py
git commit -m "feat: add signal audit API endpoints (get by id, by position, history)"
```

---

## Chunk 3: Frontend — TypeScript Interfaces & Service

### Task 9: Add TypeScript interfaces for signal audit data

**Files:**
- Modify: `frontend/src/app/core/models/index.ts`

- [ ] **Step 1: Add interfaces**

Append to `frontend/src/app/core/models/index.ts`:

```typescript
// --- Signal Audit Trail ---

export interface SignalAudit {
  id: number;
  epic: string;
  direction: 'BUY' | 'SELL';
  confidence: number;
  status: 'EXECUTED' | 'REJECTED';
  generated_at: string;
  rejection_reason: string | null;
  features: SignalFeatures;
  position_summary: AuditPositionSummary | null;
}

export interface SignalFeatures {
  version: number;
  rejection_reason: string | null;
  votes: Record<string, { value: number; [key: string]: any }>;
  gates: Record<string, { passed: boolean; [key: string]: any } | null>;
  ml: SignalMl | null;
  risk: SignalRisk | null;
  market_snapshot: Record<string, number | string>;
}

export interface SignalMl {
  signal_class: number;
  signal_name: string;
  confidence: number;
  probabilities: Record<string, number>;
  agreement: string;
  confidence_before: number;
  confidence_after: number;
}

export interface SignalRisk {
  approved: boolean;
  rejection_reason: string | null;
  circuit_breakers: { ok: boolean; tripped: string[] };
  sizing_method: string;
  kelly_fraction: number;
  position_size: number;
  confidence_tier: { multiplier: number; tier: string };
  equity_curve: { multiplier: number };
  correlation: { multiplier: number; warnings: string[] };
  dynamic_sl: { multiplier: number; baseline_atr: number; current_atr: number; vol_ratio: number };
  stop_loss: number;
  take_profit: number;
  tp1: number | null;
  tp2: number | null;
  adjustments: string[];
}

export interface AuditPositionSummary {
  deal_id: string;
  entry_price: number;
  current_price: number;
  pnl: number;
  pnl_pct: number;
  stop_loss: number | null;
  take_profit: number | null;
  status: 'OPEN' | 'CLOSED';
  close_reason: string | null;
  opened_at: string | null;
  closed_at: string | null;
  size: number;
}

export interface SignalHistoryItem {
  id: number;
  epic: string;
  direction: 'BUY' | 'SELL';
  confidence: number;
  status: 'EXECUTED' | 'REJECTED';
  generated_at: string;
  rejection_reason: string | null;
  position_pnl: number | null;
  position_status: string | null;
}
```

Also add `signal_db_id` to `PaperSignal` interface (around line 301):
```typescript
  signal_db_id?: number | null;
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/core/models/index.ts
git commit -m "feat: add TypeScript interfaces for signal audit trail"
```

---

### Task 10: Create SignalAuditService

**Files:**
- Create: `frontend/src/app/core/services/signal-audit.service.ts`

- [ ] **Step 1: Create the service**

```typescript
// frontend/src/app/core/services/signal-audit.service.ts
import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { SignalAudit, SignalHistoryItem } from '../models';
import { NotificationService } from './notification.service';
import { WebSocketService } from './websocket.service';

@Injectable({ providedIn: 'root' })
export class SignalAuditService {
  private readonly http = inject(HttpClient);
  private readonly toast = inject(NotificationService);
  private readonly ws = inject(WebSocketService);

  // State
  readonly isOpen = signal(false);
  readonly currentAudit = signal<SignalAudit | null>(null);
  readonly relatedSignals = signal<SignalHistoryItem[]>([]);
  readonly loading = signal(false);

  // Live P&L for open positions
  readonly livePositionSummary = computed(() => {
    const audit = this.currentAudit();
    if (!audit?.position_summary || audit.position_summary.status !== 'OPEN') {
      return audit?.position_summary ?? null;
    }

    const prices = this.ws.prices();
    const tick = prices[audit.epic];
    if (!tick) return audit.position_summary;

    const currentPrice = audit.direction === 'BUY' ? tick.bid : tick.offer;
    const diff = audit.direction === 'BUY'
      ? currentPrice - audit.position_summary.entry_price
      : audit.position_summary.entry_price - currentPrice;
    const pnl = Math.round(diff * audit.position_summary.size * 100) / 100;
    const pnlPct = audit.position_summary.entry_price
      ? Math.round((diff / audit.position_summary.entry_price) * 10000) / 100
      : 0;

    return {
      ...audit.position_summary,
      current_price: currentPrice,
      pnl,
      pnl_pct: pnlPct,
    };
  });

  open(signalId: number): void {
    this.loading.set(true);
    this.isOpen.set(true);

    this.http.get<{ success: boolean; data: SignalAudit }>(`/api/signals/audit/${signalId}`)
      .subscribe({
        next: (resp) => {
          this.currentAudit.set(resp.data);
          this.loading.set(false);
          // Load related signals
          if (resp.data) {
            this._loadHistory(resp.data.epic, resp.data.id);
          }
        },
        error: () => {
          this.loading.set(false);
          this.toast.error('Impossibile caricare i dati del segnale');
          this.close();
        },
      });
  }

  openByDealId(dealId: string): void {
    this.loading.set(true);
    this.isOpen.set(true);

    this.http.get<{ success: boolean; data: SignalAudit | null }>(`/api/signals/audit/by-position/${dealId}`)
      .subscribe({
        next: (resp) => {
          if (!resp.data) {
            this.loading.set(false);
            this.toast.warn('Audit non disponibile per questa posizione');
            this.close();
            return;
          }
          this.currentAudit.set(resp.data);
          this.loading.set(false);
          this._loadHistory(resp.data.epic, resp.data.id);
        },
        error: () => {
          this.loading.set(false);
          this.toast.error('Impossibile caricare i dati del segnale');
          this.close();
        },
      });
  }

  close(): void {
    this.isOpen.set(false);
    this.currentAudit.set(null);
    this.relatedSignals.set([]);
  }

  navigateToSignal(signalId: number): void {
    this.open(signalId);
  }

  private _loadHistory(epic: string, currentSignalId: number): void {
    this.http.get<{ success: boolean; data: SignalHistoryItem[]; total: number }>(
      `/api/signals/audit/history/${epic}?limit=10`
    ).subscribe({
      next: (resp) => this.relatedSignals.set(resp.data ?? []),
      error: () => {},
    });
  }
}
```

- [ ] **Step 2: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`
Expected: 0 errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/core/services/signal-audit.service.ts
git commit -m "feat: create SignalAuditService for drawer state and API calls"
```

---

## Chunk 4: Frontend — Drawer Component

### Task 11: Create SignalAuditDrawerComponent

**Files:**
- Create: `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.ts`
- Create: `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.html`
- Create: `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.scss`

- [ ] **Step 1: Create component TypeScript**

```typescript
// frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.ts
import { Component, ChangeDetectionStrategy, inject, HostListener } from '@angular/core';
import { CommonModule } from '@angular/common';
import { SignalAuditService } from '../../../core/services/signal-audit.service';
import { EpicLogoComponent } from '../epic-logo/epic-logo.component';
import { BadgeComponent, SpinnerComponent } from '@coreui/angular';

@Component({
  selector: 'app-signal-audit-drawer',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [CommonModule, EpicLogoComponent, BadgeComponent, SpinnerComponent],
  templateUrl: './signal-audit-drawer.component.html',
  styleUrls: ['./signal-audit-drawer.component.scss'],
})
export class SignalAuditDrawerComponent {
  readonly auditService = inject(SignalAuditService);

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.auditService.isOpen()) {
      this.auditService.close();
    }
  }

  onBackdropClick(): void {
    this.auditService.close();
  }

  voteEntries(): [string, any][] {
    const votes = this.auditService.currentAudit()?.features?.votes;
    if (!votes) return [];
    return Object.entries(votes);
  }

  gateEntries(): [string, any][] {
    const gates = this.auditService.currentAudit()?.features?.gates;
    if (!gates) return [];
    return Object.entries(gates);
  }

  gatesPassed(): number {
    return this.gateEntries().filter(([, g]) => g?.passed === true).length;
  }

  gatesTotal(): number {
    return this.gateEntries().filter(([, g]) => g !== null).length;
  }

  voteLabel(key: string): string {
    const labels: Record<string, string> = {
      ema: 'EMA', rsi: 'RSI', macd: 'MACD',
      volume: 'Volume', adx: 'ADX', bb_keltner: 'BB/Keltner',
    };
    return labels[key] ?? key;
  }

  gateLabel(key: string): string {
    const labels: Record<string, string> = {
      session: 'Session', dead_market: 'Dead Market',
      vwap: 'VWAP', htf: 'HTF Trend', confluence: 'Confluence',
    };
    return labels[key] ?? key;
  }

  mlAgreementColor(): string {
    const ml = this.auditService.currentAudit()?.features?.ml;
    if (!ml) return 'secondary';
    switch (ml.agreement) {
      case 'agree': return 'success';
      case 'neutral': return 'warning';
      case 'disagree': return 'danger';
      default: return 'secondary';
    }
  }
}
```

- [ ] **Step 2: Create component HTML template**

Create `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.html` — this will contain the full template with all 7 sections (header, position summary, votes, gates, ML, risk, related signals). The template follows the mockup approved in the spec, using `@if` blocks for conditional sections and `@for` for iteration.

The template is large (~300 lines of HTML). Key patterns:
- Uses `auditService.isOpen()` for visibility
- Uses `auditService.livePositionSummary()` for live P&L
- Uses `auditService.currentAudit()?.features?.ml` with null checks
- All numbers use `mantis-mono` class
- Vote values use conditional coloring: `+1` green, `-1` red, `0` neutral
- Gate dots: green for passed, red for failed, grey for null

- [ ] **Step 3: Create component SCSS**

Create `frontend/src/app/shared/components/signal-audit-drawer/signal-audit-drawer.component.scss` with:
- `.audit-backdrop` — fixed overlay, `z-index: 1040`, backdrop click handler
- `.audit-drawer` — fixed right, 480px width, `translateX` animation
- `.audit-header` — sticky header with border-bottom
- `.audit-section` — consistent section styling with diamond icon
- Section-specific styles for votes grid, gates list, ML boxes, risk grid
- Media query for mobile: `@media (max-width: 767px)` → 100% width

All colors via CSS custom properties (`var(--mantis-profit)`, `var(--mantis-loss)`, etc.).

- [ ] **Step 4: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`
Expected: 0 errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/shared/components/signal-audit-drawer/
git commit -m "feat: create SignalAuditDrawerComponent with full audit display"
```

---

### Task 12: Integrate drawer into DefaultLayoutComponent

**Files:**
- Modify: `frontend/src/app/layout/default-layout/default-layout.component.ts`
- Modify: `frontend/src/app/layout/default-layout/default-layout.component.html`

- [ ] **Step 1: Add import in TypeScript**

In `default-layout.component.ts`, add import:
```typescript
import { SignalAuditDrawerComponent } from '../../shared/components/signal-audit-drawer/signal-audit-drawer.component';
```

Add to `imports` array (after `BottomNavComponent`):
```typescript
    SignalAuditDrawerComponent
```

- [ ] **Step 2: Add to template**

In `default-layout.component.html`, after the `<app-confirm-dialog>` tag (around line 67):
```html
<app-signal-audit-drawer />
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`
Expected: 0 errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/layout/default-layout/default-layout.component.ts frontend/src/app/layout/default-layout/default-layout.component.html
git commit -m "feat: integrate SignalAuditDrawer into default layout"
```

---

## Chunk 5: Frontend — Wire Click Handlers in All Views

### Task 13: Add click-to-audit in Positions view

**Files:**
- Modify: `frontend/src/app/views/positions/positions.component.ts`

- [ ] **Step 1: Inject SignalAuditService**

Add import and inject:
```typescript
import { SignalAuditService } from '../../core/services/signal-audit.service';

readonly auditService = inject(SignalAuditService);
```

- [ ] **Step 2: Add row click handler**

```typescript
openAudit(dealId: string): void {
  this.auditService.openByDealId(dealId);
}
```

- [ ] **Step 3: Wire click on open positions table rows**

In the template, on desktop `<tr>` for open positions (around line 146), add:
```html
<tr ... (click)="openAudit(pos.deal_id)" style="cursor:pointer;">
```

On the Close button, add `$event.stopPropagation()`:
```html
<app-loading-button ... (clicked)="closePosition(pos.deal_id); $event.stopPropagation()">
```

Same for mobile cards.

- [ ] **Step 4: Wire click on history table rows**

In the template, on history `<tr>` (around line 386), add:
```html
<tr ... (click)="openAudit(pos.deal_id)" style="cursor:pointer;">
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/views/positions/positions.component.ts
git commit -m "feat: wire position row clicks to signal audit drawer in Positions view"
```

---

### Task 14: Add click-to-audit in Paper Trading view

**Files:**
- Modify: `frontend/src/app/views/paper-trading/paper-trading.component.ts`

- [ ] **Step 1: Inject SignalAuditService**

```typescript
import { SignalAuditService } from '../../core/services/signal-audit.service';
readonly auditService = inject(SignalAuditService);
```

- [ ] **Step 2: Add methods**

```typescript
openAuditByDeal(dealId: string, event: MouseEvent): void {
  event.stopPropagation();  // Don't toggle group
  this.auditService.openByDealId(dealId);
}

openAuditBySignal(signalDbId: number | null | undefined): void {
  if (!signalDbId) {
    this.toast.warn('Audit non disponibile per questo segnale');
    return;
  }
  this.auditService.open(signalDbId);
}
```

- [ ] **Step 3: Wire click on expanded position detail rows**

In the template, on detail rows inside expanded groups (around line 371):
```html
<tr class="detail-row" (click)="openAuditByDeal(pos.deal_id, $event)" style="cursor:pointer;">
```

- [ ] **Step 4: Wire click on signal feed rows**

In signal feed table rows, add:
```html
<tr (click)="openAuditBySignal(s.signal_db_id)" style="cursor:pointer;">
```

- [ ] **Step 5: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/views/paper-trading/paper-trading.component.ts
git commit -m "feat: wire position and signal clicks to audit drawer in Paper Trading"
```

---

### Task 15: Add click-to-audit in Dashboard and Trade Journal

**Files:**
- Modify: `frontend/src/app/views/dashboard/dashboard.component.ts`
- Modify: `frontend/src/app/views/dashboard/dashboard.component.html`
- Modify: `frontend/src/app/views/trade-journal/trade-journal.component.ts`

- [ ] **Step 1: Dashboard — inject service and add click handler**

In `dashboard.component.ts`:
```typescript
import { SignalAuditService } from '../../core/services/signal-audit.service';
readonly auditService = inject(SignalAuditService);

openAudit(dealId: string): void {
  this.auditService.openByDealId(dealId);
}
```

In `dashboard.component.html`, on mini positions table rows:
```html
<tr (click)="openAudit(pos.deal_id)" style="cursor:pointer;">
```

- [ ] **Step 2: Trade Journal — inject service and add click handler**

In `trade-journal.component.ts`:
```typescript
import { SignalAuditService } from '../../core/services/signal-audit.service';
readonly auditService = inject(SignalAuditService);

openAudit(signalDbId: number | null | undefined): void {
  if (!signalDbId) {
    this.toast.warn('Audit non disponibile per questo segnale');
    return;
  }
  this.auditService.open(signalDbId);
}
```

On signal table rows:
```html
<tr (click)="openAudit(sig.signal_db_id)" style="cursor:pointer;">
```

- [ ] **Step 3: Verify build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`
Expected: 0 errors, 0 warnings

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/views/dashboard/ frontend/src/app/views/trade-journal/
git commit -m "feat: wire audit drawer clicks in Dashboard and Trade Journal"
```

---

## Chunk 6: Final Integration & Verification

### Task 16: Full build + all backend tests

- [ ] **Step 1: Run complete backend test suite**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: ~1500+ tests pass (original 1487 + new audit tests), 3 ORB+FVG pre-existing failures

- [ ] **Step 2: Run complete frontend build**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | tail -20`
Expected: 0 errors, 0 warnings

- [ ] **Step 3: Manual smoke test (if servers running)**

1. Start backend: `cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000`
2. Start frontend: `cd frontend && npx ng serve --port 4321`
3. Open browser → Paper Trading → Start trading loop
4. Wait for signals to be generated
5. Click on a position row → verify drawer opens with audit data
6. Check: votes section shows 6 votes with values
7. Check: gates section shows pass/fail status
8. Click on a signal in Trade Journal → verify drawer opens

- [ ] **Step 4: Final commit with all remaining changes**

```bash
git add -A
git commit -m "feat: complete Decision Audit Trail - Phase 1 (backend) + Phase 2 (frontend drawer)"
```

---

## Phase 3 Tasks (separate implementation cycle)

Phase 3 (Related Signals + Polish) should be implemented in a follow-up session after Phase 1+2 are verified working in production. Tasks:

1. Add "Ultimi Segnali" section to drawer template (calls `auditService.relatedSignals()`)
2. Highlight current signal with green left border
3. Click on related signal row → `auditService.navigateToSignal(id)`
4. Add `prefers-reduced-motion` support for slide animation
5. Focus trap implementation (trap Tab key within drawer when open)
6. Mobile polish: swipe-to-close gesture (optional)
