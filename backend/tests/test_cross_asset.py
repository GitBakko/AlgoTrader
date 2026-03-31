"""Tests for cross-asset feature computation."""

from datetime import datetime, timedelta

import numpy as np
import polars as pl

from src.features.cross_asset import CrossAssetEngine


def _make_ohlcv(n: int, base_price: float = 100.0, seed: int = 42) -> pl.DataFrame:
    """Generate synthetic OHLCV data."""
    rng = np.random.default_rng(seed)
    prices = base_price + np.cumsum(rng.normal(0, 0.5, n))
    timestamps = [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": prices,
            "high": prices + rng.uniform(0, 1, n),
            "low": prices - rng.uniform(0, 1, n),
            "close": prices + rng.normal(0, 0.2, n),
            "volume": rng.integers(100, 10000, n),
        }
    )


class TestCrossAssetEngine:
    def test_compute_rolling_correlation(self):
        n = 200
        rng = np.random.default_rng(42)
        x = np.cumsum(rng.normal(0, 1, n))
        y = 0.8 * x + np.cumsum(rng.normal(0, 0.5, n))
        df_main = pl.DataFrame(
            {
                "timestamp": [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(n)],
                "close": x.tolist(),
            }
        )
        df_related = pl.DataFrame(
            {
                "timestamp": [datetime(2026, 1, 1) + timedelta(hours=i) for i in range(n)],
                "close": y.tolist(),
            }
        )
        engine = CrossAssetEngine()
        result = engine.compute_rolling_correlation(df_main, df_related, window=50)
        assert "rolling_corr_50" in result.columns
        last_corr = result["rolling_corr_50"][-1]
        assert last_corr > 0.5, f"Expected high correlation, got {last_corr}"

    def test_compute_lead_lag_returns(self):
        n = 100
        df_related = _make_ohlcv(n, seed=42)
        engine = CrossAssetEngine()
        result = engine.compute_lead_lag_returns(df_related, lags=[1, 3, 6])
        assert "ret_lag_1" in result.columns
        assert "ret_lag_3" in result.columns
        assert "ret_lag_6" in result.columns
        assert len(result) == n
        assert result["ret_lag_6"][0] is None

    def test_compute_sector_momentum(self):
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
        n = 200
        main_df = _make_ohlcv(n, base_price=3000, seed=10)
        related_dfs = {
            "BTCUSD": _make_ohlcv(n, base_price=60000, seed=20),
            "US500": _make_ohlcv(n, base_price=5000, seed=30),
        }
        engine = CrossAssetEngine()
        result = engine.build_cross_asset_features(
            main_df=main_df, epic="XAUUSD", related_dfs=related_dfs
        )
        assert len(result) == n
        cross_cols = [c for c in result.columns if c.startswith(("corr_", "lead_", "sector_"))]
        assert len(cross_cols) > 0
        assert len(cross_cols) >= 8

    def test_empty_related_dfs(self):
        main_df = _make_ohlcv(100, seed=10)
        engine = CrossAssetEngine()
        result = engine.build_cross_asset_features(main_df=main_df, epic="XAUUSD", related_dfs={})
        assert result.columns == main_df.columns

    def test_mismatched_lengths(self):
        main_df = _make_ohlcv(200, seed=10)
        short_df = _make_ohlcv(100, seed=20)
        engine = CrossAssetEngine()
        result = engine.build_cross_asset_features(
            main_df=main_df, epic="XAUUSD", related_dfs={"BTCUSD": short_df}
        )
        assert len(result) == 200


class TestCorrelationRegime:
    def test_compute_correlation_regime(self):
        n = 200
        rng = np.random.default_rng(42)
        base = np.cumsum(rng.normal(0, 1, n))
        all_dfs = {
            f"ASSET_{i}": pl.DataFrame(
                {
                    "timestamp": [datetime(2026, 1, 1) + timedelta(hours=j) for j in range(n)],
                    "close": (base + rng.normal(0, 0.3, n)).tolist(),
                }
            )
            for i in range(5)
        }
        engine = CrossAssetEngine()
        regime = engine.compute_correlation_regime(all_dfs, window=50)
        assert "mean_correlation" in regime.columns
        assert "correlation_regime" in regime.columns
        last_regime = regime["correlation_regime"][-1]
        assert last_regime in ("panic", "elevated", "normal", "decorrelated")
