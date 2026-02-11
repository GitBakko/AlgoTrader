"""
Quick verification script: loads new 3-class models and runs predictions
to confirm signals are being generated (not all HOLD).

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/verify_predictions.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.data.data_access import DataAccessLayer
from src.data.storage import ParquetStorageManager
from src.features.builder import FeatureBuilder
from src.models.prediction_service import PredictionService
from src.models.versioning import ModelVersioning


def main():
    logger.info("=" * 60)
    logger.info("Prediction Verification - 3-Class Models")
    logger.info("=" * 60)

    # Initialize services
    storage = ParquetStorageManager()
    data_access = DataAccessLayer(storage=storage)
    feature_builder = FeatureBuilder(data_access=data_access)
    versioning = ModelVersioning()

    prediction_service = PredictionService(
        feature_builder=feature_builder,
        model_versioning=versioning,
        data_access=data_access,
    )

    # Load models
    n_loaded = prediction_service.load_models()
    logger.info(f"Loaded {n_loaded} models")

    if n_loaded == 0:
        logger.error("No models found! Run train_models.py first.")
        return

    # Show loaded models
    for epic, info in prediction_service.get_loaded_models().items():
        logger.info(f"  {epic}: {info['model_id']} ({info['num_features']} features)")

    # Run predictions for each asset
    assets = ["XAUUSD", "BTCUSD", "US500"]
    results = {}

    for epic in assets:
        logger.info(f"\n{'='*40}")
        logger.info(f"Predicting {epic}...")

        prediction = prediction_service.predict(epic, "1h")
        if prediction is None:
            logger.error(f"  FAILED: No prediction for {epic}")
            results[epic] = None
            continue

        results[epic] = prediction
        logger.info(f"  Signal: {prediction.signal_name}")
        logger.info(f"  Confidence: {prediction.confidence:.4f}")
        logger.info(f"  Probabilities: {prediction.probabilities}")

        # Get market data
        market = prediction_service.get_market_data(epic, "1h")
        if market:
            logger.info(f"  Price: {market['current_price']:.2f}, ATR: {market['atr']:.4f}")

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("PREDICTION SUMMARY")
    logger.info(f"{'='*60}")

    signal_counts = {"BUY": 0, "SELL": 0, "HOLD": 0, "FAILED": 0}
    for epic, pred in results.items():
        if pred is None:
            signal_counts["FAILED"] += 1
            logger.info(f"  {epic}: FAILED")
        else:
            signal_counts[pred.signal_name] += 1
            conf_bar = "#" * int(pred.confidence * 20)
            logger.info(
                f"  {epic}: {pred.signal_name:4s} "
                f"(conf={pred.confidence:.2%}) [{conf_bar}]"
            )

    logger.info(f"\nSignal distribution: {signal_counts}")

    # Check: at least one signal is not HOLD
    has_trade_signals = signal_counts["BUY"] > 0 or signal_counts["SELL"] > 0
    if has_trade_signals:
        logger.info("OK: Trade signals (BUY/SELL) are being generated!")
    else:
        logger.warning(
            "WARNING: All signals are HOLD. The min_confidence threshold "
            "or model confidence may need tuning."
        )

    # Check confidence levels
    for epic, pred in results.items():
        if pred and pred.confidence < 0.40:
            logger.warning(
                f"  {epic}: Low confidence ({pred.confidence:.2%}). "
                "Model may need more training data or feature tuning."
            )


if __name__ == "__main__":
    main()
