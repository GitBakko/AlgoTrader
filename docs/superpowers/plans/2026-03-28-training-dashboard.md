# Training Dashboard & Extended Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a training management system with UI dashboard, per-epic training, hot model reload, Telegram/toast notifications, and extended historical data from free API sources.

**Architecture:** Backend training orchestrator runs 2-3 parallel jobs, fires alerts on start/complete/fail, auto-reloads models into PredictionService. Frontend adds a Training tab to the existing AI Models page with status cards, progress, and retrain controls. Historical data layer normalizes yfinance/CryptoCompare into the existing Parquet pipeline.

**Tech Stack:** Python (asyncio, concurrent.futures), XGBoost, yfinance, CryptoCompare API (free), FastAPI WebSocket, Angular 21 signals, CoreUI components.

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| `backend/src/models/training_orchestrator.py` | Manages parallel training jobs, tracks status, fires alerts |
| `backend/src/data/extended_data_provider.py` | Fetches historical data from yfinance + CryptoCompare, normalizes to OHLCV |
| `backend/src/data/ticker_mapping.py` | Maps Capital.com epics to yfinance/CryptoCompare tickers |
| `backend/tests/models/test_training_orchestrator.py` | Orchestrator tests |
| `backend/tests/data/test_extended_data_provider.py` | Extended data tests |
| `backend/tests/data/test_ticker_mapping.py` | Mapping tests |

### Backend — Modified Files
| File | Changes |
|------|---------|
| `backend/src/api/routers/models.py` | New endpoints: training status, retrain single/all, cancel |
| `backend/src/models/prediction_service.py` | Add `reload_model(epic)` method for hot reload |
| `backend/src/models/auto_retrain.py` | Refactor to use orchestrator |
| `backend/src/monitoring/alerting/schemas.py` | Add TRAINING_STARTED, TRAINING_COMPLETE, TRAINING_FAILED alert types |
| `backend/src/monitoring/alerting/alert_manager.py` | Add training alert helper methods |
| `backend/src/api/main.py` | Wire orchestrator into app state |

### Frontend — New/Modified Files
| File | Changes |
|------|---------|
| `frontend/src/app/views/ai-models/ai-models.component.ts` | Add Training tab with status, controls, progress |
| `frontend/src/app/views/ai-models/ai-models.component.scss` | Training-specific styles |
| `frontend/src/app/core/services/trading.service.ts` | Add training status/retrain methods |
| `frontend/src/app/core/models/index.ts` | Add TrainingStatus, TrainingJob interfaces |

---

## Task 1: Ticker Mapping (epic -> yfinance/CryptoCompare)

**Files:**
- Create: `backend/src/data/ticker_mapping.py`
- Test: `backend/tests/data/test_ticker_mapping.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/data/test_ticker_mapping.py
"""Tests for epic-to-ticker mapping."""
import pytest
from src.data.ticker_mapping import TickerMapper


class TestTickerMapper:
    def test_gold_yfinance(self):
        assert TickerMapper.to_yfinance("XAUUSD") == "GC=F"

    def test_btc_yfinance(self):
        assert TickerMapper.to_yfinance("BTCUSD") == "BTC-USD"

    def test_sp500_yfinance(self):
        assert TickerMapper.to_yfinance("US500") == "^GSPC"

    def test_tsla_yfinance(self):
        assert TickerMapper.to_yfinance("TSLA") == "TSLA"

    def test_unknown_returns_none(self):
        assert TickerMapper.to_yfinance("UNKNOWN123") is None

    def test_btc_cryptocompare(self):
        assert TickerMapper.to_cryptocompare("BTCUSD") == ("BTC", "USD")

    def test_eth_cryptocompare(self):
        assert TickerMapper.to_cryptocompare("ETHUSD") == ("ETH", "USD")

    def test_gold_not_crypto(self):
        assert TickerMapper.to_cryptocompare("XAUUSD") is None

    def test_all_tradable_have_yfinance(self):
        """Every tradable asset must have a yfinance mapping."""
        from src.utils.constants import TRADABLE_ASSETS
        unmapped = [a for a in TRADABLE_ASSETS if TickerMapper.to_yfinance(a) is None]
        assert unmapped == [], f"Unmapped: {unmapped}"

    def test_asset_class(self):
        assert TickerMapper.asset_class("BTCUSD") == "crypto"
        assert TickerMapper.asset_class("XAUUSD") == "commodity"
        assert TickerMapper.asset_class("TSLA") == "stock"
        assert TickerMapper.asset_class("EURUSD") == "forex"
        assert TickerMapper.asset_class("US500") == "index"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/data/test_ticker_mapping.py -v --no-header -q`
Expected: FAIL — module not found

- [ ] **Step 3: Write implementation**

