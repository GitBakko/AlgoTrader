"""Tests for BacktestSignalGenerator."""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import numpy as np
import polars as pl
import pytest

from src.backtest.signal_generator import BacktestSignalGenerator
from src.features.builder import FeatureBuilder
from src.models.calibration import ConfidenceCalibrator
from src.models.schemas import SignalClass


def _make_ohlc(n_bars: int = 500) -> pl.DataFrame:
    """Create synthetic OHLC data."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
    timestamps = [base + timedelta(hours=i) for i in range(n_bars)]
    np.random.seed(42)
    prices = 2000.0 + np.cumsum(np.random.randn(n_bars) * 5.0)

    return pl.DataFrame({
        "timestamp": timestamps,
        "open": prices.tolist(),
        "high": (prices + np.abs(np.random.randn(n_bars) * 3)).tolist(),
        "low": (prices - np.abs(np.random.randn(n_bars) * 3)).tolist(),
        "close": (prices + np.random.randn(n_bars) * 1.0).tolist(),
        "volume": np.random.randint(100, 10000, n_bars).tolist(),
    })


def _make_mock_model(n_classes: int = 3):
    """Create a mock XGBoost model that returns random probabilities."""
    model = MagicMock()
    model.model_type = "xgboost"

    def mock_predict_proba(X):
        np.random.seed(123)
        proba = np.random.dirichlet([1, 1, 1], size=len(X))
        return proba

    model.predict_proba = mock_predict_proba
    return model


class TestBacktestSignalGenerator:
    def test_generate_signals_basic(self):
        """Signals generated with correct shape and columns."""
        ohlc = _make_ohlc(500)
        model = _make_mock_model()
        feature_builder = FeatureBuilder()

        # Build features to get feature names
        df_features, meta = feature_builder.build_features_from_df(
            ohlc, "XAUUSD", "1h", normalize=True,
        )
        feature_names = meta.feature_names

        gen = BacktestSignalGenerator()
        signals_df = gen.generate_signals(
            model=model,
            feature_builder=feature_builder,
            ohlc_df=ohlc,
            epic="XAUUSD",
            timeframe="1h",
            feature_names=feature_names,
            min_confidence=0.40,
        )

        assert not signals_df.is_empty()
        assert "timestamp" in signals_df.columns
        assert "signal" in signals_df.columns
        assert "confidence" in signals_df.columns
        assert "atr" in signals_df.columns

        # All signals should be valid classes
        unique_signals = signals_df["signal"].unique().to_list()
        for s in unique_signals:
            assert s in [SignalClass.SELL, SignalClass.HOLD, SignalClass.BUY]

        # Confidence should be in [0, 1]
        assert signals_df["confidence"].min() >= 0.0
        assert signals_df["confidence"].max() <= 1.0

    def test_generate_signals_confidence_threshold(self):
        """Low-confidence predictions are converted to HOLD."""
        ohlc = _make_ohlc(500)
        feature_builder = FeatureBuilder()
        df_features, meta = feature_builder.build_features_from_df(
            ohlc, "XAUUSD", "1h", normalize=True,
        )

        # Create model that returns low confidence (uniform distribution → ~33%)
        model = MagicMock()
        model.predict_proba = lambda X: np.full((len(X), 3), 1 / 3)

        gen = BacktestSignalGenerator()
        signals_df = gen.generate_signals(
            model=model,
            feature_builder=feature_builder,
            ohlc_df=ohlc,
            epic="XAUUSD",
            timeframe="1h",
            feature_names=meta.feature_names,
            min_confidence=0.50,  # Higher than 33%
        )

        # All signals should be HOLD since confidence < threshold
        assert not signals_df.is_empty()
        assert (signals_df["signal"] == SignalClass.HOLD).all()

    def test_generate_signals_with_calibrator(self):
        """Calibrator transforms probabilities before thresholding."""
        ohlc = _make_ohlc(300)
        model = _make_mock_model()
        feature_builder = FeatureBuilder()
        df_features, meta = feature_builder.build_features_from_df(
            ohlc, "XAUUSD", "1h", normalize=True,
        )

        # Mock calibrator that boosts confidence
        calibrator = MagicMock(spec=ConfidenceCalibrator)
        calibrator.transform = lambda proba: np.column_stack([
            np.full(len(proba), 0.1),
            np.full(len(proba), 0.1),
            np.full(len(proba), 0.8),  # Always high BUY confidence
        ])

        gen = BacktestSignalGenerator()
        signals_df = gen.generate_signals(
            model=model,
            feature_builder=feature_builder,
            ohlc_df=ohlc,
            epic="XAUUSD",
            timeframe="1h",
            feature_names=meta.feature_names,
            calibrator=calibrator,
            min_confidence=0.50,
        )

        # All signals should be BUY (confidence 0.8 > 0.5 threshold)
        assert not signals_df.is_empty()
        buy_count = signals_df.filter(pl.col("signal") == SignalClass.BUY).height
        assert buy_count == len(signals_df)

    def test_generate_signals_empty_df(self):
        """Empty DataFrame returns empty signals."""
        empty_df = pl.DataFrame(schema={
            "timestamp": pl.Datetime,
            "open": pl.Float64,
            "high": pl.Float64,
            "low": pl.Float64,
            "close": pl.Float64,
            "volume": pl.Float64,
        })
        model = _make_mock_model()
        feature_builder = FeatureBuilder()

        gen = BacktestSignalGenerator()
        signals_df = gen.generate_signals(
            model=model,
            feature_builder=feature_builder,
            ohlc_df=empty_df,
            epic="XAUUSD",
            timeframe="1h",
            feature_names=["rsi_14_zscore", "macd_zscore"],
        )

        assert signals_df.is_empty()

    def test_generate_signals_feature_mismatch(self):
        """Returns empty when too few features are available."""
        ohlc = _make_ohlc(200)
        model = _make_mock_model()
        feature_builder = FeatureBuilder()

        gen = BacktestSignalGenerator()
        # Request features that don't exist
        signals_df = gen.generate_signals(
            model=model,
            feature_builder=feature_builder,
            ohlc_df=ohlc,
            epic="XAUUSD",
            timeframe="1h",
            feature_names=["nonexistent_feature_" + str(i) for i in range(100)],
        )

        # Should return empty because <50% of features available
        assert signals_df.is_empty()

    def test_generate_signals_missing_features_filled_with_zero(self):
        """Missing features are filled with zeros when majority are available."""
        ohlc = _make_ohlc(300)
        model = _make_mock_model()
        feature_builder = FeatureBuilder()
        df_features, meta = feature_builder.build_features_from_df(
            ohlc, "XAUUSD", "1h", normalize=True,
        )

        # Add one non-existent feature to the list
        feature_names = meta.feature_names + ["extra_nonexistent_feature"]

        gen = BacktestSignalGenerator()
        signals_df = gen.generate_signals(
            model=model,
            feature_builder=feature_builder,
            ohlc_df=ohlc,
            epic="XAUUSD",
            timeframe="1h",
            feature_names=feature_names,
            min_confidence=0.0,  # Accept all
        )

        # Should succeed (>50% features available)
        assert not signals_df.is_empty()
