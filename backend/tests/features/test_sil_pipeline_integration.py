"""Test that SIL data flows through the prediction pipeline."""
import numpy as np
import polars as pl
import pytest
from src.external.sil_schemas import (
    SILData, FearGreedData, FREDData, AlphaVantageData, COTData, SocialSentimentData,
)
from src.features.builder import FeatureBuilder
from src.features.sil_features import SIL_FEATURE_COLS


def _make_sil_data() -> SILData:
    return SILData(
        fear_greed=FearGreedData(normalized=0.65, gold_bias=0.3, value=65),
        fred=FREDData(real_yield_10y=-0.5, breakeven_inflation=2.3),
        alpha_vantage=AlphaVantageData(average_sentiment_score=0.4, bullish_ratio=0.6),
        cot=COTData(net_position_normalized=0.25, z_score_4w=1.2, is_institutional_bullish=True),
        social=SocialSentimentData(combined_bullish_ratio=0.55),
    )


def _make_ohlcv_df(n: int = 100) -> pl.DataFrame:
    np.random.seed(42)
    close = 100.0 + np.cumsum(np.random.randn(n) * 0.5)
    start = pl.datetime(2026, 1, 1)
    end = start + pl.duration(hours=n - 1)
    timestamps = pl.datetime_range(start, end, interval="1h", eager=True).head(n)
    return pl.DataFrame({
        "timestamp": timestamps,
        "open": close - np.random.rand(n) * 0.3,
        "high": close + np.random.rand(n) * 0.5,
        "low": close - np.random.rand(n) * 0.5,
        "close": close,
        "volume": np.random.randint(1000, 10000, n).astype(float),
    })


class TestSILPipelineIntegration:
    def test_build_features_from_df_with_sil_data(self):
        builder = FeatureBuilder()
        df = _make_ohlcv_df()
        sil = _make_sil_data()
        result_df, meta = builder.build_features_from_df(
            df, "XAUUSD", "1h", normalize=False, sil_data=sil,
        )
        for col in SIL_FEATURE_COLS:
            assert col in result_df.columns, f"Missing SIL column: {col}"
        sil_values = result_df.select(SIL_FEATURE_COLS).to_numpy()
        non_zero = (sil_values != 0.0).sum()
        assert non_zero > 0, "All SIL features are zero"

    def test_build_features_from_df_without_sil_defaults_to_zero(self):
        builder = FeatureBuilder()
        df = _make_ohlcv_df()
        result_df, meta = builder.build_features_from_df(
            df, "XAUUSD", "1h", normalize=False,
        )
        for col in SIL_FEATURE_COLS:
            assert col in result_df.columns
        sil_values = result_df.select(SIL_FEATURE_COLS).to_numpy()
        assert (sil_values == 0.0).all()

    def test_sil_composite_score_populated(self):
        builder = FeatureBuilder()
        df = _make_ohlcv_df()
        sil = _make_sil_data()
        result_df, _ = builder.build_features_from_df(
            df, "XAUUSD", "1h", normalize=False, sil_data=sil,
        )
        composite = result_df["sil_composite_score"].to_list()[-1]
        assert composite > 0.0, f"Composite should be >0 with bullish data, got {composite}"