```python
# backend/src/data/ticker_mapping.py
"""Maps Capital.com epic codes to yfinance and CryptoCompare tickers."""


# Capital.com epic -> yfinance ticker
_YFINANCE_MAP: dict[str, str] = {
    # Commodities
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "WTIUSD": "CL=F",
    "NATGAS": "NG=F",
    "COPPER": "HG=F",
    "PLATINUM": "PL=F",
    # Crypto
    "BTCUSD": "BTC-USD",
    "ETHUSD": "ETH-USD",
    "SOLUSD": "SOL-USD",
    "BNBUSD": "BNB-USD",
    "DOGUSD": "DOGE-USD",
    "DASHUSD": "DASH-USD",
    "ICPUSD": "ICP-USD",
    # Indices
    "US500": "^GSPC",
    "NAS100": "^NDX",
    "DE40": "^GDAXI",
    # Forex
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    # Stocks
    "NVDA": "NVDA",
    "TSLA": "TSLA",
}

# Capital.com epic -> CryptoCompare (fsym, tsym)
_CRYPTO_MAP: dict[str, tuple[str, str]] = {
    "BTCUSD": ("BTC", "USD"),
    "ETHUSD": ("ETH", "USD"),
    "SOLUSD": ("SOL", "USD"),
    "BNBUSD": ("BNB", "USD"),
    "DOGUSD": ("DOGE", "USD"),
    "DASHUSD": ("DASH", "USD"),
    "ICPUSD": ("ICP", "USD"),
}

_ASSET_CLASS: dict[str, str] = {
    "XAUUSD": "commodity", "XAGUSD": "commodity", "WTIUSD": "commodity",
    "NATGAS": "commodity", "COPPER": "commodity", "PLATINUM": "commodity",
    "BTCUSD": "crypto", "ETHUSD": "crypto", "SOLUSD": "crypto",
    "BNBUSD": "crypto", "DOGUSD": "crypto", "DASHUSD": "crypto", "ICPUSD": "crypto",
    "US500": "index", "NAS100": "index", "DE40": "index",
    "EURUSD": "forex", "GBPUSD": "forex", "USDJPY": "forex",
    "NVDA": "stock", "TSLA": "stock",
}


class TickerMapper:
    """Static mapper from Capital.com epic codes to external data source tickers."""

    @staticmethod
    def to_yfinance(epic: str) -> str | None:
        return _YFINANCE_MAP.get(epic)

    @staticmethod
    def to_cryptocompare(epic: str) -> tuple[str, str] | None:
        return _CRYPTO_MAP.get(epic)

    @staticmethod
    def asset_class(epic: str) -> str:
        return _ASSET_CLASS.get(epic, "unknown")

    @staticmethod
    def is_crypto(epic: str) -> bool:
        return epic in _CRYPTO_MAP

    @staticmethod
    def all_yfinance_mapped() -> dict[str, str]:
        return dict(_YFINANCE_MAP)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/data/test_ticker_mapping.py -v --no-header -q`
