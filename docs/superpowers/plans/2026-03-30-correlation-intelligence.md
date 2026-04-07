# Correlation Intelligence System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 3-level correlation intelligence to MANTIS AI — cross-asset features for ML models, dynamic correlation regime detection, and portfolio-aware position sizing.

**Architecture:** A new `CrossAssetEngine` computes and caches rolling correlations + lead-lag returns across all 20 tradable assets. Level 1 injects cross-asset features into the feature builder for XGBoost training/prediction. Level 2 adds a correlation regime detector that triggers risk adjustments when cross-asset correlations spike. Level 3 replaces the hardcoded `CorrelationGuard` with a dynamic version using the live correlation matrix.

**Tech Stack:** Python 3.12, Polars, numpy, existing FeatureBuilder/DataAccessLayer/CorrelationGuard classes.

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| **Create** | `src/features/cross_asset.py` | CrossAssetEngine: compute rolling correlations, lead-lag returns, sector momentum, and correlation regime metrics |
| **Create** | `src/features/cross_asset_config.py` | Asset cluster definitions, lead-lag pairs, correlation thresholds |
| **Create** | `tests/test_cross_asset.py` | Unit tests for CrossAssetEngine |
| **Create** | `tests/test_correlation_guard_dynamic.py` | Tests for dynamic CorrelationGuard |
| **Modify** | `src/features/builder.py:138-277` | Add `cross_asset: bool` param to `build_features()`, call `CrossAssetEngine` in pipeline |
| **Modify** | `src/features/schemas.py` | Add `cross_asset_features` field to `FeatureMatrix` |
| **Modify** | `src/models/trainer.py:51-121` | Pass `cross_asset=True` to `build_features()` during training |
| **Modify** | `src/models/prediction_service.py:94-216` | Pass `cross_asset=True` during live prediction |
| **Modify** | `src/risk/correlation_guard.py` | Replace hardcoded pairs with dynamic correlation matrix lookup |
| **Modify** | `src/risk/risk_manager.py:239-250` | Pass DataAccessLayer to CorrelationGuard, add regime check |
| **Modify** | `src/trading/paper_loop.py:~1326` | Initialize CrossAssetEngine, pass to feature builder |
| **Modify** | `src/utils/config.py` | Add `CROSS_ASSET_ENABLED`, `CORRELATION_REGIME_THRESHOLD` settings |
| **Modify** | `src/utils/constants.py` | Add `ASSET_CLUSTERS` dict |
| **Modify** | `src/api/routers/analytics.py` | Add `/correlation-regime` endpoint |

---

## Level 1: Cross-Asset Features for ML Models

### Task 1: Asset Cluster Definitions

**Files:**
- Modify: `src/utils/constants.py`
- Create: `src/features/cross_asset_config.py`

- [ ] **Step 1: Define asset clusters in constants.py**

Add after line 66 (`STOCK_ASSETS`):

```python
# Cross-asset correlation clusters
# Each asset maps to its cluster leader(s) — assets whose returns
# are used as features for this asset's ML model.
ASSET_CLUSTERS: dict[str, list[str]] = {
    # Crypto: BTC leads the pack
    "BTCUSD": ["US500", "XAUUSD"],       # BTC vs risk-on (S&P) and safe-haven (gold)
    "ETHUSD": ["BTCUSD", "US500"],        # ETH follows BTC + risk-on
    "SOLUSD": ["BTCUSD", "ETHUSD"],       # SOL follows BTC/ETH
    "BNBUSD": ["BTCUSD", "ETHUSD"],
    "DOGUSD": ["BTCUSD", "ETHUSD"],
    "DASHUSD": ["BTCUSD", "ETHUSD"],
    "ICPUSD": ["BTCUSD", "ETHUSD"],
    # Commodities: Gold leads, oil separate
    "XAUUSD": ["USDJPY", "US500"],        # Gold vs USD strength and risk
    "XAGUSD": ["XAUUSD", "COPPER"],       # Silver follows gold + industrial
    "WTIUSD": ["US500", "COPPER"],         # Oil = growth proxy
    "NATGAS": ["WTIUSD", "COPPER"],        # Energy cluster
    "COPPER": ["US500", "WTIUSD"],         # Industrial bellwether
    "PLATINUM": ["XAUUSD", "COPPER"],      # Precious + industrial
    # Forex: USD index dynamics
    "EURUSD": ["GBPUSD", "USDJPY"],       # EUR = anti-USD
    "GBPUSD": ["EURUSD", "US500"],
    "USDJPY": ["XAUUSD", "US500"],         # JPY = safe-haven inverse
    # Indices: co-move strongly
    "US500": ["NAS100", "DE40"],
    "DE40": ["US500", "EURUSD"],
    "NAS100": ["US500", "NVDA"],
    # Stocks: sector + index
    "NVDA": ["NAS100", "US500"],
    "TSLA": ["NAS100", "US500"],
}
```

- [ ] **Step 2: Create cross-asset config with lead-lag settings**

Create `src/features/cross_asset_config.py`:

```python
"""
Cross-asset feature configuration.
Defines correlation windows, lead-lag settings, and sector momentum parameters.
"""

# Rolling correlation window (in bars of the primary timeframe)
CORRELATION_WINDOW_SHORT = 20   # ~1 day of 1h bars — captures fast regime shifts
CORRELATION_WINDOW_LONG = 100   # ~4 days — captures structural correlation

# Lead-lag return windows: how many bars back to look for cross-asset returns
LEAD_LAG_WINDOWS = [1, 3, 6]   # 1h, 3h, 6h lead signals

# Maximum number of cross-asset features per related epic
# (2 correlations + N lead-lag returns + 1 sector momentum = ~9 features per pair)
# With 2 related epics → ~18 new features per asset — manageable for XGBoost

# Sector momentum: simple average of returns within the cluster
SECTOR_MOMENTUM_WINDOW = 12    # 12h rolling average of cluster returns

# Correlation regime thresholds
CORR_REGIME_PANIC_THRESHOLD = 0.75   # Mean cross-asset correlation > 0.75 = panic
CORR_REGIME_NORMAL_RANGE = (0.20, 0.55)  # Normal correlation range
```

