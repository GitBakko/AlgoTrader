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


# Approximate hourly bars per trading day for each timeframe
# Gold/BTC trade ~22-24h/day, S&P 500 CFDs ~16-24h; 24 is a safe average
BARS_PER_DAY = {
    "1h": 24,
    "4h": 6,
    "1d": 1,
}


def get_walk_forward_splitter(timeframe: str) -> WalkForwardSplitter:
    """Create a WalkForwardSplitter with windows scaled to the timeframe.

    The base windows are calibrated for daily bars (252/63/21 trading days).
    For intraday timeframes, we scale by bars_per_day to maintain the same
    calendar coverage (~1 year train, ~3 months val, ~1 month test).
    """
    scale = BARS_PER_DAY.get(timeframe, 1)
    return WalkForwardSplitter(
        train_window=252 * scale,
        val_window=63 * scale,
        test_window=21 * scale,
        step_size=21 * scale,
        purge_gap=5 * scale,
        embargo=2 * scale,
    )


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

    min_required = trainer.splitter.min_samples
    if n_bars < min_required:
        logger.error(
            f"Insufficient data: {n_bars} bars, need at least {min_required}. "
            f"Download more historical data."
        )
        return False

    n_folds = trainer.splitter.get_n_splits(n_bars)
    logger.info(f"Walk-forward: {n_folds} folds (train={trainer.splitter.train_window} bars)")

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
            multi_timeframe=True,
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
    splitter = get_walk_forward_splitter(timeframe)

    logger.info(f"Walk-forward config: {splitter.describe(0)}")

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