Expected: PASS (all 11 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/data/ticker_mapping.py backend/tests/data/test_ticker_mapping.py
git commit -m "feat(data): add epic-to-ticker mapping for yfinance and CryptoCompare"
```

---

## Task 2: Extended Data Provider (yfinance + CryptoCompare)

**Files:**
- Create: `backend/src/data/extended_data_provider.py`
- Test: `backend/tests/data/test_extended_data_provider.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/data/test_extended_data_provider.py
"""Tests for extended historical data provider."""
import pytest
import polars as pl
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from src.data.extended_data_provider import ExtendedDataProvider


class TestExtendedDataProvider:
    def test_normalize_yfinance_columns(self):
        """yfinance DataFrame is normalized to standard OHLCV columns."""
        provider = ExtendedDataProvider()
        # Simulate yfinance output (pandas)
        import pandas as pd
        df_pd = pd.DataFrame({
            "Open": [100.0, 101.0],
            "High": [105.0, 106.0],
            "Low": [98.0, 99.0],
            "Close": [103.0, 104.0],
            "Volume": [1000, 1100],
        }, index=pd.date_range("2024-01-01", periods=2, freq="1h", tz="UTC"))
        df = provider._normalize_yfinance(df_pd, "XAUUSD")
        assert set(df.columns) >= {"timestamp", "open", "high", "low", "close", "volume", "epic"}
        assert df["epic"][0] == "XAUUSD"
        assert len(df) == 2

    def test_normalize_cryptocompare_columns(self):
        """CryptoCompare JSON is normalized to standard OHLCV columns."""
        provider = ExtendedDataProvider()
        raw = [
            {"time": 1704067200, "open": 42000, "high": 43000, "low": 41000, "close": 42500, "volumefrom": 100, "volumeto": 4200000},
            {"time": 1704070800, "open": 42500, "high": 43500, "low": 42000, "close": 43000, "volumefrom": 120, "volumeto": 5160000},
        ]
        df = provider._normalize_cryptocompare(raw, "BTCUSD")
        assert set(df.columns) >= {"timestamp", "open", "high", "low", "close", "volume", "epic"}
        assert df["epic"][0] == "BTCUSD"
        assert len(df) == 2

    def test_merge_with_existing(self):
        """Extended data merged with existing broker data, no duplicates."""
        provider = ExtendedDataProvider()
        existing = pl.DataFrame({
            "timestamp": [datetime(2024, 6, 1, tzinfo=timezone.utc), datetime(2024, 6, 2, tzinfo=timezone.utc)],
            "open": [100.0, 101.0],
            "high": [105.0, 106.0],
            "low": [98.0, 99.0],
            "close": [103.0, 104.0],
            "volume": [1000.0, 1100.0],
        })
        extended = pl.DataFrame({
            "timestamp": [datetime(2024, 5, 30, tzinfo=timezone.utc), datetime(2024, 6, 1, tzinfo=timezone.utc)],
            "open": [99.0, 100.0],
            "high": [104.0, 105.0],
            "low": [97.0, 98.0],
            "close": [102.0, 103.0],
            "volume": [900.0, 1000.0],
            "epic": ["XAUUSD", "XAUUSD"],
        })
        merged = provider.merge_with_existing(existing, extended)
        assert len(merged) == 3  # May 30 + June 1 + June 2 (dedup on June 1)
        assert merged["timestamp"].is_sorted()

    def test_get_source_for_epic(self):
        """Crypto uses CryptoCompare, others use yfinance."""
        provider = ExtendedDataProvider()
        assert provider.get_best_source("BTCUSD") == "cryptocompare"
        assert provider.get_best_source("XAUUSD") == "yfinance"
        assert provider.get_best_source("TSLA") == "yfinance"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/data/test_extended_data_provider.py -v --no-header -q`
Expected: FAIL — module not found

- [ ] **Step 3: Write implementation**

```python
# backend/src/data/extended_data_provider.py
"""Extended historical data from free public APIs (yfinance, CryptoCompare).

Normalizes external data to match the Parquet OHLCV format used by
Capital.com data pipeline, enabling seamless merge for training.
"""
from datetime import datetime, timezone

import httpx
import polars as pl
from loguru import logger

from src.data.ticker_mapping import TickerMapper


class ExtendedDataProvider:
    """Fetches and normalizes historical OHLCV from free public APIs."""

    CRYPTOCOMPARE_API = "https://min-api.cryptocompare.com/data/v2"

    def get_best_source(self, epic: str) -> str:
        """Determine best data source for an epic."""
        if TickerMapper.is_crypto(epic):
            return "cryptocompare"
        return "yfinance"

    async def fetch_yfinance(
        self,
        epic: str,
        start: datetime,
        end: datetime | None = None,
        interval: str = "1h",
    ) -> pl.DataFrame | None:
        """Fetch historical data from yfinance (runs in thread to avoid blocking)."""
        import asyncio

        ticker = TickerMapper.to_yfinance(epic)
        if not ticker:
            logger.warning(f"No yfinance mapping for {epic}")
            return None

        def _download():
            import yfinance as yf

            start_str = start.strftime("%Y-%m-%d")
            end_str = end.strftime("%Y-%m-%d") if end else None
            df = yf.download(ticker, start=start_str, end=end_str, interval=interval, progress=False)
            if df.empty:
                return None
            return self._normalize_yfinance(df, epic)

        try:
            return await asyncio.to_thread(_download)
        except Exception as e:
            logger.error(f"yfinance download failed for {epic}: {e}")
            return None

    async def fetch_cryptocompare(
        self,
        epic: str,
        limit: int = 2000,
        to_ts: int | None = None,
    ) -> pl.DataFrame | None:
        """Fetch hourly data from CryptoCompare free API."""
        pair = TickerMapper.to_cryptocompare(epic)
        if not pair:
            return None
        fsym, tsym = pair

        url = f"{self.CRYPTOCOMPARE_API}/histohour"
        params = {"fsym": fsym, "tsym": tsym, "limit": min(limit, 2000)}
        if to_ts:
            params["toTs"] = to_ts

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, params=params, timeout=30.0)
                data = resp.json()
                if data.get("Response") != "Success":
                    logger.warning(f"CryptoCompare error for {epic}: {data.get('Message')}")
                    return None
                raw = data.get("Data", {}).get("Data", [])
                if not raw:
                    return None
                return self._normalize_cryptocompare(raw, epic)
        except Exception as e:
            logger.error(f"CryptoCompare download failed for {epic}: {e}")
            return None

    async def fetch_extended(
        self,
        epic: str,
        start: datetime,
        end: datetime | None = None,
    ) -> pl.DataFrame | None:
        """Fetch extended data from best available source."""
        source = self.get_best_source(epic)
        if source == "cryptocompare":
            # CryptoCompare uses limit-based pagination, not date range
            # For now, fetch max 2000 hourly bars (~83 days)
            return await self.fetch_cryptocompare(epic, limit=2000)
        else:
            return await self.fetch_yfinance(epic, start, end)

    def _normalize_yfinance(self, df_pd, epic: str) -> pl.DataFrame:
        """Normalize yfinance pandas DataFrame to standard Polars OHLCV."""
        df_pd = df_pd.reset_index()
        # Handle multi-level columns from yfinance
        if hasattr(df_pd.columns, "levels"):
            df_pd.columns = [c[0] if isinstance(c, tuple) else c for c in df_pd.columns]

        rename = {}
        for col in df_pd.columns:
            lower = str(col).lower()
            if "date" in lower or "datetime" in lower:
                rename[col] = "timestamp"
            elif lower == "open":
                rename[col] = "open"
            elif lower == "high":
                rename[col] = "high"
            elif lower == "low":
                rename[col] = "low"
            elif lower == "close":
                rename[col] = "close"
            elif lower == "volume":
                rename[col] = "volume"

        df_pd = df_pd.rename(columns=rename)
        df = pl.from_pandas(df_pd[["timestamp", "open", "high", "low", "close", "volume"]])
        df = df.with_columns(pl.lit(epic).alias("epic"))
        return df.sort("timestamp")

    def _normalize_cryptocompare(self, raw: list[dict], epic: str) -> pl.DataFrame:
        """Normalize CryptoCompare JSON to standard Polars OHLCV."""
        rows = []
        for r in raw:
            if r.get("close", 0) == 0:
                continue
            rows.append({
                "timestamp": datetime.fromtimestamp(r["time"], tz=timezone.utc),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
                "volume": float(r.get("volumefrom", 0)),
                "epic": epic,
            })
        if not rows:
            return pl.DataFrame()
        return pl.DataFrame(rows).sort("timestamp")

    def merge_with_existing(
        self,
        existing: pl.DataFrame,
        extended: pl.DataFrame,
    ) -> pl.DataFrame:
        """Merge extended data with existing broker data, dedup on timestamp."""
        if "epic" in extended.columns:
            extended = extended.drop("epic")
        combined = pl.concat([extended, existing], how="diagonal_relaxed")
        combined = combined.unique(subset=["timestamp"], keep="last")
        return combined.sort("timestamp")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/data/test_extended_data_provider.py -v --no-header -q`
Expected: PASS (all 4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/data/extended_data_provider.py backend/tests/data/test_extended_data_provider.py
git commit -m "feat(data): add extended data provider (yfinance + CryptoCompare)"
```