- [ ] **Step 3: Commit**

```bash
git add src/utils/constants.py src/features/cross_asset_config.py
git commit -m "feat: add asset cluster definitions and cross-asset config"
```

---

### Task 2: CrossAssetEngine Core

**Files:**
- Create: `src/features/cross_asset.py`
- Create: `tests/test_cross_asset.py`

- [ ] **Step 1: Write failing tests for CrossAssetEngine**

Create `tests/test_cross_asset.py`:

```python
"""Tests for cross-asset feature computation."""

import numpy as np
import polars as pl
import pytest
from datetime import datetime, timedelta

from src.features.cross_asset import CrossAssetEngine


def _make_ohlcv(n: int, base_price: float = 100.0, seed: int = 42) -> pl.DataFrame:
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    prices = base_price + np.cumsum(rng.normal(0, 0.5, n))
    timestamps = [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(n)]
    return pl.DataFrame({
        "timestamp": timestamps,
        "open": prices,
        "high": prices + rng.uniform(0, 1, n),
        "low": prices - rng.uniform(0, 1, n),
        "close": prices + rng.normal(0, 0.2, n),
        "volume": rng.integers(100, 10000, n),
    })


class TestCrossAssetEngine:
    def test_compute_rolling_correlation(self):
        """Rolling correlation between two price series."""
        n = 200
        rng = np.random.default_rng(42)
        # Create correlated series: Y = 0.8*X + noise
        x = np.cumsum(rng.normal(0, 1, n))
        y = 0.8 * x + np.cumsum(rng.normal(0, 0.5, n))

        df_main = pl.DataFrame({
            "timestamp": [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(n)],
            "close": x.tolist(),
        })
        df_related = pl.DataFrame({
            "timestamp": [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(n)],
            "close": y.tolist(),
        })

        engine = CrossAssetEngine()
        result = engine.compute_rolling_correlation(df_main, df_related, window=50)

        assert "rolling_corr_50" in result.columns
        # Last values should show strong positive correlation
        last_corr = result["rolling_corr_50"][-1]
        assert last_corr > 0.5, f"Expected high correlation, got {last_corr}"

    def test_compute_lead_lag_returns(self):
        """Lead-lag returns from a related asset."""
        n = 100
        df_related = _make_ohlcv(n, seed=42)

        engine = CrossAssetEngine()
        result = engine.compute_lead_lag_returns(df_related, lags=[1, 3, 6])

        assert "ret_lag_1" in result.columns
        assert "ret_lag_3" in result.columns
        assert "ret_lag_6" in result.columns
        assert len(result) == n
        # First rows should be null due to lag
        assert result["ret_lag_6"][0] is None

    def test_compute_sector_momentum(self):
        """Sector momentum = average returns across cluster."""
        n = 100
        dfs = {
            "BTCUSD": _make_ohlcv(n, base_price=60000, seed=1),
            "ETHUSD": _make_ohlcv(n, base_price=2000, seed=2),
            "SOLUSD": _make_ohlcv(n, base_price=80, seed=3),
        }

        engine = CrossAssetEngine()
        result = engine.compute_sector_momentum(dfs, window=12)

        assert "sector_momentum_12" in result.columns
        assert "sector_dispersion_12" in result.columns
        assert len(result) == n

    def test_build_cross_asset_features(self):
        """Full cross-asset feature build for one epic."""
        n = 200
        main_df = _make_ohlcv(n, base_price=3000, seed=10)
        related_dfs = {
            "BTCUSD": _make_ohlcv(n, base_price=60000, seed=20),
            "US500": _make_ohlcv(n, base_price=5000, seed=30),
        }

        engine = CrossAssetEngine()
        result = engine.build_cross_asset_features(
            main_df=main_df,
            epic="XAUUSD",
            related_dfs=related_dfs,
        )

        # Should have original columns + cross-asset features
        assert len(result) == n
        # Check for expected cross-asset columns
        cross_cols = [c for c in result.columns if c.startswith(("corr_", "lead_", "sector_"))]
        assert len(cross_cols) > 0, f"No cross-asset columns found. Columns: {result.columns}"
        # At least: 2 correlations * 2 windows + 2 epics * 3 lags + 2 sector = ~12 features
        assert len(cross_cols) >= 8, f"Expected >=8 cross-asset features, got {len(cross_cols)}"

    def test_empty_related_dfs(self):
        """Graceful handling when no related data available."""
        main_df = _make_ohlcv(100, seed=10)

        engine = CrossAssetEngine()
        result = engine.build_cross_asset_features(
            main_df=main_df,
            epic="XAUUSD",
            related_dfs={},
        )

        # Should return original df unchanged
        assert result.columns == main_df.columns

    def test_mismatched_lengths(self):
        """Related asset has fewer bars — should align correctly."""
        main_df = _make_ohlcv(200, seed=10)
        short_df = _make_ohlcv(100, seed=20)

        engine = CrossAssetEngine()
        result = engine.build_cross_asset_features(
            main_df=main_df,
            epic="XAUUSD",
            related_dfs={"BTCUSD": short_df},
        )

        assert len(result) == 200  # Main df length preserved


class TestCorrelationRegime:
    def test_compute_correlation_regime(self):
        """Correlation regime detection across all assets."""
        n = 200
        rng = np.random.default_rng(42)
        # Create highly correlated cluster (simulating panic)
        base = np.cumsum(rng.normal(0, 1, n))
        all_dfs = {
            f"ASSET_{i}": pl.DataFrame({
                "timestamp": [datetime(2026, 1, 1) + timedelta(hours=j) for j in range(n)],
                "close": (base + rng.normal(0, 0.3, n)).tolist(),
            })
            for i in range(5)
        }

        engine = CrossAssetEngine()
        regime = engine.compute_correlation_regime(all_dfs, window=50)

        assert "mean_correlation" in regime.columns
        assert "correlation_regime" in regime.columns
        # Highly correlated data should show "panic" regime
        last_regime = regime["correlation_regime"][-1]
        assert last_regime in ("panic", "elevated", "normal", "decorrelated")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cross_asset.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.features.cross_asset'`

