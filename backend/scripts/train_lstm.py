"""
Script per addestrare modelli LSTM su dati storici e confrontarli con XGBoost.
Usa walk-forward optimization con purge+embargo per ogni asset.

Prerequisito: dati storici scaricati via download_data.py

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/train_lstm.py
    .venv/Scripts/python.exe scripts/train_lstm.py --assets XAUUSD --timeframe 1h
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.data.data_access import DataAccessLayer
from src.data.storage import ParquetStorageManager
from src.features.builder import FeatureBuilder
from src.models.lstm_model import LSTMClassifier
from src.models.trainer import ModelTrainer
from src.models.versioning import ModelVersioning
from src.models.walk_forward import WalkForwardSplitter


BARS_PER_DAY = {"1h": 24, "4h": 6, "1d": 1}


def get_walk_forward_splitter(timeframe: str) -> WalkForwardSplitter:
    """Create WalkForwardSplitter scaled to timeframe."""
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
    """Train LSTM model for a single asset. Returns True on success."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Training LSTM {epic}/{timeframe}")
    logger.info(f"{'='*60}")

    df = data_access.get_candles(epic, timeframe)
    if df.is_empty():
        logger.error(f"No data for {epic}/{timeframe}. Run download_data.py first.")
        return False

    n_bars = len(df)
    first = df["timestamp"].min()
    last = df["timestamp"].max()
    logger.info(f"Data: {n_bars} bars ({first.date()} -> {last.date()})")

    min_required = trainer.splitter.min_samples
    if n_bars < min_required:
        logger.error(f"Insufficient data: {n_bars} bars, need {min_required}")
        return False

    n_folds = trainer.splitter.get_n_splits(n_bars)
    logger.info(f"Walk-forward: {n_folds} folds")

    # Create LSTM model
    model = LSTMClassifier(
        seq_len=24,
        hidden_size=64,
        num_layers=2,
        dropout=0.3,
        n_classes=3,
        learning_rate=1e-3,
        batch_size=64,
        max_epochs=50,
        patience=7,
    )

    try:
        result = trainer.train(
            model=model,
            epic=epic,
            timeframe=timeframe,
            save_best=True,
            multi_timeframe=True,
        )

        logger.info(f"\nResults for LSTM {epic}/{timeframe}:")
        logger.info(f"  Folds: {result.num_folds}")
        logger.info(f"  Features: {result.num_features}")
        logger.info(f"  Duration: {result.training_duration_seconds:.1f}s")

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
    """Train LSTM models and compare with XGBoost."""
    logger.info("=" * 60)
    logger.info("AlgoTrader AI - LSTM Model Training")
    logger.info("=" * 60)

    assets = args.assets
    timeframe = args.timeframe

    logger.info(f"Assets: {assets}")
    logger.info(f"Timeframe: {timeframe}")

    storage = ParquetStorageManager()
    data_access = DataAccessLayer(storage=storage)
    feature_builder = FeatureBuilder(data_access=data_access)
    versioning = ModelVersioning()
    splitter = get_walk_forward_splitter(timeframe)

    trainer = ModelTrainer(
        feature_builder=feature_builder,
        versioning=versioning,
        splitter=splitter,
    )

    results = {}
    for epic in assets:
        success = train_asset(trainer, epic, timeframe, data_access)
        results[epic] = success

    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("LSTM TRAINING SUMMARY")
    logger.info(f"{'='*60}")

    for epic, success in results.items():
        status = "OK" if success else "FAIL"
        logger.info(f"  [{status}] {epic}/{timeframe}")

    # Compare with XGBoost
    logger.info(f"\nModel comparison (check saved metadata for metrics):")
    for epic in assets:
        models = versioning.list_models(epic)
        if models:
            for m in models[:5]:
                logger.info(f"  {epic}: {m.model_id}")

    successful = sum(1 for s in results.values() if s)
    logger.info(f"\n{successful}/{len(assets)} LSTM models trained successfully")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train LSTM models for AlgoTrader AI")
    parser.add_argument(
        "--assets", nargs="+", default=["XAUUSD", "BTCUSD", "US500"],
        help="Asset epics to train",
    )
    parser.add_argument(
        "--timeframe", default="1h", help="Timeframe for training",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