---

## Task 3: Training Alert Types + Alert Manager Methods

**Files:**
- Modify: `backend/src/monitoring/alerting/schemas.py` (AlertType enum)
- Modify: `backend/src/monitoring/alerting/alert_manager.py` (add training helpers)
- Test: `backend/tests/monitoring/test_training_alerts.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/monitoring/test_training_alerts.py
"""Tests for training alert methods."""
import pytest
from unittest.mock import AsyncMock, patch

from src.monitoring.alerting.schemas import AlertType, AlertSeverity
from src.monitoring.alerting.alert_manager import AlertManager


class TestTrainingAlerts:
    @pytest.fixture
    def manager(self):
        with patch("src.monitoring.alerting.alert_manager.get_settings") as mock_settings:
            mock_settings.return_value.alerts_enabled = False
            mock_settings.return_value.alert_telegram_enabled = False
            mock_settings.return_value.alert_email_enabled = False
            mock_settings.return_value.alert_slack_enabled = False
            mock_settings.return_value.alert_webhook_enabled = False
            return AlertManager()

    @pytest.mark.asyncio
    async def test_alert_training_started(self, manager):
        manager.send_alert = AsyncMock(return_value={})
        await manager.alert_training_started("XAUUSD")
        manager.send_alert.assert_called_once()
        alert = manager.send_alert.call_args[0][0]
        assert alert.alert_type == AlertType.TRAINING_STARTED
        assert "XAUUSD" in alert.title

    @pytest.mark.asyncio
    async def test_alert_training_complete(self, manager):
        manager.send_alert = AsyncMock(return_value={})
        await manager.alert_training_complete("XAUUSD", f1=0.58, accuracy=0.62, duration_s=120.5)
        manager.send_alert.assert_called_once()
        alert = manager.send_alert.call_args[0][0]
        assert alert.alert_type == AlertType.TRAINING_COMPLETE
        assert alert.severity == AlertSeverity.INFO
        assert "0.58" in alert.message

    @pytest.mark.asyncio
    async def test_alert_training_failed(self, manager):
        manager.send_alert = AsyncMock(return_value={})
        await manager.alert_training_failed("BTCUSD", error="Out of memory")
        alert = manager.send_alert.call_args[0][0]
        assert alert.alert_type == AlertType.TRAINING_FAILED
        assert alert.severity == AlertSeverity.CRITICAL
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/monitoring/test_training_alerts.py -v --no-header -q`
Expected: FAIL — AlertType.TRAINING_STARTED not found

- [ ] **Step 3: Add alert types to schemas.py**

Add to `AlertType` enum in `backend/src/monitoring/alerting/schemas.py`:

```python
TRAINING_STARTED = "training_started"
TRAINING_COMPLETE = "training_complete"
TRAINING_FAILED = "training_failed"
```

Add to `_EMOJI_MAP` in same file:

```python
AlertType.TRAINING_STARTED: "\U0001f3cb",   # weight lifter
AlertType.TRAINING_COMPLETE: "\u2705",       # check mark
AlertType.TRAINING_FAILED: "\u274c",         # cross mark
```

- [ ] **Step 4: Add training alert methods to alert_manager.py**

Add after `alert_trade_closed()` in `backend/src/monitoring/alerting/alert_manager.py`:

```python
async def alert_training_started(self, epic: str) -> None:
    alert = Alert(
        alert_type=AlertType.TRAINING_STARTED,
        severity=AlertSeverity.INFO,
        title=f"Training Started: {epic}",
        message=f"Model training initiated for {epic}.",
        epic=epic,
    )
    await self.send_alert(alert)

async def alert_training_complete(
    self, epic: str, f1: float, accuracy: float, duration_s: float,
) -> None:
    alert = Alert(
        alert_type=AlertType.TRAINING_COMPLETE,
        severity=AlertSeverity.INFO,
        title=f"Training Complete: {epic}",
        message=(
            f"Model trained for {epic} in {duration_s:.0f}s. "
            f"F1={f1:.4f}, Accuracy={accuracy:.4f}"
        ),
        epic=epic,
        details={"f1": f1, "accuracy": accuracy, "duration_seconds": duration_s},
    )
    await self.send_alert(alert)

async def alert_training_failed(self, epic: str, error: str) -> None:
    alert = Alert(
        alert_type=AlertType.TRAINING_FAILED,
        severity=AlertSeverity.CRITICAL,
        title=f"Training Failed: {epic}",
        message=f"Model training failed for {epic}: {error}",
        epic=epic,
        details={"error": error},
    )
    await self.send_alert(alert)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/monitoring/test_training_alerts.py -v --no-header -q`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/src/monitoring/alerting/schemas.py backend/src/monitoring/alerting/alert_manager.py backend/tests/monitoring/test_training_alerts.py