- [ ] **Step 3: Implement CrossAssetEngine**

Create `src/features/cross_asset.py`:

```python
"""
Cross-asset feature engine.
Computes rolling correlations, lead-lag returns, sector momentum,
and correlation regime metrics across the MANTIS AI asset universe.
"""

import numpy as np
import polars as pl
from loguru import logger

from src.features.cross_asset_config import (
    CORRELATION_WINDOW_LONG,
    CORRELATION_WINDOW_SHORT,
    CORR_REGIME_NORMAL_RANGE,
    CORR_REGIME_PANIC_THRESHOLD,
    LEAD_LAG_WINDOWS,
    SECTOR_MOMENTUM_WINDOW,
)


class CrossAssetEngine:
    """Computes cross-asset features for ML model training and prediction."""

    def compute_rolling_correlation(
        self,
        df_main: pl.DataFrame,
        df_related: pl.DataFrame,
        window: int = 50,
    ) -> pl.DataFrame:
        """Compute rolling Pearson correlation of log returns between two assets.

        Args:
            df_main: Main asset DataFrame (must have 'close' column)
            df_related: Related asset DataFrame (must have 'close' and 'timestamp')
            window: Rolling window size in bars

        Returns:
            DataFrame with 'rolling_corr_{window}' column, aligned to main df
        """
        # Compute log returns
        main_rets = np.diff(np.log(np.maximum(df_main["close"].to_numpy(), 1e-10)))
        related_rets = np.diff(np.log(np.maximum(df_related["close"].to_numpy(), 1e-10)))

        # Align to shorter length
        min_len = min(len(main_rets), len(related_rets))
        main_rets = main_rets[-min_len:]
        related_rets = related_rets[-min_len:]

        # Rolling correlation
        corr = np.full(len(df_main), np.nan)
        offset = len(df_main) - min_len
        for i in range(window, min_len + 1):
            x = main_rets[i - window : i]
            y = related_rets[i - window : i]
            std_x = np.std(x)
            std_y = np.std(y)
            if std_x > 1e-10 and std_y > 1e-10:
                corr[offset + i] = float(np.corrcoef(x, y)[0, 1])

        return df_main.with_columns(
            pl.Series(f"rolling_corr_{window}", corr)
        )

    def compute_lead_lag_returns(
        self,
        df_related: pl.DataFrame,
        lags: list[int] | None = None,
    ) -> pl.DataFrame:
        """Compute lagged log returns from a related asset.

        These capture how the related asset moved N bars ago —
        the ML model can learn if those moves predict our asset.

        Args:
            df_related: Related asset DataFrame with 'close'
            lags: Lag periods in bars (default: [1, 3, 6])

        Returns:
            DataFrame with 'ret_lag_{N}' columns
        """
        if lags is None:
            lags = LEAD_LAG_WINDOWS

        closes = df_related["close"]
        result = df_related

        for lag in lags:
            ret = closes.log().diff(lag)
            result = result.with_columns(ret.alias(f"ret_lag_{lag}"))

        return result

    def compute_sector_momentum(
        self,
        cluster_dfs: dict[str, pl.DataFrame],
        window: int | None = None,
    ) -> pl.DataFrame:
        """Compute average rolling return across a cluster of assets.

        Captures whether the entire sector is moving together.

        Args:
            cluster_dfs: Dict of epic -> DataFrame for cluster members
            window: Rolling average window (default: SECTOR_MOMENTUM_WINDOW)

        Returns:
            DataFrame with 'sector_momentum_{window}' and 'sector_dispersion_{window}'
        """
        if window is None:
            window = SECTOR_MOMENTUM_WINDOW

        if not cluster_dfs:
            return pl.DataFrame()

        # Get common length
        lengths = [len(df) for df in cluster_dfs.values()]
        n = min(lengths)

        # Compute 1-bar log returns for each asset, aligned to tail
        all_rets = []
        for df in cluster_dfs.values():
            closes = df["close"].tail(n).to_numpy()
            rets = np.diff(np.log(np.maximum(closes, 1e-10)))
            rets = np.insert(rets, 0, 0.0)  # pad first value
            all_rets.append(rets)

        rets_matrix = np.array(all_rets)  # shape: (n_assets, n_bars)
        avg_ret = np.mean(rets_matrix, axis=0)
        dispersion = np.std(rets_matrix, axis=0)

        # Rolling average for smoothing
        momentum = np.convolve(avg_ret, np.ones(window) / window, mode="same")
        disp_smooth = np.convolve(dispersion, np.ones(window) / window, mode="same")

        # Build result using first df's timestamps
        first_df = list(cluster_dfs.values())[0]
        timestamps = first_df["timestamp"].tail(n)

        return pl.DataFrame({
            "timestamp": timestamps,
            f"sector_momentum_{window}": momentum.tolist(),
            f"sector_dispersion_{window}": disp_smooth.tolist(),
        })

    def build_cross_asset_features(
        self,
        main_df: pl.DataFrame,
        epic: str,
        related_dfs: dict[str, pl.DataFrame],
    ) -> pl.DataFrame:
        """Build all cross-asset features for a single epic.

        Combines rolling correlations, lead-lag returns, and sector momentum
        into the main DataFrame.

        Args:
            main_df: Main asset's feature DataFrame (must have 'close', 'timestamp')
            epic: Main asset epic name
            related_dfs: Dict of related_epic -> DataFrame

        Returns:
            main_df enriched with cross-asset feature columns
        """
        if not related_dfs:
            return main_df

        result = main_df

        for related_epic, rel_df in related_dfs.items():
            prefix = f"corr_{related_epic.lower()}"

            # Rolling correlations (short + long window)
            for window in [CORRELATION_WINDOW_SHORT, CORRELATION_WINDOW_LONG]:
                corr_df = self.compute_rolling_correlation(result, rel_df, window=window)
                col_name = f"rolling_corr_{window}"
                new_col_name = f"{prefix}_{window}"
                if col_name in corr_df.columns:
                    result = corr_df.rename({col_name: new_col_name})

            # Lead-lag returns
            lag_df = self.compute_lead_lag_returns(rel_df)
            n_main = len(result)
            for lag in LEAD_LAG_WINDOWS:
                col = f"ret_lag_{lag}"
                if col in lag_df.columns:
                    vals = lag_df[col].tail(n_main).to_numpy()
                    # Pad with NaN if related df is shorter
                    if len(vals) < n_main:
                        vals = np.concatenate(
                            [np.full(n_main - len(vals), np.nan), vals]
                        )
                    result = result.with_columns(
                        pl.Series(f"lead_{related_epic.lower()}_{lag}", vals)
                    )

        # Sector momentum (all related assets as the cluster)
        if len(related_dfs) >= 2:
            sector_df = self.compute_sector_momentum(related_dfs)
            if len(sector_df) > 0:
                n_main = len(result)
                for col in sector_df.columns:
                    if col == "timestamp":
                        continue
                    vals = sector_df[col].tail(n_main).to_numpy()
                    if len(vals) < n_main:
                        vals = np.concatenate(
                            [np.full(n_main - len(vals), np.nan), vals]
                        )
                    result = result.with_columns(
                        pl.Series(f"sector_{col}", vals)
                    )

        n_new = len([c for c in result.columns if c not in main_df.columns])
        logger.debug(
            f"[{epic}] Added {n_new} cross-asset features "
            f"from {list(related_dfs.keys())}"
        )
        return result

    def compute_correlation_regime(
        self,
        all_dfs: dict[str, pl.DataFrame],
        window: int = 50,
    ) -> pl.DataFrame:
        """Detect correlation regime across all assets.

        When mean pairwise correlation spikes → panic/risk-off.
        When correlations are low → normal diversified market.

        Args:
            all_dfs: Dict of epic -> DataFrame for all assets
            window: Rolling window for correlation computation

        Returns:
            DataFrame with 'mean_correlation', 'max_correlation',
            'correlation_regime' columns indexed by timestamp
        """
        if len(all_dfs) < 3:
            return pl.DataFrame()

        # Compute log returns for all assets
        epics = sorted(all_dfs.keys())
        lengths = [len(df) for df in all_dfs.values()]
        n = min(lengths)

        returns_matrix = []
        for epic in epics:
            closes = all_dfs[epic]["close"].tail(n).to_numpy()
            rets = np.diff(np.log(np.maximum(closes, 1e-10)))
            returns_matrix.append(rets)

        returns_matrix = np.array(returns_matrix)  # (n_assets, n_bars-1)
        n_assets = len(epics)
        n_bars = returns_matrix.shape[1]

        mean_corrs = np.full(n_bars, np.nan)
        max_corrs = np.full(n_bars, np.nan)

        for t in range(window, n_bars):
            block = returns_matrix[:, t - window : t]
            corr_matrix = np.corrcoef(block)
            # Extract upper triangle (excluding diagonal)
            upper = corr_matrix[np.triu_indices(n_assets, k=1)]
            upper = upper[~np.isnan(upper)]
            if len(upper) > 0:
                mean_corrs[t] = float(np.mean(upper))
                max_corrs[t] = float(np.max(upper))

        # Classify regime
        regimes = []
        for mc in mean_corrs:
            if np.isnan(mc):
                regimes.append(None)
            elif mc >= CORR_REGIME_PANIC_THRESHOLD:
                regimes.append("panic")
            elif mc >= CORR_REGIME_NORMAL_RANGE[1]:
                regimes.append("elevated")
            elif mc >= CORR_REGIME_NORMAL_RANGE[0]:
                regimes.append("normal")
            else:
                regimes.append("decorrelated")

        first_df = list(all_dfs.values())[0]
        # +1 offset because diff() reduces length by 1
        timestamps = first_df["timestamp"].tail(n).to_list()[1:]

        return pl.DataFrame({
            "timestamp": timestamps,
            "mean_correlation": mean_corrs.tolist(),
            "max_correlation": max_corrs.tolist(),
            "correlation_regime": regimes,
        })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_cross_asset.py -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/features/cross_asset.py tests/test_cross_asset.py
git commit -m "feat: implement CrossAssetEngine with correlations, lead-lag, sector momentum"
```

