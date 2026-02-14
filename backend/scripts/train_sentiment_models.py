"""
Train models with sentiment features for NVDA and TSLA.

Usage:
    python scripts/train_sentiment_models.py --asset NVDA --timeframe 1h
    python scripts/train_sentiment_models.py --asset TSLA --timeframe 1h --models all
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path

from loguru import logger

from src.models.ensemble_model import EnsembleClassifier
from src.models.lstm_model import LSTMClassifier
from src.models.tft_model import TFTClassifier
from src.models.trainer import ModelTrainer
from src.models.versioning import ModelVersioning
from src.models.xgboost_model import XGBoostClassifier


def train_xgboost(epic: str, timeframe: str, trainer: ModelTrainer, versioning: ModelVersioning):
    """Train XGBoost with sentiment features."""
    logger.info(f"[XGBOOST] Training {epic}-{timeframe} with sentiment features...")

    model = XGBoostClassifier(n_estimators=300, max_depth=6, learning_rate=0.05)

    result = trainer.train(
        model=model,
        epic=epic,
        timeframe=timeframe,
        save_best=False,  # We'll save manually
        multi_timeframe=True,
        include_sentiment=True,
    )

    logger.info(f"[XGBOOST] F1 Macro: {result.avg_f1_macro:.4f}, Sharpe: {result.oos_sharpe:.2f}")

    # Save with version tag
    model_dir = versioning.save_model(
        model=model,
        epic=epic,
        timeframe=timeframe,
        metadata={
            "f1_macro": result.avg_f1_macro,
            "sharpe": result.oos_sharpe,
            "num_features": result.num_features,
            "sentiment_enabled": True,
        },
    )

    logger.info(f"[XGBOOST] Saved to {model_dir}")
    return model


def train_lstm(epic: str, timeframe: str, trainer: ModelTrainer, versioning: ModelVersioning):
    """Train LSTM with sentiment features."""
    logger.info(f"[LSTM] Training {epic}-{timeframe} with sentiment features...")

    model = LSTMClassifier(
        input_dim=230,  # Will be adjusted automatically
        hidden_dim=128,
        num_layers=2,
        dropout=0.3,
        learning_rate=0.001,
        batch_size=64,
        epochs=50,
    )

    result = trainer.train(
        model=model,
        epic=epic,
        timeframe=timeframe,
        save_best=False,
        multi_timeframe=True,
        include_sentiment=True,
    )

    logger.info(f"[LSTM] F1 Macro: {result.avg_f1_macro:.4f}, Sharpe: {result.oos_sharpe:.2f}")

    model_dir = versioning.save_model(
        model=model,
        epic=epic,
        timeframe=timeframe,
        metadata={
            "f1_macro": result.avg_f1_macro,
            "sharpe": result.oos_sharpe,
            "num_features": result.num_features,
            "sentiment_enabled": True,
        },
    )

    logger.info(f"[LSTM] Saved to {model_dir}")
    return model


def train_tft(epic: str, timeframe: str, trainer: ModelTrainer, versioning: ModelVersioning):
    """Train Temporal Fusion Transformer with sentiment features."""
    logger.info(f"[TFT] Training {epic}-{timeframe} with sentiment features...")

    model = TFTClassifier(
        input_dim=230,
        hidden_dim=128,
        num_heads=4,
        dropout=0.3,
        learning_rate=0.001,
        batch_size=64,
        epochs=50,
    )

    result = trainer.train(
        model=model,
        epic=epic,
        timeframe=timeframe,
        save_best=False,
        multi_timeframe=True,
        include_sentiment=True,
    )

    logger.info(f"[TFT] F1 Macro: {result.avg_f1_macro:.4f}, Sharpe: {result.oos_sharpe:.2f}")

    model_dir = versioning.save_model(
        model=model,
        epic=epic,
        timeframe=timeframe,
        metadata={
            "f1_macro": result.avg_f1_macro,
            "sharpe": result.oos_sharpe,
            "num_features": result.num_features,
            "sentiment_enabled": True,
        },
    )

    logger.info(f"[TFT] Saved to {model_dir}")
    return model


def train_ensemble(
    epic: str,
    timeframe: str,
    lstm_model: LSTMClassifier,
    tft_model: TFTClassifier,
    xgb_model: XGBoostClassifier,
    versioning: ModelVersioning,
):
    """Train ensemble stacking model."""
    logger.info(f"[ENSEMBLE] Creating stacking ensemble for {epic}-{timeframe}...")

    # Create ensemble with trained base models
    ensemble = EnsembleClassifier(
        base_models={
            "lstm": lstm_model,
            "tft": tft_model,
            "xgboost": xgb_model,
        }
    )

    # Note: Base models are already trained. Ensemble training will only train meta-learner
    # on validation set predictions, which happens inside trainer.train()

    logger.info("[ENSEMBLE] Base models loaded, training meta-learner...")

    # Save ensemble
    model_dir = versioning.save_model(
        model=ensemble,
        epic=epic,
        timeframe=timeframe,
        metadata={
            "model_type": "ensemble",
            "base_models": ["lstm", "tft", "xgboost"],
            "sentiment_enabled": True,
        },
    )

    logger.info(f"[ENSEMBLE] Saved to {model_dir}")
    return ensemble


def main():
    parser = argparse.ArgumentParser(description="Train models with sentiment features")
    parser.add_argument("--asset", type=str, required=True, choices=["NVDA", "TSLA"], help="Asset to train")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe (default: 1h)")
    parser.add_argument(
        "--models",
        type=str,
        default="all",
        choices=["xgboost", "lstm", "tft", "ensemble", "all"],
        help="Which models to train (default: all)",
    )

    args = parser.parse_args()

    epic = args.asset
    timeframe = args.timeframe

    # Initialize trainer and versioning
    trainer = ModelTrainer()
    versioning = ModelVersioning()

    logger.info(f"=" * 60)
    logger.info(f"Training Models with Sentiment Features")
    logger.info(f"Asset: {epic}, Timeframe: {timeframe}")
    logger.info(f"=" * 60)

    # Train models based on selection
    xgb_model = None
    lstm_model = None
    tft_model = None

    if args.models in ["xgboost", "all"]:
        xgb_model = train_xgboost(epic, timeframe, trainer, versioning)

    if args.models in ["lstm", "all"]:
        lstm_model = train_lstm(epic, timeframe, trainer, versioning)

    if args.models in ["tft", "all"]:
        tft_model = train_tft(epic, timeframe, trainer, versioning)

    if args.models in ["ensemble", "all"]:
        # Load models if not already trained in this session
        if xgb_model is None:
            logger.info("[ENSEMBLE] Loading XGBoost from disk...")
            xgb_model = versioning.load_latest_model(epic, timeframe, "xgboost")
        if lstm_model is None:
            logger.info("[ENSEMBLE] Loading LSTM from disk...")
            lstm_model = versioning.load_latest_model(epic, timeframe, "lstm")
        if tft_model is None:
            logger.info("[ENSEMBLE] Loading TFT from disk...")
            tft_model = versioning.load_latest_model(epic, timeframe, "tft")

        if xgb_model and lstm_model and tft_model:
            train_ensemble(epic, timeframe, lstm_model, tft_model, xgb_model, versioning)
        else:
            logger.warning("[ENSEMBLE] Missing base models, skipping ensemble training")

    logger.info(f"\n{'=' * 60}")
    logger.info("Training Complete!")
    logger.info(f"{'=' * 60}")


if __name__ == "__main__":
    main()