git commit -m "feat(alerts): add training started/complete/failed alert types"
```

---

## Task 4: Training Orchestrator (parallel jobs + status + hot reload)

**Files:**
- Create: `backend/src/models/training_orchestrator.py`
- Modify: `backend/src/models/prediction_service.py` (add `reload_model`)
- Test: `backend/tests/models/test_training_orchestrator.py`

- [ ] **Step 1: Add `reload_model()` to PredictionService**

In `backend/src/models/prediction_service.py`, add after `has_model_for()`:

```python
def reload_model(self, epic: str) -> bool:
    """Hot-reload a single model from disk (after retraining).

    Returns True if successfully reloaded, False otherwise.
    """
    try:
        models = self._versioning.list_models(epic)
        xgb_models = [m for m in models if m.model_type == "xgboost"]
        if not xgb_models:
            logger.warning(f"No XGBoost model found for {epic} during reload")
            return False

        latest = xgb_models[0]
        model = self._versioning.load_model(XGBoostClassifier, epic, latest.model_id)
        meta = latest

        # Load calibrator
        calibrator = None
        cal_path = self._versioning.model_dir / epic / latest.model_id / "calibration"
        if cal_path.exists():
            calibrator = ConfidenceCalibrator.load(str(cal_path))

        self._loaded_models[epic] = (model, meta)
        if calibrator:
            self._calibrators[epic] = calibrator
        elif epic in self._calibrators:
            del self._calibrators[epic]

        logger.info(
            f"Hot-reloaded model for {epic}: {latest.model_id} "
            f"({meta.num_features} features)"
        )
        return True
    except Exception as e:
        logger.error(f"Failed to hot-reload model for {epic}: {e}")
        return False
```

- [ ] **Step 2: Write failing test for orchestrator**

```python
# backend/tests/models/test_training_orchestrator.py
"""Tests for training orchestrator."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

from src.models.training_orchestrator import TrainingOrchestrator, TrainingJobStatus


class TestTrainingOrchestrator:
    @pytest.fixture
    def orchestrator(self):
        return TrainingOrchestrator(max_parallel=2)

    def test_initial_status_idle(self, orchestrator):
        status = orchestrator.get_status()
        assert status["running"] is False
        assert status["jobs"] == {}
        assert status["queue"] == []

    def test_max_parallel_respected(self, orchestrator):
        assert orchestrator.max_parallel == 2

    def test_job_status_enum(self):
        assert TrainingJobStatus.QUEUED == "queued"
        assert TrainingJobStatus.RUNNING == "running"
        assert TrainingJobStatus.COMPLETED == "completed"
        assert TrainingJobStatus.FAILED == "failed"

    def test_get_job_status_unknown(self, orchestrator):
        assert orchestrator.get_job_status("UNKNOWN") is None
```

- [ ] **Step 3: Write orchestrator implementation**

```python
# backend/src/models/training_orchestrator.py
"""Training orchestrator — manages parallel model training jobs.

Coordinates training of multiple epics with configurable parallelism,
tracks progress, fires alerts, and hot-reloads models on completion.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from enum import Enum

from loguru import logger

from src.utils.config import get_settings


class TrainingJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrainingJob:
    """State for a single epic training job."""

    __slots__ = (
        "epic", "status", "started_at", "completed_at",
        "error", "metrics", "progress",
    )

    def __init__(self, epic: str):
        self.epic = epic
        self.status = TrainingJobStatus.QUEUED
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.error: str | None = None
        self.metrics: dict | None = None
        self.progress: str = "Queued"

    def to_dict(self) -> dict:
        return {
            "epic": self.epic,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": (
                (self.completed_at - self.started_at).total_seconds()
                if self.started_at and self.completed_at
                else None
            ),
            "error": self.error,
            "metrics": self.metrics,
            "progress": self.progress,
        }