---

### Task 3: Integrate CrossAssetEngine into FeatureBuilder

**Files:**
- Modify: `src/features/builder.py:138-277`
- Modify: `src/features/schemas.py`
- Modify: `src/utils/config.py`

- [ ] **Step 1: Add config setting**

In `src/utils/config.py`, add after the `max_spread_pct` line:

```python
    cross_asset_enabled: bool = Field(default=False, alias="CROSS_ASSET_ENABLED")
```

- [ ] **Step 2: Update FeatureMatrix schema**

In `src/features/schemas.py`, find the `FeatureMatrix` class and add:

```python
    cross_asset_features: list[str] = []  # Names of cross-asset feature columns
```

- [ ] **Step 3: Add `cross_asset` parameter to `build_features()`**

In `src/features/builder.py`, modify the signature at line 138:

```python
    def build_features(
        self,
        epic: str,
        timeframe: str,
        ...
        sil_data: "SILData | None" = None,
        cross_asset: bool = False,  # NEW
    ) -> tuple[pl.DataFrame, FeatureMatrix]:
```

- [ ] **Step 4: Add cross-asset feature step in the pipeline**

In `build_features()`, after the SIL features step (around line 221) and before multi-timeframe alignment, add:

```python
        # Step 5.5: Cross-asset correlation features
        cross_asset_cols: list[str] = []
        if cross_asset and get_settings().cross_asset_enabled:
            try:
                from src.features.cross_asset import CrossAssetEngine
                from src.utils.constants import ASSET_CLUSTERS

                related_epics = ASSET_CLUSTERS.get(epic, [])
                if related_epics:
                    engine = CrossAssetEngine()
                    related_dfs = {}
                    for rel_epic in related_epics:
                        try:
                            rel_df = self.data_access.get_candles(
                                epic=rel_epic,
                                timeframe=timeframe,
                                start_date=start_date,
                                end_date=end_date,
                            )
                            if rel_df is not None and len(rel_df) >= 50:
                                related_dfs[rel_epic] = rel_df
                        except Exception as e:
                            logger.debug(f"[{epic}] Failed to load {rel_epic}: {e}")

                    if related_dfs:
                        cols_before = set(df.columns)
                        df = engine.build_cross_asset_features(
                            main_df=df, epic=epic, related_dfs=related_dfs
                        )
                        cross_asset_cols = [
                            c for c in df.columns if c not in cols_before
                        ]
                        logger.info(
                            f"[{epic}] Added {len(cross_asset_cols)} cross-asset features"
                        )
            except Exception as e:
                logger.warning(f"[{epic}] Cross-asset features failed: {e}")
```

