"""
Script per addestrare modelli XGBoost su dati storici scaricati.
Usa walk-forward optimization con purge+embargo per ogni asset.

Prerequisito: dati storici scaricati via download_data.py

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/train_models.py
    .venv/Scripts/python.exe scripts/train_models.py --assets XAUUSD --timeframe 1h
"""

import argparse
import sys
from pathlib import Path

# Add backend src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.data.data_access import DataAccessLayer
from src.data.storage import ParquetStorageManager
from src.features.builder import FeatureBuilder
from src.models.trainer import ModelTrainer
from src.models.versioning import ModelVersioning
from src.models.walk_forward import WalkForwardSplitter
from src.models.xgboost_model import XGBoostClassifier


# Walk-forward needs at least 343 bars (252 train + 5 purge + 63 val + 2 embargo + 21 test)
MIN_BARS_REQUIRED = 343


def train_asset(
    trainer: ModelTrainer,
    epic: str,
    timeframe: str,
    data_access: DataAccessLayer,
) -> bool:
    """Train XGBoost model for a single asset. Returns True on success."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Training {epic}/{timeframe}")
    logger.info(f"{'='*60}")

    # Check data availability
    df = data_access.get_candles(epic, timeframe)
    if df.is_empty():
        logger.error(f"No data available for {epic}/{timeframe}. Run download_data.py first.")
        return False

    n_bars = len(df)
    first = df["timestamp"].min()
    last = df["timestamp"].max()
    logger.info(f"Data: {n_bars} bars ({first.date()} -> {last.date()})")

    if n_bars < MIN_BARS_REQUIRED:
        logger.error(
            f"Insufficient data: {n_bars} bars, need at least {MIN_BARS_REQUIRED}. "
            f"Download more historical data."
        )
        return False

    # Create a fresh model instance for each asset
    model = XGBoostClassifier(
        max_depth=6,
        learning_rate=0.1,
        n_estimators=500,
        subsample=0.8,
        colsample_bytree=0.8,
        min_child_weight=5,
        early_stopping_rounds=20,
    )

    try:
        result = trainer.train(
            model=model,
            epic=epic,
            timeframe=timeframe,
            save_best=True,
        )

        # Print results
        logger.info(f"\nResults for {epic}/{timeframe}:")
        logger.info(f"  Folds: {result.num_folds}")
        logger.info(f"  Features: {result.num_features}")
        logger.info(f"  Total samples: {result.total_train_samples}")
        logger.info(f"  Training duration: {result.training_duration_seconds:.1f}s")

        logger.info(f"\n  Average Validation Metrics:")
        for key, val in sorted(result.avg_val_metrics.items()):
            logger.info(f"    {key}: {val:.4f}")

        logger.info(f"\n  Average Test Metrics:")
        for key, val in sorted(result.avg_test_metrics.items()):
            logger.info(f"    {key}: {val:.4f}")

        logger.info(f"\n  Per-fold results:")
        for fold in result.fold_results:
            val_f1 = fold.val_metrics.get("f1_macro", 0)
            test_f1 = fold.test_metrics.get("f1_macro", 0)
            val_acc = fold.val_metrics.get("accuracy", 0)
            test_acc = fold.test_metrics.get("accuracy", 0)
            logger.info(
                f"    Fold {fold.fold_index}: "
                f"Val(F1={val_f1:.4f}, Acc={val_acc:.4f}) "
                f"Test(F1={test_f1:.4f}, Acc={test_acc:.4f})"
            )

        logger.info(f"\n  Best fold: {result.best_fold_index}")
        return True

    except Exception as e:
        logger.error(f"Training failed for {epic}/{timeframe}: {e}", exc_info=True)
        return False


def main(args: argparse.Namespace) -> None:
    """Train XGBoost models for all configured assets."""
    logger.info("=" * 60)
    logger.info("AlgoTrader AI - Model Training")
    logger.info("=" * 60)

    assets = args.assets
    timeframe = args.timeframe

    logger.info(f"Assets: {assets}")
    logger.info(f"Timeframe: {timeframe}")

    # Initialize components
    storage = ParquetStorageManager()
    data_access = DataAccessLayer(storage=storage)
    feature_builder = FeatureBuilder(data_access=data_access)
    versioning = ModelVersioning()
    splitter = WalkForwardSplitter()

    trainer = ModelTrainer(
        feature_builder=feature_builder,
        versioning=versioning,
        splitter=splitter,
    )

    # Train each asset
    results = {}
    for epic in assets:
        success = train_asset(trainer, epic, timeframe, data_access)
        results[epic] = success

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("TRAINING SUMMARY")
    logger.info(f"{'='*60}")

    for epic, success in results.items():
        status = "OK" if success else "FAIL"
        logger.info(f"  [{status}] {epic}/{timeframe}")

    # List saved models
    logger.info(f"\nSaved models:")
    for epic in assets:
        models = versioning.list_models(epic)
        if models:
            for m in models[:3]:
                logger.info(f"  {epic}: {m.model_id} (created: {m.created_at})")
        else:
            logger.info(f"  {epic}: no models saved")

    successful = sum(1 for s in results.values() if s)
    logger.info(f"\n{successful}/{len(assets)} models trained successfully")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train XGBoost models for AlgoTrader AI")
    parser.add_argument(
        "--assets",
        nargs="+",
        default=["XAUUSD", "BTCUSD", "US500"],
        help="Asset epics to train (default: XAUUSD BTCUSD US500)",
    )
    parser.add_argument(
        "--timeframe",
        default="1h",
        help="Timeframe for training (default: 1h)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