class TrainingOrchestrator:
    """Manages parallel model training with status tracking and alerts."""

    def __init__(self, max_parallel: int = 2):
        self.max_parallel = max_parallel
        self._jobs: dict[str, TrainingJob] = {}
        self._queue: list[str] = []
        self._running = False
        self._executor = ThreadPoolExecutor(max_workers=max_parallel)
        self._prediction_service = None  # Set from app state
        self._ws_broadcast = None  # Set from app state

    def set_prediction_service(self, ps) -> None:
        self._prediction_service = ps

    def set_ws_broadcast(self, fn) -> None:
        self._ws_broadcast = fn

    def get_status(self) -> dict:
        return {
            "running": self._running,
            "max_parallel": self.max_parallel,
            "jobs": {
                epic: job.to_dict() for epic, job in self._jobs.items()
            },
            "queue": list(self._queue),
            "completed_count": sum(
                1 for j in self._jobs.values()
                if j.status == TrainingJobStatus.COMPLETED
            ),
            "failed_count": sum(
                1 for j in self._jobs.values()
                if j.status == TrainingJobStatus.FAILED
            ),
        }

    def get_job_status(self, epic: str) -> dict | None:
        job = self._jobs.get(epic)
        return job.to_dict() if job else None

    async def train_epics(
        self,
        epics: list[str],
        timeframe: str = "1h",
        config: dict | None = None,
    ) -> None:
        """Queue training for multiple epics and start processing."""
        if self._running:
            raise RuntimeError("Training already in progress")

        self._running = True
        self._jobs.clear()
        self._queue.clear()

        for epic in epics:
            self._jobs[epic] = TrainingJob(epic)
            self._queue.append(epic)

        logger.info(
            f"Training orchestrator started: {len(epics)} epics, "
            f"max_parallel={self.max_parallel}"
        )

        try:
            semaphore = asyncio.Semaphore(self.max_parallel)
            tasks = [
                self._train_one(epic, semaphore, timeframe, config or {})
                for epic in epics
            ]
            await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            self._running = False
            self._queue.clear()
            logger.info("Training orchestrator finished")

    async def _train_one(
        self,
        epic: str,
        semaphore: asyncio.Semaphore,
        timeframe: str,
        config: dict,
    ) -> None:
        """Train a single epic with semaphore-controlled parallelism."""
        job = self._jobs[epic]

        async with semaphore:
            if epic in self._queue:
                self._queue.remove(epic)
            job.status = TrainingJobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc)
            job.progress = "Training..."
            await self._broadcast_status()

            # Fire alert
            try:
                from src.monitoring.alerting.alert_manager import get_alert_manager
                await get_alert_manager().alert_training_started(epic)
            except Exception:
                pass

            try:
                result = await self._run_training(epic, timeframe, config)
                job.status = TrainingJobStatus.COMPLETED
                job.completed_at = datetime.now(timezone.utc)
                job.metrics = result
                job.progress = "Complete"
                duration = (job.completed_at - job.started_at).total_seconds()

                # Hot reload
                if self._prediction_service:
                    reloaded = self._prediction_service.reload_model(epic)
                    job.progress = "Reloaded" if reloaded else "Complete (reload failed)"

                # Fire complete alert
                try:
                    am = get_alert_manager()
                    await am.alert_training_complete(
                        epic=epic,
                        f1=result.get("f1_macro", 0),
                        accuracy=result.get("accuracy", 0),
                        duration_s=duration,
                    )
                except Exception:
                    pass

                logger.info(
                    f"Training complete: {epic} in {duration:.0f}s "
                    f"F1={result.get('f1_macro', 0):.4f}"
                )

            except Exception as e:
                job.status = TrainingJobStatus.FAILED
                job.completed_at = datetime.now(timezone.utc)
                job.error = str(e)
                job.progress = f"Failed: {e}"
                logger.error(f"Training failed for {epic}: {e}")

                try:
                    am = get_alert_manager()
                    await am.alert_training_failed(epic, str(e))
                except Exception:
                    pass

            await self._broadcast_status()

    async def _run_training(self, epic: str, timeframe: str, config: dict) -> dict:
        """Execute model training in thread pool."""
        from src.models.trainer import ModelTrainer
        from src.models.xgboost_model import XGBoostClassifier
        from src.features.builder import FeatureBuilder

        trainer = ModelTrainer(feature_builder=FeatureBuilder())
        model = XGBoostClassifier()

        # Run in executor to not block event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            self._executor,
            lambda: trainer.train(
                model=model,
                epic=epic,
                timeframe=timeframe,
                save_best=True,
            ),
        )

        # Extract key metrics
        avg_test = result.avg_test_metrics or {}
        return {
            "f1_macro": avg_test.get("f1_macro", 0),
            "accuracy": avg_test.get("accuracy", 0),
            "num_features": result.num_features,
            "num_folds": result.num_folds,
            "duration_seconds": result.training_duration_seconds,
        }

    async def _broadcast_status(self) -> None:
        """Broadcast training status via WebSocket."""
        if self._ws_broadcast:
            try:
                await self._ws_broadcast("training", self.get_status())
            except Exception:
                pass
```

- [ ] **Step 4: Run tests**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/models/test_training_orchestrator.py -v --no-header -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/models/training_orchestrator.py backend/src/models/prediction_service.py backend/tests/models/test_training_orchestrator.py
git commit -m "feat(training): add training orchestrator with parallel jobs and hot reload"
```

---

## Task 5: Training API Endpoints

**Files:**
- Modify: `backend/src/api/routers/models.py` (new endpoints)
- Modify: `backend/src/api/main.py` (wire orchestrator into app state)

- [ ] **Step 1: Wire orchestrator into app state**

In `backend/src/api/main.py`, after the paper_loop initialization:

```python
# Training orchestrator
from src.models.training_orchestrator import TrainingOrchestrator
app.state.training_orchestrator = TrainingOrchestrator(max_parallel=2)
app.state.training_orchestrator.set_prediction_service(app.state.prediction_service)
try:
    from src.api.websocket import ws_manager
    app.state.training_orchestrator.set_ws_broadcast(ws_manager.broadcast)
except Exception:
    pass
logger.info("Training orchestrator initialized (max_parallel=2)")
```