- [ ] **Step 5: Include cross-asset column names in FeatureMatrix**

Where `FeatureMatrix` is constructed (around line 270), add:

```python
        feature_meta = FeatureMatrix(
            ...
            cross_asset_features=cross_asset_cols,
        )
```

- [ ] **Step 6: Verify build + run existing tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v -k "feature or builder" --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add src/features/builder.py src/features/schemas.py src/utils/config.py
git commit -m "feat: integrate cross-asset features into FeatureBuilder pipeline"
```

---

### Task 4: Wire Cross-Asset into Training and Prediction

**Files:**
- Modify: `src/models/trainer.py:~85`
- Modify: `src/models/prediction_service.py:~118,~132`

- [ ] **Step 1: Pass `cross_asset=True` in trainer**

In `src/models/trainer.py`, where `build_features()` is called (line ~85), add the parameter:

```python
        df, feature_meta = self.feature_builder.build_features(
            epic=epic,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            multi_timeframe=multi_timeframe,
            include_sentiment=include_sentiment,
            sil_data=sil_data,
            cross_asset=True,  # NEW: enable cross-asset features
        )
```

- [ ] **Step 2: Pass `cross_asset=True` in prediction service**

In `src/models/prediction_service.py`, at both places where `build_features()` or `build_features_from_df()` is called, pass `cross_asset=True`:

The `build_features()` call (line ~118):
```python
        df, feature_meta = self._feature_builder.build_features(
            epic=epic,
            timeframe=timeframe,
            multi_timeframe=has_multi_tf,
            cross_asset=True,  # NEW
        )
```

Note: `build_features_from_df()` doesn't need cross-asset — it's only used for pre-loaded data in offline mode. Cross-asset data must be loaded fresh.

- [ ] **Step 3: Verify prediction still works without cross-asset data**

The `CROSS_ASSET_ENABLED` config defaults to `False`, so this won't change behavior until explicitly enabled. Verify:

```bash
cd backend && .venv/Scripts/python.exe -c "
from src.utils.config import get_settings
print(f'cross_asset_enabled={get_settings().cross_asset_enabled}')
"
```

Expected: `cross_asset_enabled=False`

- [ ] **Step 4: Commit**

```bash
git add src/models/trainer.py src/models/prediction_service.py
git commit -m "feat: wire cross-asset features into training and prediction pipeline"
```

---

## Level 2: Dynamic Correlation Regime Detection

### Task 5: Correlation Regime in Trading Loop

**Files:**
- Modify: `src/trading/paper_loop.py`
- Modify: `src/utils/config.py`
- Modify: `src/api/routers/analytics.py`

- [ ] **Step 1: Add config settings**

In `src/utils/config.py`, add after `cross_asset_enabled`:

```python
    correlation_regime_enabled: bool = Field(default=False, alias="CORRELATION_REGIME_ENABLED")
    correlation_regime_threshold: float = Field(default=0.75, alias="CORRELATION_REGIME_THRESHOLD")
    correlation_regime_size_reduction: float = Field(default=0.50, alias="CORRELATION_REGIME_SIZE_REDUCTION")
```

- [ ] **Step 2: Add regime computation to paper_loop**

In `paper_loop.py` `__init__`, add after `_spread_blocked_epics`:

```python
        self._correlation_regime: str = "normal"  # normal, elevated, panic, decorrelated
        self._correlation_regime_ts: float = 0.0   # last update timestamp
