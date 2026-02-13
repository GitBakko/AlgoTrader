"""
B6: Verification that MACD and Volume features are present in the feature pipeline.
"""

import numpy as np
import polars as pl
import pytest

from src.features.builder import FeatureBuilder
from src.features.technical import TechnicalIndicators


@pytest.mark.unit
@pytest.mark.features
class TestFeatureCompleteness:
    """Verify that key features exist in the pipeline output."""

    def _make_ohlcv(self, n: int = 100) -> pl.DataFrame:
        np.random.seed(42)
        close = np.cumsum(np.random.randn(n)) + 100
        return pl.DataFrame({
            "timestamp": pl.datetime_range(
                pl.datetime(2025, 1, 1), pl.datetime(2025, 1, 1) + pl.duration(hours=n - 1),
                interval="1h", eager=True,
            ).head(n),
            "open": close + np.random.randn(n) * 0.5,
            "high": close + np.abs(np.random.randn(n)) * 2,
            "low": close - np.abs(np.random.randn(n)) * 2,
            "close": close,
            "volume": np.random.randint(100, 10000, n).astype(float),
        })

    def test_macd_histogram_in_indicators(self):
        """macd_histogram is computed by TechnicalIndicators.add_macd."""
        df = self._make_ohlcv()
        df = TechnicalIndicators.add_macd(df)
        assert "macd_histogram" in df.columns
        assert df["macd_histogram"].null_count() < len(df)

    def test_volume_sma_ratio_in_indicators(self):
        """volume_sma_ratio is computed by TechnicalIndicators.add_volume_sma_ratio."""
        df = self._make_ohlcv()
        df = TechnicalIndicators.add_volume_sma_ratio(df)
        assert "volume_sma_ratio" in df.columns
        assert df["volume_sma_ratio"].null_count() < len(df)

    def test_macd_and_volume_in_add_all(self):
        """Both features present when using add_all_indicators."""
        df = self._make_ohlcv(200)
        df = TechnicalIndicators.add_all_indicators(df, include_volume=True)
        assert "macd_histogram" in df.columns
        assert "volume_sma_ratio" in df.columns

    def test_market_structure_in_builder(self):
        """Market structure features are present after FeatureBuilder."""
        df = self._make_ohlcv(200)
        builder = FeatureBuilder()
        result, matrix = builder.build_features_from_df(
            df, "XAUUSD", "1h", normalize=False, include_regime=False,
        )
        assert "bos_signal" in result.columns
        assert "choch_signal" in result.columns
        assert "structure_trend" in result.columns