- [ ] **Step 2: Add API endpoints**

In `backend/src/api/routers/models.py`, add:

```python
@router.get("/training/status")
async def get_training_status(request: Request):
    """Get current training orchestrator status."""
    orch = getattr(request.app.state, "training_orchestrator", None)
    if orch is None:
        return error_response("Training orchestrator not initialized", 503)
    return success_response(orch.get_status())


@router.post("/training/start")
async def start_training(
    request: Request,
    body: dict | None = None,
):
    """Start training for specified epics or all.

    Body (optional):
        epics: list[str] — specific epics to train (default: all)
        timeframe: str — "1h" (default), "4h", "1d"
        config: dict — advanced training config
    """
    orch = getattr(request.app.state, "training_orchestrator", None)
    if orch is None:
        return error_response("Training orchestrator not initialized", 503)

    if orch._running:
        return error_response("Training already in progress", 409)

    body = body or {}
    from src.utils.constants import TRADABLE_ASSETS
    epics = body.get("epics") or list(TRADABLE_ASSETS)
    timeframe = body.get("timeframe", "1h")
    config = body.get("config", {})

    # Launch in background
    import asyncio
    asyncio.create_task(orch.train_epics(epics, timeframe, config))

    return success_response({
        "message": f"Training started for {len(epics)} epics",
        "epics": epics,
        "timeframe": timeframe,
    })


@router.post("/training/start/{epic}")
async def start_training_single(request: Request, epic: str):
    """Start training for a single epic."""
    orch = getattr(request.app.state, "training_orchestrator", None)
    if orch is None:
        return error_response("Training orchestrator not initialized", 503)

    if orch._running:
        return error_response("Training already in progress", 409)

    import asyncio
    asyncio.create_task(orch.train_epics([epic]))

    return success_response({
        "message": f"Training started for {epic}",
        "epic": epic,
    })
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/api/routers/models.py backend/src/api/main.py
git commit -m "feat(api): add training status and control endpoints"
```

---

## Task 6: Frontend — Training Tab in AI Models Page

**Files:**
- Modify: `frontend/src/app/core/models/index.ts` (add interfaces)
- Modify: `frontend/src/app/core/services/trading.service.ts` (add training methods)
- Modify: `frontend/src/app/views/ai-models/ai-models.component.ts` (add Training tab)
- Modify: `frontend/src/app/views/ai-models/ai-models.component.scss` (training styles)

- [ ] **Step 1: Add TypeScript interfaces**

In `frontend/src/app/core/models/index.ts`:

```typescript
// Training
export interface TrainingJobInfo {
  epic: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error: string | null;
  metrics: { f1_macro: number; accuracy: number; num_features: number } | null;
  progress: string;
}

export interface TrainingStatus {
  running: boolean;
  max_parallel: number;
  jobs: Record<string, TrainingJobInfo>;
  queue: string[];
  completed_count: number;
  failed_count: number;
}
```

- [ ] **Step 2: Add service methods**

In `frontend/src/app/core/services/trading.service.ts`:

```typescript
readonly trainingStatus = signal<TrainingStatus | null>(null);

loadTrainingStatus(): void {
  this.api.get<TrainingStatus>('/api/models/training/status')
    .subscribe({ next: data => this.trainingStatus.set(data), error: () => {} });
}

startTraining(epics?: string[], timeframe?: string): void {
  const body: Record<string, any> = {};
  if (epics) body['epics'] = epics;
  if (timeframe) body['timeframe'] = timeframe;
  this.api.post<any>('/api/models/training/start', body)
    .subscribe({ next: () => this.loadTrainingStatus(), error: () => {} });
}

startTrainingSingle(epic: string): void {
  this.api.post<any>(`/api/models/training/start/${epic}`)
    .subscribe({ next: () => this.loadTrainingStatus(), error: () => {} });
}
```

- [ ] **Step 3: Add Training tab to AI Models component**

Update `ai-models.component.ts` template to add a tab header with "Modelli" and "Training" tabs. The Training tab shows:

1. **Status banner** — "Training in corso: 3/20 completati" or "Nessun training attivo"
2. **Start button** — "Retrain All" + dropdown per singolo epic
3. **Jobs grid** — card per epic con status badge (queued/running/completed/failed), progress bar, F1 metric when done
4. **Config toggle** — switch between basic (just the button) and advanced (timeframe, lookback days)

Key template additions:

