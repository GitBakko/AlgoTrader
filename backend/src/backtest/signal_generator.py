"""
Backtest signal generator.
Generates ML-based trading signals for historical backtesting by running
batch inference on an entire OHLC DataFrame.
"""

import numpy as np
import polars as pl
from loguru import logger

from src.features.builder import FeatureBuilder
from src.features.technical import TechnicalIndicators
from src.models.calibration import ConfidenceCalibrator
from src.models.schemas import SignalClass
from src.models.xgboost_model import XGBoostClassifier


class BacktestSignalGenerator:
    """
    Generates trading signals for backtesting using a trained ML model.

    Unlike PredictionService (which predicts only the latest bar),
    this generates signals for ALL bars in a historical DataFrame using
    efficient batch inference.
    """

    def generate_signals(
        self,
        model: XGBoostClassifier,
        feature_builder: FeatureBuilder,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
        feature_names: list[str],
        calibrator: ConfidenceCalibrator | None = None,
        min_confidence: float = 0.40,
    ) -> pl.DataFrame:
        """
        Generate signals for each bar in the OHLC DataFrame.

        Args:
            model: Trained XGBoost model
            feature_builder: FeatureBuilder instance
            ohlc_df: OHLC DataFrame with timestamp, open, high, low, close, volume
            epic: Asset epic (XAUUSD, BTCUSD, US500)
            timeframe: Timeframe (1h, 4h, 1d)
            feature_names: Feature column names the model was trained with
            calibrator: Optional confidence calibrator
            min_confidence: Minimum confidence threshold (below → HOLD)

        Returns:
            DataFrame with columns: timestamp, signal (int), confidence (float), atr (float)
        """
        if ohlc_df.is_empty():
            return pl.DataFrame(schema={
                "timestamp": pl.Datetime,
                "signal": pl.Int32,
                "confidence": pl.Float64,
                "atr": pl.Float64,
            })

        # Step 1: Build features from OHLC
        # Detect if model needs multi-timeframe features (4h_, 1d_ prefixed)
        has_multi_tf = any(
            f.startswith("4h_") or f.startswith("1d_")
            for f in feature_names
        )

        logger.info(
            f"Building features for backtest: {epic}/{timeframe}, "
            f"{len(ohlc_df)} bars, multi_tf={has_multi_tf}"
        )

        if has_multi_tf and feature_builder.data_access is not None:
            # Use build_features() which loads higher-TF data from DataAccessLayer
            start_date = ohlc_df["timestamp"].min()
            end_date = ohlc_df["timestamp"].max()
            df_features, matrix = feature_builder.build_features(
                epic=epic, timeframe=timeframe,
                start_date=start_date, end_date=end_date,
                normalize=True, include_regime=True, multi_timeframe=True,
            )
        else:
            df_features, matrix = feature_builder.build_features_from_df(
                ohlc_df, epic, timeframe, normalize=True, include_regime=True,
            )

        if df_features.is_empty():
            logger.warning(f"Feature building returned empty DataFrame for {epic}")
            return pl.DataFrame(schema={
                "timestamp": pl.Datetime,
                "signal": pl.Int32,
                "confidence": pl.Float64,
                "atr": pl.Float64,
            })

        # Step 2: Ensure ATR is available
        if "atr_14" not in df_features.columns:
            df_features = TechnicalIndicators.add_atr(df_features, period=14)

        # Step 3: Filter out non-numeric columns (e.g. 'regime' is a string)
        non_numeric_cols = {"regime"}
        feature_names = [c for c in feature_names if c not in non_numeric_cols]

        # Align feature columns with model expectations
        available = [c for c in feature_names if c in df_features.columns]
        if len(available) < len(feature_names) * 0.5:
            logger.warning(
                f"Feature mismatch: model expects {len(feature_names)}, "
                f"only {len(available)} available. Aborting."
            )
            return pl.DataFrame(schema={
                "timestamp": pl.Datetime,
                "signal": pl.Int32,
                "confidence": pl.Float64,
                "atr": pl.Float64,
            })

        missing = [c for c in feature_names if c not in df_features.columns]
        if missing:
            logger.debug(f"Adding {len(missing)} missing features as zeros: {missing[:5]}...")
            for col in missing:
                df_features = df_features.with_columns(pl.lit(0.0).alias(col))

        # Step 4: Extract feature matrix (all rows)
        X = df_features.select(feature_names).to_numpy().astype(np.float64)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        # Step 5: Batch inference
        logger.info(f"Running batch inference: {len(X)} samples, {len(feature_names)} features")
        proba = model.predict_proba(X)

        # Step 6: Apply calibration
        if calibrator is not None:
            proba = calibrator.transform(proba)

        # Step 7: Extract predictions and confidence
        predicted_classes = np.argmax(proba, axis=1).astype(np.int32)
        confidences = np.max(proba, axis=1)

        # Step 8: Apply confidence threshold (below → HOLD)
        hold_mask = confidences < min_confidence
        predicted_classes[hold_mask] = SignalClass.HOLD

        # Step 9: Build result DataFrame
        timestamps = df_features["timestamp"].to_list()
        atr_values = df_features["atr_14"].to_list() if "atr_14" in df_features.columns else [0.0] * len(timestamps)

        signals_df = pl.DataFrame({
            "timestamp": timestamps,
            "signal": predicted_classes.tolist(),
            "confidence": confidences.tolist(),
            "atr": atr_values,
        })

        # Stats
        n_buy = int((predicted_classes == SignalClass.BUY).sum())
        n_sell = int((predicted_classes == SignalClass.SELL).sum())
        n_hold = int((predicted_classes == SignalClass.HOLD).sum())
        logger.info(
            f"Signals generated: {n_buy} BUY, {n_sell} SELL, {n_hold} HOLD "
            f"(threshold filtered: {int(hold_mask.sum())})"
        )

        return signals_df