```

Add a new method `_refresh_correlation_regime()`:

```python
    async def _refresh_correlation_regime(self) -> None:
        """Recompute correlation regime every 30 minutes."""
        now = _time.monotonic()
        if now - self._correlation_regime_ts < 1800:  # 30 min
            return
        self._correlation_regime_ts = now

        _settings = get_settings()
        if not _settings.correlation_regime_enabled:
            return

        try:
            from src.features.cross_asset import CrossAssetEngine

            engine = CrossAssetEngine()
            all_dfs = {}
            for epic in self.epics[:10]:  # Top 10 most liquid for speed
                df = self.data_access.get_candles(epic, self._candle_resolution)
                if df is not None and len(df) >= 100:
                    all_dfs[epic] = df

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
        except Exception as e:
            logger.debug(f"Correlation regime update failed: {e}")
```

- [ ] **Step 3: Call regime refresh in iteration loop**

In `_run_iteration()`, after the spread refresh call, add:

```python
        # Refresh correlation regime every 30 minutes
        await self._refresh_correlation_regime()
```

- [ ] **Step 4: Use regime in risk check (position size reduction)**

In `_process_epic()`, after the risk check succeeds (line ~1660), add regime-based size reduction:

```python
        # Correlation regime adjustment: reduce size during panic
        if (
            self._correlation_regime == "panic"
            and get_settings().correlation_regime_enabled
        ):
            reduction = get_settings().correlation_regime_size_reduction
            original_size = risk_result.position_size
            risk_result.position_size *= (1.0 - reduction)
            risk_result.adjustments.append(
                f"Correlation regime PANIC: size reduced by {reduction:.0%} "
                f"({original_size:.4f} -> {risk_result.position_size:.4f})"
            )
            logger.info(
                f"[{epic}] Correlation panic regime: size {original_size:.4f} "
                f"-> {risk_result.position_size:.4f}"
            )
```

- [ ] **Step 5: Expose regime in trading status API**

In the status dict build (around line 2570), add:

```python
            "correlation_regime": self._correlation_regime,
```

- [ ] **Step 6: Add /correlation-regime API endpoint**

In `src/api/routers/analytics.py`, add a new endpoint:

```python
@router.get("/correlation-regime")
async def get_correlation_regime(request: Request):
    """Get current correlation regime from trading loop."""
    loop = getattr(request.app.state, "paper_loop", None)
    if loop is None:
        return {"success": True, "data": {"regime": "unknown", "reason": "trading loop not running"}}

    return {
        "success": True,
        "data": {
            "regime": loop._correlation_regime,
        },
    }
```

- [ ] **Step 7: Commit**

```bash
git add src/trading/paper_loop.py src/utils/config.py src/api/routers/analytics.py
git commit -m "feat: dynamic correlation regime detection with panic size reduction"
```

---

## Level 3: Dynamic CorrelationGuard

### Task 6: Replace Hardcoded CorrelationGuard with Dynamic Matrix

**Files:**
- Modify: `src/risk/correlation_guard.py`
- Create: `tests/test_correlation_guard_dynamic.py`
- Modify: `src/risk/risk_manager.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_correlation_guard_dynamic.py`:

```python
"""Tests for dynamic CorrelationGuard."""

import pytest
import numpy as np

from src.risk.correlation_guard import CorrelationGuard


class TestDynamicCorrelationGuard:
    def test_static_fallback_when_no_matrix(self):
        """Without a dynamic matrix, falls back to hardcoded pairs."""
        multiplier, warnings = CorrelationGuard.check_exposure(
            epic="XAGUSD",
            direction="BUY",
            open_positions=[{"epic": "XAUUSD", "direction": "BUY"}],
        )
        # XAUUSD-XAGUSD has 0.85 reduction hardcoded
        assert multiplier < 0.20

    def test_dynamic_matrix_overrides_static(self):
        """When a correlation matrix is provided, it overrides hardcoded pairs."""
        # Mock a matrix where XAUUSD-XAGUSD correlation is only 0.3
        epics = ["XAGUSD", "XAUUSD"]
        matrix = np.array([[1.0, 0.3], [0.3, 1.0]])

        guard = CorrelationGuard()
        guard.update_matrix(epics, matrix)

        multiplier, warnings = guard.check_exposure_dynamic(
            epic="XAGUSD",
            direction="BUY",
            open_positions=[{"epic": "XAUUSD", "direction": "BUY"}],
        )
        # 0.3 correlation → 0.3 reduction → multiplier = 0.7
        assert 0.65 <= multiplier <= 0.75

    def test_high_dynamic_correlation_reduces_more(self):
        """High dynamic correlation = more size reduction."""
        epics = ["BTCUSD", "ETHUSD"]
        matrix = np.array([[1.0, 0.95], [0.95, 1.0]])

        guard = CorrelationGuard()
        guard.update_matrix(epics, matrix)

        multiplier, _ = guard.check_exposure_dynamic(
            epic="ETHUSD",
            direction="BUY",
            open_positions=[{"epic": "BTCUSD", "direction": "BUY"}],
        )
        # 0.95 correlation → multiplier ≈ 0.05
        assert multiplier < 0.15

    def test_opposite_directions_no_penalty(self):
        """Hedged positions (opposite directions) should not be penalized."""
        epics = ["BTCUSD", "ETHUSD"]
        matrix = np.array([[1.0, 0.90], [0.90, 1.0]])

        guard = CorrelationGuard()
        guard.update_matrix(epics, matrix)

        multiplier, _ = guard.check_exposure_dynamic(
            epic="ETHUSD",
            direction="SELL",  # Opposite to BTC BUY
            open_positions=[{"epic": "BTCUSD", "direction": "BUY"}],
        )
        # Opposite directions = hedge, no penalty
        assert multiplier == 1.0

    def test_multiple_correlated_positions(self):
        """Multiple correlated positions accumulate reduction."""
        epics = ["BTCUSD", "ETHUSD", "SOLUSD"]
        matrix = np.array([
            [1.0, 0.85, 0.80],
            [0.85, 1.0, 0.75],
            [0.80, 0.75, 1.0],
        ])

        guard = CorrelationGuard()
        guard.update_matrix(epics, matrix)

        multiplier, _ = guard.check_exposure_dynamic(
            epic="SOLUSD",
            direction="BUY",
            open_positions=[
                {"epic": "BTCUSD", "direction": "BUY"},
                {"epic": "ETHUSD", "direction": "BUY"},
            ],
        )
        # Both BTC (0.80) and ETH (0.75) are correlated → heavy reduction
        assert multiplier < 0.25
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && .venv/Scripts/python.exe -m pytest tests/test_correlation_guard_dynamic.py -v`
Expected: FAIL — `AttributeError: 'CorrelationGuard' object has no attribute 'update_matrix'`

- [ ] **Step 3: Implement dynamic CorrelationGuard**

Rewrite `src/risk/correlation_guard.py`:

```python
"""
Cross-asset correlation exposure checker.
Uses a dynamic correlation matrix when available, falls back to hardcoded pairs.
Reduces position size when correlated assets have open positions in the same direction.
"""

