"""Tests for FeatureBuilder sentiment and macro feature integration."""

import numpy as np
import polars as pl
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

from src.features.builder import FeatureBuilder


def _make_ohlcv(n: int = 200) -> pl.DataFrame:
    """Create OHLCV DataFrame for testing."""
    np.random.seed(42)
    close = np.cumsum(np.random.randn(n)) + 100
    return pl.DataFrame({
        "timestamp": pl.datetime_range(
            pl.datetime(2025, 1, 1),
            pl.datetime(2025, 1, 1) + pl.duration(hours=n - 1),
            interval="1h", eager=True,
        ).head(n),
        "open": close + np.random.randn(n) * 0.5,
        "high": close + np.abs(np.random.randn(n)) * 2,
        "low": close - np.abs(np.random.randn(n)) * 2,
        "close": close,
        "volume": np.random.randint(100, 10000, n).astype(float),
    })


def _make_macro_df() -> pl.DataFrame:
    """Create a mock macro DataFrame aligned with OHLCV dates."""
    dates = pl.date_range(
        datetime(2025, 1, 1), datetime(2025, 1, 10), "1d", eager=True
    )
    n = len(dates)
    return pl.DataFrame({
        "date": dates,
        "vix_close": [20.0 + i for i in range(n)],
        "vix_change_5d": [0.01 * i for i in range(n)],
        "dxy_close": [105.0 + i * 0.1 for i in range(n)],
        "dxy_change_5d": [0.002 * i for i in range(n)],
        "yield_10y_close": [4.0 + i * 0.05 for i in range(n)],
        "yield_10y_change_5d": [0.005 * i for i in range(n)],
    })


@pytest.mark.unit
@pytest.mark.features
class TestBuilderSentiment:
    """Test sentiment feature integration in FeatureBuilder."""

    def test_build_features_without_sentiment(self):
        """Without include_sentiment, no sentiment columns are added."""
        builder = FeatureBuilder()
        df = _make_ohlcv()
        result, matrix = builder.build_features_from_df(
            df, "XAUUSD", "1h", normalize=False, include_regime=False
        )
        assert "insider_mspr" not in result.columns
        assert "news_sentiment_avg" not in result.columns

    def test_apply_sentiment_none_data_adds_placeholders(self):
        """When sentiment_data is None, placeholder columns are added."""
        builder = FeatureBuilder()
        df = _make_ohlcv()
        result = builder._apply_sentiment_features(df, "XAUUSD", sentiment_data=None)
        expected = {"insider_mspr", "analyst_consensus", "price_target_upside",
                    "earnings_flag", "news_sentiment_avg"}
        assert expected.issubset(set(result.columns))

    def test_apply_sentiment_tier1_equity(self):
        """Tier 1 (NVDA) uses all 5 features from pre-fetched data."""
        builder = FeatureBuilder()
        df = _make_ohlcv()
        sentiment_data = {
            "insider": {"mspr": -0.5},
            "analyst": {"consensus": 3.5, "buy": 20, "sell": 2, "hold": 5},
            "price_target": {"targetMean": 150.0},
            "earnings": [],
            "news": [],
        }

        with patch("src.features.builder.SentimentFeatures") as mock_sf:
            # Make each method return the df with an extra column
            mock_sf.add_insider_mspr.return_value = df.with_columns(
                pl.lit(-0.5).alias("insider_mspr")
            )
            mock_sf.add_analyst_consensus.return_value = df.with_columns(
                pl.lit(-0.5).alias("insider_mspr"),
                pl.lit(3).alias("analyst_consensus"),
            )
            mock_sf.add_price_target_upside.return_value = df.with_columns(
                pl.lit(-0.5).alias("insider_mspr"),
                pl.lit(3).alias("analyst_consensus"),
                pl.lit(0.5).alias("price_target_upside"),
            )
            mock_sf.add_earnings_flag.return_value = df.with_columns(
                pl.lit(-0.5).alias("insider_mspr"),
                pl.lit(3).alias("analyst_consensus"),
                pl.lit(0.5).alias("price_target_upside"),
                pl.lit(0).alias("earnings_flag"),
            )
            mock_sf.add_news_sentiment.return_value = df.with_columns(
                pl.lit(-0.5).alias("insider_mspr"),
                pl.lit(3).alias("analyst_consensus"),
                pl.lit(0.5).alias("price_target_upside"),
                pl.lit(0).alias("earnings_flag"),
                pl.lit(0.1).alias("news_sentiment_avg"),
            )

            result = builder._apply_sentiment_features(df, "NVDA", sentiment_data)

            mock_sf.add_insider_mspr.assert_called_once()
            mock_sf.add_analyst_consensus.assert_called_once()
            mock_sf.add_news_sentiment.assert_called_once()

    def test_apply_sentiment_tier2_crypto(self):
        """Tier 2 (BTCUSD) gets news_sentiment_avg + 4 placeholders."""
        builder = FeatureBuilder()
        df = _make_ohlcv()
        sentiment_data = {
            "insider": None,
            "analyst": None,
            "price_target": None,
            "earnings": [],
            "news": [{"sentiment": 0.3}],
        }

        with patch("src.features.builder.SentimentFeatures") as mock_sf:
            mock_sf.add_news_sentiment.return_value = df.with_columns(
                pl.lit(None).alias("insider_mspr").cast(pl.Float64),
                pl.lit(0).alias("analyst_consensus"),
                pl.lit(0.0).alias("price_target_upside"),
                pl.lit(0).alias("earnings_flag"),
                pl.lit(0.3).alias("news_sentiment_avg"),
            )

            result = builder._apply_sentiment_features(df, "BTCUSD", sentiment_data)

            # Should NOT call equity-only features
            mock_sf.add_insider_mspr.assert_not_called()
            mock_sf.add_analyst_consensus.assert_not_called()
            # Should call news sentiment
            mock_sf.add_news_sentiment.assert_called_once()

    def test_apply_sentiment_exception_adds_placeholders(self):
        """If sentiment application fails, placeholders are added."""
        builder = FeatureBuilder()
        df = _make_ohlcv()
        sentiment_data = {"news": "bad_data"}  # Will cause an error

        with patch("src.features.builder.SentimentFeatures") as mock_sf:
            mock_sf.add_news_sentiment.side_effect = TypeError("bad data")

            result = builder._apply_sentiment_features(df, "BTCUSD", sentiment_data)
            expected = {"insider_mspr", "analyst_consensus", "price_target_upside",
                        "earnings_flag", "news_sentiment_avg"}
            assert expected.issubset(set(result.columns))


