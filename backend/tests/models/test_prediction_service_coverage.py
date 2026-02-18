"""
Tests for PredictionService covering untested paths:
- predict() with multi-TF features but no data_access
- predict() with < 50% feature match
- predict() with > 50% NaN values
- predict() with calibration applied
- predict() successful path returning PredictionResult
- get_market_data() when no data available
- get_market_data() with ADX present
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import numpy as np
import polars as pl
import pytest

from src.features.schemas import FeatureMatrix
from src.models.prediction_service import PredictionService
from src.models.schemas import ModelMetadata, PredictionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_metadata(
    feature_names: list[str] | None = None,
    model_type: str = "xgboost",
) -> ModelMetadata:
    """Create a minimal ModelMetadata for tests."""
    return ModelMetadata(
        model_id="test-model-001",
        model_type=model_type,
        epic="XAUUSD",
        timeframe="1h",
        version=1,
        feature_names=feature_names or ["feat_a", "feat_b", "feat_c", "feat_d"],
        num_features=len(feature_names) if feature_names else 4,
        created_at=datetime.now(timezone.utc),
    )


def _make_candles_df(n: int = 100) -> pl.DataFrame:
    """Create a minimal OHLC candle DataFrame with n rows."""
    return pl.DataFrame({
        "timestamp": [datetime(2026, 1, 1, i % 24) for i in range(n)],
        "open": [2000.0 + i for i in range(n)],
        "high": [2005.0 + i for i in range(n)],
        "low": [1995.0 + i for i in range(n)],
        "close": [2002.0 + i for i in range(n)],
        "volume": [1000 + i for i in range(n)],
    })


def _make_features_df(
    feature_names: list[str],
    n_rows: int = 1,
    nan_fraction: float = 0.0,
) -> pl.DataFrame:
    """Create a DataFrame with the given feature columns."""
    data: dict[str, list[float]] = {}
    for i, name in enumerate(feature_names):
        vals = [float(i + 1 + r) for r in range(n_rows)]
        if nan_fraction > 0:
            # Set a fraction of the *last row* values to NaN
            nan_count = int(len(feature_names) * nan_fraction)
            if i < nan_count:
                vals[-1] = float("nan")
        data[name] = vals
    return pl.DataFrame(data)


def _make_feature_matrix(
    feature_names: list[str],
    num_rows: int = 1,
) -> FeatureMatrix:
    return FeatureMatrix(
        epic="XAUUSD",
        timeframe="1h",
        feature_names=feature_names,
        num_rows=num_rows,
        num_features=len(feature_names),
    )


def _make_service(
    meta: ModelMetadata | None = None,
    data_access=None,
) -> PredictionService:
    """Create PredictionService with mocked dependencies."""
    feature_builder = MagicMock()
    versioning = MagicMock()
    da = data_access or MagicMock()
    svc = PredictionService(feature_builder, versioning, da)

    if meta is not None:
        model_mock = MagicMock()
        # Default: predict_proba returns 3-class probabilities
        model_mock.predict_proba.return_value = np.array([[0.1, 0.3, 0.6]])
        svc._loaded_models["XAUUSD"] = (model_mock, meta)

    return svc


# ===========================================================================
# predict() tests
# ===========================================================================

class TestPredictMultiTfFallback:
    """When model has multi-TF features but data_access is used in single-TF fallback."""

    def test_multi_tf_features_uses_build_features(self):
        """Model trained with 4h_ prefixed features -> calls build_features (multi-TF path)."""
        feature_names = ["feat_a", "feat_b", "4h_rsi_14", "1d_atr_14"]
        meta = _make_metadata(feature_names=feature_names)
        svc = _make_service(meta=meta)

        df_features = _make_features_df(feature_names, n_rows=5)
        matrix = _make_feature_matrix(feature_names, num_rows=5)

        svc.feature_builder.build_features.return_value = (df_features, matrix)

        result = svc.predict("XAUUSD")
        assert result is not None
        assert isinstance(result, PredictionResult)
        svc.feature_builder.build_features.assert_called_once()

    def test_single_tf_path_with_data_access(self):
        """Model WITHOUT multi-TF features -> uses single-TF path via get_candles."""
        feature_names = ["feat_a", "feat_b", "feat_c"]
        meta = _make_metadata(feature_names=feature_names)

        da = MagicMock()
        candles = _make_candles_df(100)
        da.get_candles.return_value = candles

        svc = _make_service(meta=meta, data_access=da)

        df_features = _make_features_df(feature_names, n_rows=5)
        matrix = _make_feature_matrix(feature_names, num_rows=5)
        svc.feature_builder.build_features_from_df.return_value = (df_features, matrix)

        result = svc.predict("XAUUSD")
        assert result is not None
        assert isinstance(result, PredictionResult)
        da.get_candles.assert_called_once_with("XAUUSD", "1h", limit=300)
        svc.feature_builder.build_features_from_df.assert_called_once()


class TestPredictFeatureMismatch:
    """predict() returns None when < 50% features match."""

    def test_less_than_50_percent_features_returns_none(self):
        """Model expects 10 features, only 4 available -> returns None."""
        model_features = [f"feat_{i}" for i in range(10)]
        meta = _make_metadata(feature_names=model_features)

        da = MagicMock()
        da.get_candles.return_value = _make_candles_df(100)

        svc = _make_service(meta=meta, data_access=da)

        # Only provide 4 of the 10 expected features (< 50%)
        available_features = model_features[:4]
        df_features = _make_features_df(available_features, n_rows=5)
        matrix = _make_feature_matrix(available_features, num_rows=5)
        svc.feature_builder.build_features_from_df.return_value = (df_features, matrix)

        result = svc.predict("XAUUSD")
        assert result is None


class TestPredictNaNValues:
    """predict() returns None when > 50% feature values are NaN."""

    def test_more_than_50_percent_nan_returns_none(self):
        """Feature vector with > 50% NaN values -> returns None."""
        feature_names = ["feat_a", "feat_b", "feat_c", "feat_d"]
        meta = _make_metadata(feature_names=feature_names)

        da = MagicMock()
        da.get_candles.return_value = _make_candles_df(100)

        svc = _make_service(meta=meta, data_access=da)

        # Create features where > 50% of last row are NaN
        df_features = _make_features_df(feature_names, n_rows=1, nan_fraction=0.8)
        matrix = _make_feature_matrix(feature_names, num_rows=1)
        svc.feature_builder.build_features_from_df.return_value = (df_features, matrix)

        result = svc.predict("XAUUSD")
        assert result is None


class TestPredictWithCalibration:
    """predict() applies calibrator when one is loaded."""

    def test_calibrator_transforms_probabilities(self):
        """When calibrator loaded for epic, transform() is called on proba."""
        feature_names = ["feat_a", "feat_b", "feat_c", "feat_d"]
        meta = _make_metadata(feature_names=feature_names)

        da = MagicMock()
        da.get_candles.return_value = _make_candles_df(100)

        svc = _make_service(meta=meta, data_access=da)

        df_features = _make_features_df(feature_names, n_rows=1)
        matrix = _make_feature_matrix(feature_names, num_rows=1)
        svc.feature_builder.build_features_from_df.return_value = (df_features, matrix)

        # Install a mock calibrator
        calibrator = MagicMock()
        calibrated_proba = np.array([[0.05, 0.15, 0.80]])
        calibrator.transform.return_value = calibrated_proba
        svc._calibrators["XAUUSD"] = calibrator

        result = svc.predict("XAUUSD")

        calibrator.transform.assert_called_once()
        assert result is not None
        assert result.confidence == pytest.approx(0.80, abs=1e-6)
        assert result.signal_class == 2  # BUY (argmax of calibrated)
        assert result.signal_name == "BUY"


class TestPredictSuccessful:
    """predict() successful path returns correct PredictionResult."""

    def test_returns_correct_fields(self):
        """Full successful prediction returns PredictionResult with all fields."""
        feature_names = ["feat_a", "feat_b", "feat_c", "feat_d"]
        meta = _make_metadata(feature_names=feature_names)

        da = MagicMock()
        da.get_candles.return_value = _make_candles_df(100)

        svc = _make_service(meta=meta, data_access=da)

        df_features = _make_features_df(feature_names, n_rows=1)
        matrix = _make_feature_matrix(feature_names, num_rows=1)
        svc.feature_builder.build_features_from_df.return_value = (df_features, matrix)

        # Model predicts class 2 (BUY) with 0.6 confidence
        model_mock = svc._loaded_models["XAUUSD"][0]
        model_mock.predict_proba.return_value = np.array([[0.1, 0.3, 0.6]])

        result = svc.predict("XAUUSD")

        assert result is not None
        assert isinstance(result, PredictionResult)
        assert result.signal_class == 2
        assert result.signal_name == "BUY"
        assert result.confidence == pytest.approx(0.6, abs=1e-6)
        assert "SELL" in result.probabilities
        assert "HOLD" in result.probabilities
        assert "BUY" in result.probabilities
        assert result.probabilities["SELL"] == pytest.approx(0.1, abs=1e-6)
        assert result.probabilities["HOLD"] == pytest.approx(0.3, abs=1e-6)
        assert result.probabilities["BUY"] == pytest.approx(0.6, abs=1e-6)
        assert result.timestamp is not None

    def test_no_model_loaded_returns_none(self):
        """predict() for an epic with no loaded model returns None."""
        svc = _make_service(meta=None)
        result = svc.predict("BTCUSD")
        assert result is None

    def test_empty_features_returns_none(self):
        """predict() returns None when feature building produces empty DataFrame."""
        feature_names = ["feat_a", "feat_b"]
        meta = _make_metadata(feature_names=feature_names)
        da = MagicMock()
        da.get_candles.return_value = _make_candles_df(100)

        svc = _make_service(meta=meta, data_access=da)

        empty_df = pl.DataFrame()
        matrix = _make_feature_matrix([], num_rows=0)
        matrix.num_features = 0
        svc.feature_builder.build_features_from_df.return_value = (empty_df, matrix)

        result = svc.predict("XAUUSD")
        assert result is None

    def test_insufficient_candles_returns_none(self):
        """predict() returns None when fewer than 50 candles available."""
        feature_names = ["feat_a", "feat_b"]
        meta = _make_metadata(feature_names=feature_names)
        da = MagicMock()
        da.get_candles.return_value = _make_candles_df(30)  # < 50

        svc = _make_service(meta=meta, data_access=da)

        result = svc.predict("XAUUSD")
        assert result is None

    def test_inference_exception_returns_none(self):
        """predict() returns None when model.predict_proba() raises."""
        feature_names = ["feat_a", "feat_b"]
        meta = _make_metadata(feature_names=feature_names)
        da = MagicMock()
        da.get_candles.return_value = _make_candles_df(100)

        svc = _make_service(meta=meta, data_access=da)

        df_features = _make_features_df(feature_names, n_rows=1)
        matrix = _make_feature_matrix(feature_names, num_rows=1)
        svc.feature_builder.build_features_from_df.return_value = (df_features, matrix)

        model_mock = svc._loaded_models["XAUUSD"][0]
        model_mock.predict_proba.side_effect = RuntimeError("XGBoost crash")

        result = svc.predict("XAUUSD")
        assert result is None


# ===========================================================================
# get_market_data() tests
# ===========================================================================

class TestGetMarketData:
    """Tests for get_market_data() including regime detection and RSI."""

    def _mock_ti_chain(self, mock_ti, candles, *, adx=None, rsi=None, ema_50=None):
        """Helper: set up the mock chain for TechnicalIndicators calls."""
        df = candles.clone()
        df = df.with_columns(pl.lit(25.0).alias("atr_14"))
        mock_ti.add_atr.return_value = df

        if adx is not None:
            df = df.with_columns(pl.lit(adx).alias("adx"))
        mock_ti.add_adx.return_value = df

        if rsi is not None:
            df = df.with_columns(pl.lit(rsi).alias("rsi_14"))
        mock_ti.add_rsi.return_value = df

        if ema_50 is not None:
            df = df.with_columns(pl.lit(ema_50).alias("ema_50"))
        mock_ti.add_ema.return_value = df
        return df

    def test_no_data_returns_none(self):
        """get_market_data() returns None when candles DataFrame is empty."""
        da = MagicMock()
        da.get_candles.return_value = pl.DataFrame()

        svc = _make_service(meta=None, data_access=da)
        result = svc.get_market_data("XAUUSD")
        assert result is None

    def test_uses_cached_candles_from_predict(self):
        """get_market_data() reuses candles cached during predict()."""
        feature_names = ["feat_a", "feat_b"]
        meta = _make_metadata(feature_names=feature_names)

        da = MagicMock()
        candles = _make_candles_df(100)
        da.get_candles.return_value = candles

        svc = _make_service(meta=meta, data_access=da)

        # Simulate cache from predict()
        svc._last_candles_cache["XAUUSD"] = ("1h", candles)

        with (
            patch("src.models.prediction_service.TechnicalIndicators") as mock_ti,
            patch("src.features.regime.RegimeDetector") as mock_rd,
        ):
            df = self._mock_ti_chain(mock_ti, candles, adx=30.0, rsi=55.0, ema_50=2050.0)
            df_with_regime = df.with_columns(pl.lit("trending_up").alias("regime"))
            mock_rd.return_value.detect.return_value = df_with_regime

            result = svc.get_market_data("XAUUSD")

        assert result is not None
        assert "current_price" in result
        assert "atr" in result
        assert "adx" in result
        assert result["adx"] == pytest.approx(30.0)
        # Should NOT have called get_candles because cache was used
        da.get_candles.assert_not_called()

    def test_adx_present_in_result(self):
        """get_market_data() includes ADX in result when present in data."""
        da = MagicMock()
        candles = _make_candles_df(30)
        da.get_candles.return_value = candles

        svc = _make_service(meta=None, data_access=da)

        with (
            patch("src.models.prediction_service.TechnicalIndicators") as mock_ti,
            patch("src.features.regime.RegimeDetector") as mock_rd,
        ):
            df = self._mock_ti_chain(mock_ti, candles, adx=45.5, rsi=60.0, ema_50=2050.0)
            df_with_regime = df.with_columns(pl.lit("ranging").alias("regime"))
            mock_rd.return_value.detect.return_value = df_with_regime

            result = svc.get_market_data("XAUUSD")

        assert result is not None
        assert "adx" in result
        assert result["adx"] == pytest.approx(45.5)

    def test_no_adx_in_result(self):
        """get_market_data() omits ADX from result when not present."""
        da = MagicMock()
        candles = _make_candles_df(30)
        da.get_candles.return_value = candles

        svc = _make_service(meta=None, data_access=da)

        with (
            patch("src.models.prediction_service.TechnicalIndicators") as mock_ti,
            patch("src.features.regime.RegimeDetector"),
        ):
            # No ADX or EMA column → regime detector won't trigger
            self._mock_ti_chain(mock_ti, candles)

            result = svc.get_market_data("XAUUSD")

        assert result is not None
        assert "adx" not in result

    def test_fetches_fresh_data_when_not_cached(self):
        """get_market_data() calls data_access with limit=300 when no cache exists."""
        da = MagicMock()
        candles = _make_candles_df(30)
        da.get_candles.return_value = candles

        svc = _make_service(meta=None, data_access=da)

        with (
            patch("src.models.prediction_service.TechnicalIndicators") as mock_ti,
            patch("src.features.regime.RegimeDetector"),
        ):
            self._mock_ti_chain(mock_ti, candles)

            result = svc.get_market_data("XAUUSD")

        assert result is not None
        da.get_candles.assert_called_once_with("XAUUSD", "1h", limit=300)

    def test_regime_present_in_result(self):
        """get_market_data() includes regime when ADX + EMA-50 are present."""
        da = MagicMock()
        candles = _make_candles_df(100)
        da.get_candles.return_value = candles

        svc = _make_service(meta=None, data_access=da)

        with (
            patch("src.models.prediction_service.TechnicalIndicators") as mock_ti,
            patch("src.features.regime.RegimeDetector") as mock_rd,
        ):
            df = self._mock_ti_chain(mock_ti, candles, adx=35.0, rsi=62.0, ema_50=2050.0)
            df_with_regime = df.with_columns(pl.lit("trending_up").alias("regime"))
            mock_rd.return_value.detect.return_value = df_with_regime

            result = svc.get_market_data("XAUUSD")

        assert result is not None
        assert "regime" in result
        assert result["regime"] == "trending_up"
        # RegimeDetector.detect() should have been called
        mock_rd.return_value.detect.assert_called_once()

    def test_rsi_present_in_result(self):
        """get_market_data() includes RSI when computed."""
        da = MagicMock()
        candles = _make_candles_df(100)
        da.get_candles.return_value = candles

        svc = _make_service(meta=None, data_access=da)

        with (
            patch("src.models.prediction_service.TechnicalIndicators") as mock_ti,
            patch("src.features.regime.RegimeDetector") as mock_rd,
        ):
            df = self._mock_ti_chain(mock_ti, candles, adx=28.0, rsi=72.5, ema_50=2050.0)
            df_with_regime = df.with_columns(pl.lit("ranging").alias("regime"))
            mock_rd.return_value.detect.return_value = df_with_regime

            result = svc.get_market_data("XAUUSD")

        assert result is not None
        assert "rsi" in result
        assert result["rsi"] == pytest.approx(72.5)

    def test_regime_not_present_without_adx_ema(self):
        """get_market_data() omits regime when ADX/EMA-50 not in DataFrame."""
        da = MagicMock()
        candles = _make_candles_df(100)
        da.get_candles.return_value = candles

        svc = _make_service(meta=None, data_access=da)

        with (
            patch("src.models.prediction_service.TechnicalIndicators") as mock_ti,
            patch("src.features.regime.RegimeDetector") as mock_rd,
        ):
            # No ADX, no EMA-50 → RegimeDetector should not be called
            self._mock_ti_chain(mock_ti, candles)

            result = svc.get_market_data("XAUUSD")

        assert result is not None
        assert "regime" not in result
        mock_rd.return_value.detect.assert_not_called()

    def test_full_market_data_result(self):
        """get_market_data() returns all fields: current_price, atr, adx, rsi, regime."""
        da = MagicMock()
        candles = _make_candles_df(100)
        da.get_candles.return_value = candles

        svc = _make_service(meta=None, data_access=da)

        with (
            patch("src.models.prediction_service.TechnicalIndicators") as mock_ti,
            patch("src.features.regime.RegimeDetector") as mock_rd,
        ):
            df = self._mock_ti_chain(mock_ti, candles, adx=40.0, rsi=55.0, ema_50=2050.0)
            df_with_regime = df.with_columns(pl.lit("trending_down").alias("regime"))
            mock_rd.return_value.detect.return_value = df_with_regime

            result = svc.get_market_data("XAUUSD")

        assert result is not None
        assert set(result.keys()) == {"current_price", "atr", "adx", "rsi", "regime"}
        assert result["regime"] == "trending_down"
        assert result["adx"] == pytest.approx(40.0)
        assert result["rsi"] == pytest.approx(55.0)
        assert result["current_price"] > 0
        assert result["atr"] > 0