import numpy as np
from loguru import logger

# Hardcoded fallback pairs (used when no dynamic matrix available)
CORRELATION_PAIRS: list[tuple[str, str, float]] = [
    ("XAUUSD", "BTCUSD", 0.50),
    ("BTCUSD", "US500", 0.30),
    ("XAUUSD", "XAGUSD", 0.85),
    ("US500", "DE40", 0.70),
    ("NVDA", "TSLA", 0.50),
    ("US500", "NVDA", 0.40),
    ("US500", "TSLA", 0.40),
    ("WTIUSD", "XAUUSD", 0.25),
    ("BTCUSD", "NVDA", 0.30),
]

EPIC_ALIASES: dict[str, str] = {
    "GOLD": "XAUUSD",
    "BITCOIN": "BTCUSD",
    "SP500": "US500",
    "SILVER": "XAGUSD",
    "OIL_CRUDE": "WTIUSD",
    "GERMANY40": "DE40",
}


def _normalize_epic(epic: str) -> str:
    return EPIC_ALIASES.get(epic.upper(), epic.upper())


class CorrelationGuard:
    """Checks cross-asset correlation exposure and adjusts position sizes."""

    def __init__(self) -> None:
        self._matrix: np.ndarray | None = None
        self._epic_index: dict[str, int] = {}

    def update_matrix(self, epics: list[str], matrix: np.ndarray) -> None:
        """Update the dynamic correlation matrix.

        Args:
            epics: Ordered list of epic names matching matrix rows/columns
            matrix: NxN correlation matrix (symmetric, diagonal=1.0)
        """
        self._matrix = matrix
        self._epic_index = {epic: i for i, epic in enumerate(epics)}
        logger.debug(
            f"CorrelationGuard matrix updated: {len(epics)} assets"
        )

    def get_dynamic_correlation(self, epic_a: str, epic_b: str) -> float | None:
        """Get the dynamic correlation between two assets.

        Returns None if either asset is not in the matrix.
        """
        if self._matrix is None:
            return None
        a_norm = _normalize_epic(epic_a)
        b_norm = _normalize_epic(epic_b)
        idx_a = self._epic_index.get(a_norm)
        idx_b = self._epic_index.get(b_norm)
        if idx_a is None or idx_b is None:
            return None
        return float(self._matrix[idx_a, idx_b])

    def check_exposure_dynamic(
        self,
        epic: str,
        direction: str,
        open_positions: list[dict],
    ) -> tuple[float, list[str]]:
        """Check exposure using dynamic correlation matrix.

        Falls back to static pairs for assets not in the matrix.

        Args:
            epic: Epic of the new position
            direction: "BUY" or "SELL"
            open_positions: List of open position dicts

        Returns:
            Tuple of (size_multiplier, warnings)
        """
        normalized_epic = _normalize_epic(epic)
        size_multiplier = 1.0
        warnings: list[str] = []

        for pos in open_positions:
            pos_epic = _normalize_epic(pos.get("epic", ""))
            pos_direction = pos.get("direction", "")

            if pos_epic == normalized_epic:
                continue  # Same asset — handled elsewhere
            if pos_direction != direction:
                continue  # Opposite direction = hedge, no penalty

            # Try dynamic correlation first
            corr = self.get_dynamic_correlation(normalized_epic, pos_epic)
            if corr is not None and corr > 0.1:
                reduction = abs(corr)  # Use correlation directly as reduction
                new_mult = 1.0 - reduction
                if new_mult < size_multiplier:
                    size_multiplier = new_mult
                    warnings.append(
                        f"Dynamic correlation: {epic}-{pos_epic} "
                        f"corr={corr:.2f} -> size x{new_mult:.2f}"
                    )
                continue

            # Fallback to static pairs
            for asset_a, asset_b, static_reduction in CORRELATION_PAIRS:
                correlated_epic = None
                if normalized_epic == asset_a and pos_epic == asset_b:
                    correlated_epic = asset_b
                elif normalized_epic == asset_b and pos_epic == asset_a:
                    correlated_epic = asset_a
                if correlated_epic:
                    new_mult = 1.0 - static_reduction
                    if new_mult < size_multiplier:
                        size_multiplier = new_mult
                        warnings.append(
                            f"Static correlation: {epic}-{pos_epic} "
                            f"reduction={static_reduction:.0%}"
                        )
                    break

        if warnings:
            logger.info(
                f"CorrelationGuard {epic} {direction}: "
                f"multiplier={size_multiplier:.2f}"
            )

        return size_multiplier, warnings

    @staticmethod
    def check_exposure(
        epic: str,
        direction: str,
        open_positions: list[dict],
    ) -> tuple[float, list[str]]:
        """Static fallback — uses hardcoded pairs only.

        Kept for backward compatibility. New code should use
        check_exposure_dynamic() on an instance with update_matrix().
        """
        normalized_epic = _normalize_epic(epic)
        size_multiplier = 1.0
        warnings: list[str] = []

        for asset_a, asset_b, reduction in CORRELATION_PAIRS:
            correlated_epic = None
            if normalized_epic == asset_a:
                correlated_epic = asset_b
            elif normalized_epic == asset_b:
                correlated_epic = asset_a
            else:
                continue

            for pos in open_positions:
                pos_epic = _normalize_epic(pos.get("epic", ""))
                pos_direction = pos.get("direction", "")
                if pos_epic == correlated_epic and pos_direction == direction:
                    new_mult = 1.0 - reduction
                    if new_mult < size_multiplier:
                        size_multiplier = new_mult
                        warnings.append(
                            f"Correlated exposure: {epic} {direction} with "
                            f"{correlated_epic} {pos_direction} -> "
                            f"size reduced by {reduction:.0%}"
                        )

        if warnings:
            logger.info(
                f"Correlation guard for {epic} {direction}: "
                f"multiplier={size_multiplier:.2f}, warnings={len(warnings)}"
            )

        return size_multiplier, warnings
