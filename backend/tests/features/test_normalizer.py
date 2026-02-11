"""Tests for feature normalizer module."""

import numpy as np
import polars as pl
import pytest

from src.features.normalizer import FeatureNormalizer


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """DataFrame with features to normalize."""
    np.random.seed(42)
    n = 500

    return pl.DataFrame({
        "close": 100.0 + np.random.normal(0, 10, n).cumsum(),
        "rsi_14": np.random.uniform(20, 80, n),
        "volume": np.random.randint(1000, 50000, n).astype(np.int64),
        "macd": np.random.normal(0, 5, n),
    })


class TestRollingZscore:
    def test_zscore_creates_columns(self, sample_df: pl.DataFrame):
        df = FeatureNormalizer.rolling_zscore(sample_df, ["rsi_14", "macd"], window=50)
        assert "rsi_14_zscore" in df.columns
        assert "macd_zscore" in df.columns

    def test_zscore_approximately_zero_mean(self, sample_df: pl.DataFrame):
        df = FeatureNormalizer.rolling_zscore(sample_df, ["rsi_14"], window=50)
        # After warmup, z-score should be roughly zero-mean
        zscore = df["rsi_14_zscore"].tail(200).drop_nulls()
        assert abs(zscore.mean()) < 1.0  # Loose check

    def test_zscore_skips_missing_columns(self, sample_df: pl.DataFrame):
        # Should not raise for missing column
        df = FeatureNormalizer.rolling_zscore(sample_df, ["nonexistent"], window=50)
        assert "nonexistent_zscore" not in df.columns

    def test_zscore_handles_nan(self):
        df = pl.DataFrame({"x": [1.0, 2.0, None, 4.0, 5.0] * 20})
        result = FeatureNormalizer.rolling_zscore(df, ["x"], window=10)
        assert "x_zscore" in result.columns


class TestLogTransform:
    def test_log_creates_columns(self, sample_df: pl.DataFrame):
        df = FeatureNormalizer.log_transform(sample_df, ["volume"])
        assert "volume_log" in df.columns

    def test_log_positive_values(self, sample_df: pl.DataFrame):
        df = FeatureNormalizer.log_transform(sample_df, ["volume"])
        assert (df["volume_log"] >= 0).all()

    def test_log_monotonic(self):
        df = pl.DataFrame({"x": [1.0, 10.0, 100.0, 1000.0]})
        result = FeatureNormalizer.log_transform(df, ["x"])
        log_vals = result["x_log"].to_list()
        assert all(a < b for a, b in zip(log_vals, log_vals[1:]))


class TestClipOutliers:
    def test_clip_reduces_range(self):
        # Create data with extreme outliers
        np.random.seed(42)
        data = np.random.normal(0, 1, 200)
        data[50] = 100.0  # Extreme outlier
        data[150] = -100.0

        df = pl.DataFrame({"x": data})
        result = FeatureNormalizer.clip_outliers(df, ["x"], n_sigma=3.0, window=50)
        assert result["x"].max() < 100.0
        assert result["x"].min() > -100.0


class TestNormalizeFeatures:
    def test_full_pipeline(self, sample_df: pl.DataFrame):
        df = FeatureNormalizer.normalize_features(
            sample_df,
            feature_columns=["rsi_14", "macd", "volume"],
            window=50,
            log_columns=["volume"],
        )
        # Should have z-score columns
        assert "rsi_14_zscore" in df.columns
        assert "macd_zscore" in df.columns
        # volume_log should be created, then volume_log_zscore
        assert "volume_log" in df.columns