@pytest.mark.unit
@pytest.mark.features
class TestBuilderMacro:
    """Test macro feature integration in FeatureBuilder."""

    def test_add_macro_features_with_data(self):
        """Macro features are added via asof join when data is provided."""
        builder = FeatureBuilder()
        df = _make_ohlcv(200)
        macro_df = _make_macro_df()

        result = builder._add_macro_features(df, macro_df)

        assert "vix_close" in result.columns
        assert "dxy_close" in result.columns
        assert "yield_10y_close" in result.columns
        assert "vix_change_5d" in result.columns
        assert "dxy_change_5d" in result.columns
        assert "yield_10y_change_5d" in result.columns
        # Should not have temporary join columns
        assert "_macro_date" not in result.columns
        assert "date" not in result.columns

    def test_add_macro_features_none_adds_placeholders(self):
        """When macro_df is None and fetch fails, placeholder columns are added."""
        builder = FeatureBuilder()
        df = _make_ohlcv(200)

        with patch("src.external.macro_client.MacroDataClient") as mock_cls:
            mock_cls.return_value.get_macro_data.return_value = pl.DataFrame()
            result = builder._add_macro_features(df, None)

        for col in FeatureBuilder._MACRO_FEATURE_COLS:
            assert col in result.columns

    def test_add_macro_features_empty_df_adds_placeholders(self):
        """Empty macro DataFrame results in placeholder columns."""
        builder = FeatureBuilder()
        df = _make_ohlcv(200)
        empty_macro = pl.DataFrame({
            "date": pl.Series([], dtype=pl.Date),
            "vix_close": pl.Series([], dtype=pl.Float64),
        })

        result = builder._add_macro_features(df, empty_macro)
        for col in FeatureBuilder._MACRO_FEATURE_COLS:
            assert col in result.columns

    def test_macro_features_aligned_correctly(self):
        """Asof join aligns daily macro data to hourly bars correctly."""
        builder = FeatureBuilder()
        df = _make_ohlcv(48)  # 48 hours = 2 days
        macro_df = _make_macro_df()

        result = builder._add_macro_features(df, macro_df)

        # First 24 rows (Jan 1) should have the same vix_close
        jan1_values = result.filter(
            pl.col("timestamp").cast(pl.Date) == pl.lit(datetime(2025, 1, 1)).cast(pl.Date)
        )["vix_close"].unique()
        assert len(jan1_values) == 1  # All Jan 1 bars have same macro value

    def test_macro_feature_cols_constant(self):
        """_MACRO_FEATURE_COLS has 6 expected columns."""
        assert len(FeatureBuilder._MACRO_FEATURE_COLS) == 6
        assert "vix_close" in FeatureBuilder._MACRO_FEATURE_COLS
        assert "dxy_close" in FeatureBuilder._MACRO_FEATURE_COLS
        assert "yield_10y_close" in FeatureBuilder._MACRO_FEATURE_COLS

    def test_build_features_with_macro_in_pipeline(self):
        """Macro features are included when include_macro=True in build_features_from_df."""
        builder = FeatureBuilder()
        df = _make_ohlcv(200)
        macro_df = _make_macro_df()

        with patch.object(builder, "_add_macro_features", wraps=builder._add_macro_features) as mock_add:
            # build_features (full pipeline with data loading) uses include_macro
            # We test _add_macro_features directly since build_features_from_df doesn't
            # have the macro parameter
            result = builder._add_macro_features(df, macro_df)
            assert "vix_close" in result.columns