```html
<!-- Tab header -->
<ul cNav variant="tabs" role="tablist" class="mb-3">
  <li cNavItem><a cNavLink [active]="activeTab() === 'models'" (click)="activeTab.set('models')">Modelli</a></li>
  <li cNavItem><a cNavLink [active]="activeTab() === 'training'" (click)="activeTab.set('training')">Training</a></li>
</ul>

<!-- Training tab content -->
@if (activeTab() === 'training') {
  <c-card class="border-top border-top-3 border-top-primary mb-3">
    <c-card-header class="d-flex align-items-center justify-content-between py-2">
      <span class="fw-semibold small text-body-secondary">Training Control</span>
      <app-loading-button color="primary" size="sm"
        [loading]="trainingStatus()?.running ?? false"
        (clicked)="startRetrainAll()">
        Retrain All
      </app-loading-button>
    </c-card-header>
    <c-card-body class="p-3">
      @if (trainingStatus()?.running) {
        <div class="mb-2 small">
          Completati: {{ trainingStatus()!.completed_count }} /
          {{ Object.keys(trainingStatus()!.jobs).length }}
          | Failed: {{ trainingStatus()!.failed_count }}
        </div>
      }
      <div class="row g-2">
        @for (job of trainingJobs(); track job.epic) {
          <div class="col-6 col-xl-3">
            <div class="training-job-card" [class]="'training-job-card--' + job.status">
              <div class="d-flex align-items-center gap-2 mb-1">
                <app-epic-logo [epic]="job.epic" [size]="20"></app-epic-logo>
                <span class="fw-semibold small">{{ job.epic }}</span>
                <c-badge [color]="jobColor(job.status)" class="badge-sm ms-auto">
                  {{ job.status }}
                </c-badge>
              </div>
              <div class="small text-body-secondary">{{ job.progress }}</div>
              @if (job.metrics) {
                <div class="mantis-mono small mt-1">
                  F1: {{ (job.metrics.f1_macro * 100).toFixed(1) }}%
                </div>
              }
            </div>
          </div>
        }
      </div>
    </c-card-body>
  </c-card>
}
```

- [ ] **Step 4: Add training styles to SCSS**

```scss
.training-job-card {
  padding: 0.75rem;
  border-radius: 8px;
  border: 1px solid var(--mantis-border-default);
  background: var(--cui-card-bg);
  transition: border-color 0.2s ease;

  &--queued { border-left: 3px solid var(--mantis-neutral); }
  &--running { border-left: 3px solid var(--mantis-cyan); }
  &--completed { border-left: 3px solid var(--mantis-profit); }
  &--failed { border-left: 3px solid var(--mantis-loss); }
}
```

- [ ] **Step 5: Build and verify**

Run: `cd frontend && npx ng build --configuration=development 2>&1 | grep -i error`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/core/models/index.ts frontend/src/app/core/services/trading.service.ts frontend/src/app/views/ai-models/
git commit -m "ui: add Training tab to AI Models page with retrain controls"
```

---

## Task 7: WebSocket Training Status Broadcast

**Files:**
- Modify: `backend/src/api/websocket.py` (add training channel)
- Modify: `frontend/src/app/core/services/websocket.service.ts` (listen for training updates)

- [ ] **Step 1: Add training channel to WebSocket manager**

The existing `ws_manager.broadcast(channel, data)` already supports arbitrary channels. The orchestrator calls `ws_manager.broadcast("training", status_dict)`. No backend change needed.

- [ ] **Step 2: Add training signal to WebSocket service**

In `frontend/src/app/core/services/websocket.service.ts`, add:

```typescript
readonly trainingUpdate = signal<any>(null);
```

In the message handler, add:

```typescript
case 'training':
  this.trainingUpdate.set(msg.data);
  break;
```

- [ ] **Step 3: Connect training tab to WebSocket updates**

In the AI Models component, use an `effect()` to update the training status from WebSocket:

```typescript
constructor() {
  effect(() => {
    const update = this.ws.trainingUpdate();
    if (update) {
      this.trading.trainingStatus.set(update);
    }
  });
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/core/services/websocket.service.ts frontend/src/app/views/ai-models/
git commit -m "feat(ws): add real-time training status updates via WebSocket"
```

---

## Task 8: Integration — Wire Everything Together

- [ ] **Step 1: Test full flow locally**

```bash
# Terminal 1: Start backend
cd backend && .venv/Scripts/python.exe -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Start frontend
cd frontend && npx ng serve --port 4321

# Terminal 3: Trigger training
curl -X POST http://localhost:8000/api/models/training/start -H "Content-Type: application/json" -d '{"epics": ["XAUUSD"]}'

# Check status
curl http://localhost:8000/api/models/training/status
```

- [ ] **Step 2: Verify Telegram notification received**

Check Telegram for "Training Started: XAUUSD" and "Training Complete: XAUUSD" messages.

- [ ] **Step 3: Verify hot reload**

After training completes, check logs for "Hot-reloaded model for XAUUSD" and verify the model version in `/api/models/` has changed.

- [ ] **Step 4: Verify UI**

Open browser to `http://localhost:4321`, navigate to "Modelli AI" → "Training" tab. Click "Retrain All" and observe real-time job cards updating.

- [ ] **Step 5: Run full test suite**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ --no-header -q
```
Expected: all pass, no regressions.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "feat: training dashboard with parallel jobs, hot reload, and notifications"
git push origin master
```

---

## Future Tasks (not in this plan)

These are deferred to a follow-up plan:

1. **Extended data integration into training** — Use `ExtendedDataProvider` in `ModelTrainer.train()` to merge yfinance/CryptoCompare data with broker data before feature building
2. **Advanced config UI** — Form fields for Optuna trials, walk-forward params, feature selection
3. **Backtest from training dashboard** — Button to run OOS backtest on newly trained model
4. **CryptoCompare pagination** — Fetch >2000 bars via recursive pagination for multi-year crypto history
5. **Training scheduler** — Cron-based automatic retraining (weekly/monthly)
