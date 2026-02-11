"""
Prediction service: orchestrates real-time ML inference.
Pipeline: DataAccess -> FeatureBuilder -> XGBoost -> PredictionResult
"""

from datetime import datetime, timezone

import numpy as np
from loguru import logger

from src.data.data_access import DataAccessLayer
from src.features.builder import FeatureBuilder
from src.features.technical import TechnicalIndicators
from src.models.calibration import ConfidenceCalibrator
from src.models.schemas import ModelMetadata, PredictionResult, SignalClass
from src.models.versioning import ModelVersioning
from src.models.xgboost_model import XGBoostClassifier


class PredictionService:
    """
    Orchestrates real-time prediction pipeline.

    Loads pre-trained XGBoost models and generates predictions
    by chaining: data loading -> feature building -> inference.
    """

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
        Load latest trained model for each asset.

        Returns:
            Number of models loaded
        """
        loaded = 0
        for epic in ["XAUUSD", "BTCUSD", "US500"]:
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

    def predict(self, epic: str, timeframe: str = "1h") -> PredictionResult | None:
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
            )
        else:
            df = self.data_access.get_candles(epic, timeframe, limit=300)
            if df.is_empty() or len(df) < 50:
                logger.warning(f"Insufficient data for {epic}/{timeframe}: {len(df)} bars")
                return None
            self._last_candles_cache[epic] = (timeframe, df)
            df_features, matrix = self.feature_builder.build_features_from_df(
                df, epic, timeframe, normalize=True, include_regime=True,
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
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Run inference
        try:
            proba = model.predict_proba(X)

            # Apply confidence calibration if available
            if epic in self._calibrators:
                proba = self._calibrators[epic].transform(proba)

            proba_row = proba[0]
            predicted_class = int(np.argmax(proba_row))
            confidence = float(proba_row[predicted_class])

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
        Extract current price and ATR from latest data.
        Reuses cached candles from predict() when available to avoid double query.

        Returns:
            Dict with current_price and atr, or None if no data
        """
        # Reuse candles cached by predict() if same epic/timeframe
        cached = self._last_candles_cache.get(epic)
        if cached and cached[0] == timeframe:
            df = cached[1]
        else:
            df = self.data_access.get_candles(epic, timeframe, limit=30)
        if df.is_empty():
            return None

        df = TechnicalIndicators.add_atr(df, period=14)
        last = df.tail(1).row(0, named=True)

        return {
            "current_price": float(last["close"]),
            "atr": float(last.get("atr_14", last["close"] * 0.01)),
        }

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
