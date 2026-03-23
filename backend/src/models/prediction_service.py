"""
Prediction service: orchestrates real-time ML inference.
Pipeline: DataAccess -> FeatureBuilder -> XGBoost -> PredictionResult
"""

import time as _time
from datetime import datetime, timezone

import numpy as np
import polars as pl
from loguru import logger

from src.data.data_access import DataAccessLayer
from src.features.builder import FeatureBuilder
from src.features.technical import TechnicalIndicators
from src.models.calibration import ConfidenceCalibrator
from src.models.schemas import ModelMetadata, PredictionResult, SignalClass
from src.models.versioning import ModelVersioning
from src.models.xgboost_model import XGBoostClassifier
from src.utils.constants import TRADABLE_ASSETS


class PredictionService:
    """
    Orchestrates real-time prediction pipeline.

    Loads pre-trained XGBoost models and generates predictions
    by chaining: data loading -> feature building -> inference.
    """

    # Assets excluded from live/paper trading (model exists but OOS performance is unviable)
    # EURUSD: tiny ATR (~0.003) causes massive positions → -99% OOS, 0% win rate
    EXCLUDED_EPICS = {"EURUSD"}

    # Active trading epics (from centralized constants)
    ACTIVE_EPICS = TRADABLE_ASSETS

    def __init__(
        self,
        feature_builder: FeatureBuilder,
        model_versioning: ModelVersioning,
        data_access: DataAccessLayer,
    ):
        self.feature_builder = feature_builder
        self.versioning = model_versioning
        self.data_access = data_access
        self._loaded_models: dict[str, tuple[XGBoostClassifier, ModelMetadata]] = {}
        self._calibrators: dict[str, ConfidenceCalibrator] = {}
        self._last_candles_cache: dict[str, tuple[str, object]] = {}  # (cache_key, df)

    def load_models(self) -> int:
        """
        Load latest trained model for each active asset (excludes EURUSD etc.).

        Returns:
            Number of models loaded
        """
        loaded = 0
        for epic in self.ACTIVE_EPICS:
            try:
                models = self.versioning.list_models(epic)
                if not models:
                    continue

                # Filter for XGBoost models (best performing model type for now)
                xgb_models = [m for m in models if m.model_type == "xgboost"]
                if not xgb_models:
                    logger.warning(f"No XGBoost model found for {epic}")
                    continue
                latest = xgb_models[0]  # sorted by created_at desc
                model, meta = self.versioning.load_model(
                    XGBoostClassifier, epic, latest.model_id
                )
                self._loaded_models[epic] = (model, meta)

                # Load calibrator if available
                model_dir = self.versioning.base_dir / epic / latest.model_id
                cal_dir = model_dir / "calibration"
                if cal_dir.exists():
                    try:
                        calibrator = ConfidenceCalibrator()
                        calibrator.load(cal_dir)
                        self._calibrators[epic] = calibrator
                        logger.info(f"Loaded calibrator for {epic}")
                    except Exception as ce:
                        logger.warning(f"Failed to load calibrator for {epic}: {ce}")

                loaded += 1
                logger.info(f"Loaded model for {epic}: {latest.model_id}")
            except Exception as e:
                logger.warning(f"Failed to load model for {epic}: {e}")

        logger.info(f"PredictionService: {loaded} models loaded")
        return loaded

    def predict(self, epic: str, timeframe: str = "1h", sil_data=None) -> PredictionResult | None:
        """
        Generate prediction for an asset using loaded model.

        Args:
            epic: Asset epic (XAUUSD, BTCUSD, US500)
            timeframe: Timeframe for feature calculation

        Returns:
            PredictionResult or None if prediction not possible
        """
        if epic not in self._loaded_models:
            logger.debug(f"No model loaded for {epic}")
            return None

        model, meta = self._loaded_models[epic]

        # Check if model was trained with multi-TF features
        has_multi_tf = any(
            f.startswith("4h_") or f.startswith("1d_")
            for f in (meta.feature_names or [])
        )

        # Build features (multi-TF uses build_features with data_access)
        if has_multi_tf and self.data_access is not None:
            df_features, matrix = self.feature_builder.build_features(
                epic=epic, timeframe=timeframe,
                normalize=True, include_regime=True, multi_timeframe=True,
                sil_data=sil_data,
            )
        else:
            df = self.data_access.get_candles(epic, timeframe, limit=300)
            if df.is_empty() or len(df) < 50:
                logger.warning(f"Insufficient data for {epic}/{timeframe}: {len(df)} bars")
                return None
            self._last_candles_cache[epic] = (timeframe, df)
            df_features, matrix = self.feature_builder.build_features_from_df(
                df, epic, timeframe, normalize=True, include_regime=True,
                sil_data=sil_data,
            )

        if df_features.is_empty() or len(df_features) < 1:
            logger.warning(f"No data for {epic}/{timeframe}")
            return None

        # Cache for get_market_data reuse (only fetch if not already cached)
        if epic not in self._last_candles_cache:
            df_cache = self.data_access.get_candles(epic, timeframe, limit=30)
            self._last_candles_cache[epic] = (timeframe, df_cache)

        if matrix.num_features == 0:
            logger.warning(f"No features built for {epic}/{timeframe}")
            return None

        # Match feature columns with what the model expects
        model_features = meta.feature_names
        if not model_features:
            # Fallback: use all available features
            model_features = matrix.feature_names

        available = [c for c in model_features if c in df_features.columns]
        if len(available) < len(model_features) * 0.5:
            logger.warning(
                f"Feature mismatch: model expects {len(model_features)}, "
                f"only {len(available)} available"
            )
            return None

        # Extract last row as feature vector
        X = df_features.tail(1).select(available).to_numpy()
        nan_count = int(np.isnan(X).sum())
        if nan_count > len(available) * 0.5:
            logger.warning(f"[{epic}] >50% NaN in feature vector ({nan_count}/{len(available)}), skipping")
            return None
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Run inference
        try:
            t0 = _time.monotonic()
            proba = model.predict_proba(X)

            # Apply confidence calibration if available
            if epic in self._calibrators:
                proba = self._calibrators[epic].transform(proba)

            proba_row = proba[0]
            predicted_class = int(np.argmax(proba_row))
            confidence = float(proba_row[predicted_class])
            inference_duration = _time.monotonic() - t0

            # Record prediction metric
            try:
                from src.monitoring.metrics import MetricsCollector
                MetricsCollector.record_model_prediction(
                    epic=epic,
                    model_type="xgboost",
                    predicted_class=SignalClass(predicted_class).name,
                    confidence=confidence,
                    duration=inference_duration,
                )
            except Exception:
                pass

            return PredictionResult(
                signal_class=predicted_class,
                signal_name=SignalClass(predicted_class).name,
                confidence=confidence,
                probabilities={
                    SignalClass(i).name: float(p) for i, p in enumerate(proba_row)
                },
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as e:
            logger.error(f"Inference failed for {epic}: {e}")
            return None

    def get_market_data(self, epic: str, timeframe: str = "1h") -> dict | None:
        """
        Extract current price, ATR, ADX, RSI, regime, and scalp indicators.
        Reuses cached candles from predict() when available to avoid double query.

        Returns:
            Dict with current_price, atr, adx, rsi, regime, and (when scalp mode)
            ema_9, ema_21, macd, macd_signal, macd_histogram, volume, volume_sma_20,
            bb_upper, bb_lower, bb_middle, keltner_upper, keltner_lower.
        """
        from src.features.regime import RegimeDetector
        from src.utils.config import get_settings

        # Reuse candles cached by predict() if same epic/timeframe
        cached = self._last_candles_cache.get(epic)
        if cached and cached[0] == timeframe:
            df = cached[1]
        else:
            # Need 300 bars for EMA-50 + ADX-14 stabilization
            df = self.data_access.get_candles(epic, timeframe, limit=300)
        if df.is_empty():
            return None

        df = TechnicalIndicators.add_atr(df, period=14)
        df = TechnicalIndicators.add_adx(df, period=14)
        df = TechnicalIndicators.add_rsi(df, period=14)
        df = TechnicalIndicators.add_ema(df, periods=[50])

        # Scalp mode: add extra indicators for ScalpScoreStrategy
        settings = get_settings()
        if settings.scalp_mode_enabled:
            df = TechnicalIndicators.add_ema(df, periods=[9, 21])
            df = TechnicalIndicators.add_macd(df)
            df = TechnicalIndicators.add_bollinger_bands(df)
            # Volume SMA (raw, not ratio)
            df = df.with_columns(
                pl.col("volume").rolling_mean(window_size=20).alias("volume_sma_20")
            )
            from src.features.keltner import KeltnerChannel
            df = KeltnerChannel.add_keltner(df)
            # VWAP for directional filter
            from src.features.vwap_bands import VWAPBands
            df = VWAPBands.add_vwap_bands(df)

        # Regime detection (requires adx + ema_50)
        detector = RegimeDetector()
        if "adx" in df.columns and "ema_50" in df.columns:
            df = detector.detect(df)

        last = df.tail(1).row(0, named=True)

        result = {
            "current_price": float(last["close"]),
            "atr": float(last.get("atr_14", last["close"] * 0.01)),
        }

        # ADX for strategy filtering
        adx_val = last.get("adx")
        if adx_val is not None:
            result["adx"] = float(adx_val)

        # RSI for overbought/oversold filtering
        rsi_val = last.get("rsi_14")
        if rsi_val is not None:
            result["rsi"] = float(rsi_val)

        # Regime for strategy routing and parameter adaptation
        regime_val = last.get("regime")
        if regime_val is not None:
            result["regime"] = str(regime_val)

        # Scalp indicators (only present when scalp mode enabled)
        if settings.scalp_mode_enabled:
            for key in (
                "ema_9", "ema_21", "macd_histogram", "macd", "macd_signal",
                "bb_upper", "bb_lower", "bb_middle", "volume_sma_20",
            ):
                val = last.get(key)
                if val is not None:
                    result[key] = float(val)
            # Keltner uses kc_ prefix
            for src_key, dst_key in (
                ("kc_upper", "keltner_upper"),
                ("kc_lower", "keltner_lower"),
            ):
                val = last.get(src_key)
                if val is not None:
                    result[dst_key] = float(val)
            # Raw volume
            vol = last.get("volume")
            if vol is not None:
                result["volume"] = float(vol)
            # VWAP for directional filter
            vwap_val = last.get("vwap_rolling")
            if vwap_val is not None:
                result["vwap"] = float(vwap_val)
            # Recent bars for micro-regime detection (last 100 bars with indicators)
            result["recent_bars"] = df.tail(100)

            # HTF bias from 1H candles (separate query)
            if settings.scalp_htf_enabled:
                htf_bias = self.get_htf_bias(epic)
                if htf_bias is not None:
                    result["htf_bias"] = htf_bias

        return result

    def get_htf_bias(self, epic: str) -> str | None:
        """
        Get 1H higher-timeframe directional bias using EMA-50.

        Returns:
            "bullish" — price > EMA-50 by 0.2%+
            "bearish" — price < EMA-50 by 0.2%+
            None — no clear bias (price near EMA-50)
        """
        try:
            df = self.data_access.get_candles(epic, "1h", limit=100)
            if df.is_empty() or len(df) < 50:
                return None
            df = TechnicalIndicators.add_ema(df, periods=[50])
            last = df.tail(1).row(0, named=True)
            price = float(last["close"])
            ema_50 = float(last.get("ema_50", 0))
            if ema_50 <= 0 or price <= 0:
                return None
            spread = (price - ema_50) / ema_50
            if spread > 0.002:
                return "bullish"
            elif spread < -0.002:
                return "bearish"
            return None
        except Exception as e:
            logger.debug(f"HTF bias failed for {epic}: {e}")
            return None

    def get_loaded_models(self) -> dict[str, dict]:
        """Get info about currently loaded models."""
        result = {}
        for epic, (model, meta) in self._loaded_models.items():
            result[epic] = {
                "model_id": meta.model_id,
                "model_type": meta.model_type,
                "num_features": meta.num_features,
                "created_at": meta.created_at.isoformat(),
                "version": meta.version,
            }
        return result

    @property
    def has_models(self) -> bool:
        """Check if any models are loaded."""
        return len(self._loaded_models) > 0

    def has_model_for(self, epic: str) -> bool:
        """Check if a model is loaded for a specific asset."""
        return epic in self._loaded_models