```

- [ ] **Step 4: Run tests**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/test_correlation_guard_dynamic.py -v
```

Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/risk/correlation_guard.py tests/test_correlation_guard_dynamic.py
git commit -m "feat: dynamic CorrelationGuard with live correlation matrix"
```

---

### Task 7: Wire Dynamic Matrix Updates into Trading Loop

**Files:**
- Modify: `src/risk/risk_manager.py`
- Modify: `src/trading/paper_loop.py`

- [ ] **Step 1: Add CorrelationGuard instance to RiskManager**

In `src/risk/risk_manager.py` `__init__`, add:

```python
        self.correlation_guard = CorrelationGuard()
```

And update the `check_trade()` correlation section (~line 240) to use the instance:

```python
        # 5. Check correlation exposure (dynamic if matrix available, else static)
        corr_multiplier, corr_warnings = self.correlation_guard.check_exposure_dynamic(
            epic=signal.epic,
            direction=signal.direction.value,
            open_positions=open_positions,
        )
```

- [ ] **Step 2: Update correlation matrix periodically in paper_loop**

In `_refresh_correlation_regime()` (added in Task 5), after computing the regime, also update the guard's matrix:

```python
        # Update CorrelationGuard's dynamic matrix
        if len(all_dfs) >= 5:
            # Compute pairwise correlations from recent returns
            epics_list = sorted(all_dfs.keys())
            n_assets = len(epics_list)
            common_len = min(len(df) for df in all_dfs.values())
            returns = np.array([
                np.diff(np.log(np.maximum(
                    all_dfs[e]["close"].tail(common_len).to_numpy(), 1e-10
                )))
                for e in epics_list
            ])
            corr_matrix = np.corrcoef(returns)
            self.risk_manager.correlation_guard.update_matrix(epics_list, corr_matrix)
```

- [ ] **Step 3: Verify existing tests still pass**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v -k "risk or correlation" --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add src/risk/risk_manager.py src/trading/paper_loop.py
git commit -m "feat: wire dynamic correlation matrix into risk manager and trading loop"
```

---

### Task 8: Activation and Validation

**Files:**
- Modify: `backend/.env` (or document)

- [ ] **Step 1: Run full test suite**

```bash
cd backend && .venv/Scripts/python.exe -m pytest tests/ -v --tb=short
```

All tests must pass.

- [ ] **Step 2: Run ruff + black**

```bash
cd backend && .venv/Scripts/python.exe -m ruff check src/ && .venv/Scripts/python.exe -m black src/ --check
```

- [ ] **Step 3: Document activation flags**

The system is designed to be enabled incrementally via `.env`:

```bash
# Level 1: Cross-asset features for ML (requires retrain)
CROSS_ASSET_ENABLED=true

# Level 2: Correlation regime detection (real-time)
CORRELATION_REGIME_ENABLED=true
CORRELATION_REGIME_THRESHOLD=0.75      # Mean corr above this = panic
CORRELATION_REGIME_SIZE_REDUCTION=0.50  # Reduce size by 50% in panic

# Level 3: Dynamic CorrelationGuard (auto — uses matrix when available)
# No flag needed — automatically uses dynamic matrix when regime is enabled
```

**Activation order:**
1. Enable Level 3 first (no retrain needed, just smarter sizing) — `CORRELATION_REGIME_ENABLED=true`
2. Enable Level 1 (`CROSS_ASSET_ENABLED=true`) + retrain all models: `curl -X POST http://localhost:8000/api/models/retrain-all`
3. Monitor model performance (F1 scores) in training dashboard — cross-asset features should improve F1 by 2-5%

- [ ] **Step 4: Commit documentation + final push**

```bash
git add docs/superpowers/plans/2026-03-30-correlation-intelligence.md
git commit -m "docs: correlation intelligence implementation plan"
git push origin master
```
