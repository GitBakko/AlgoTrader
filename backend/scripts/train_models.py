"""
Script per addestrare modelli XGBoost su dati storici scaricati.
Usa walk-forward optimization con purge+embargo per ogni asset.
Supporta Optuna hyperparameter tuning e feature selection.

Prerequisito: dati storici scaricati via download_data.py

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/train_models.py
    .venv/Scripts/python.exe scripts/train_models.py --tune --prune-pct 0.25
    .venv/Scripts/python.exe scripts/train_models.py --assets XAUUSD --timeframe 1h --tune
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# Add backend src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger

from src.data.data_access import DataAccessLayer
from src.data.storage import ParquetStorageManager
from src.features.builder import FeatureBuilder
from src.models.target_builder import TargetBuilder
from src.models.trainer import ModelTrainer
from src.models.versioning import ModelVersioning
from src.models.walk_forward import WalkForwardSplitter
from src.models.xgboost_model import XGBoostClassifier


# Approximate hourly bars per trading day for each timeframe
# Gold/BTC/Forex trade ~22-24h/day, S&P 500/DAX CFDs ~16-24h
BARS_PER_DAY = {
    "1h": 24,
    "4h": 6,
    "1d": 1,
}

# Individual stocks (NVDA, TSLA) trade ~8-11h/day on Capital.com CFDs
STOCK_EPICS = {"NVDA", "TSLA"}
STOCK_BARS_PER_DAY = {
    "1h": 10,
    "4h": 3,
    "1d": 1,
}

# NAS100 trades very limited hours on Capital.com (~5h/day)
LIMITED_HOURS_EPICS = {"NAS100"}
LIMITED_HOURS_BARS_PER_DAY = {
    "1h": 5,
    "4h": 2,
    "1d": 1,
}

# Import centralized asset definitions
from src.utils.constants import (
    ALL_ASSETS as _ALL_ASSETS,
    CRYPTO_ASSETS as CRYPTO_EPICS,
    TRADABLE_ASSETS,
)

# Active trading assets (EURUSD excluded: tiny ATR → massive position sizes → -99% OOS)
ACTIVE_ASSETS = list(TRADABLE_ASSETS)
ALL_ASSETS = list(_ALL_ASSETS)

# Directory to save/load tuned hyperparameters
TUNED_PARAMS_DIR = Path(__file__).parent.parent / "data" / "tuned_params"


def get_walk_forward_splitter(
    timeframe: str, epic: str = "", horizon_bars: int = 12
) -> WalkForwardSplitter:
    """Create a WalkForwardSplitter with windows scaled to the timeframe.

    The base windows are calibrated for daily bars (252/63/21 trading days).
    For intraday timeframes, we scale by bars_per_day to maintain the same
    calendar coverage (~1 year train, ~3 months val, ~1 month test).
    Stock epics (NVDA, TSLA) use reduced bars_per_day since they trade fewer hours.
    Purge gap and embargo scale with horizon to prevent data leakage.
    """
    if epic in STOCK_EPICS:
        scale = STOCK_BARS_PER_DAY.get(timeframe, 1)
    elif epic in LIMITED_HOURS_EPICS:
        scale = LIMITED_HOURS_BARS_PER_DAY.get(timeframe, 1)
    else:
        scale = BARS_PER_DAY.get(timeframe, 1)
    return WalkForwardSplitter(
        train_window=252 * scale,
        val_window=63 * scale,
        test_window=21 * scale,
        step_size=21 * scale,
        purge_gap=max(5 * scale, 2 * horizon_bars),
        embargo=max(2 * scale, horizon_bars),
    )


def tune_hyperparameters(
    epic: str,
    timeframe: str,
    feature_builder: FeatureBuilder,
    splitter: WalkForwardSplitter,
    n_trials: int = 40,
    horizon_bars: int = 6,
) -> dict:
    """Run Optuna tuning on the first walk-forward fold. Returns best params dict."""
    from src.models.tuner import XGBoostTuner

    logger.info(f"Tuning hyperparameters for {epic} ({n_trials} trials, horizon={horizon_bars})...")

    # Build features
    df, feature_meta = feature_builder.build_features(
        epic=epic, timeframe=timeframe, normalize=True,
        include_regime=True, multi_timeframe=True,
    )
    if df.is_empty():
        logger.warning(f"No data for {epic}/{timeframe}, skipping tuning")
        return {}

    target_builder = TargetBuilder(horizon_bars=horizon_bars)
    df = target_builder.build_targets(df)
    df_valid = df.filter(df["target"].is_not_null())

    # Extract feature matrix
    zscore_features = [c for c in feature_meta.feature_names if c.endswith("_zscore")]
    raw_features = [
        c for c in feature_meta.feature_names
        if not c.endswith("_zscore") and c != "regime" and f"{c}_zscore" not in df.columns
    ]
    feature_cols = zscore_features + raw_features
    feature_cols = [c for c in feature_cols if c in df_valid.columns]

    X = df_valid.select(feature_cols).to_numpy().astype(np.float64)
    y = df_valid["target"].to_numpy().astype(np.int32)
    X = np.nan_to_num(X, nan=0.0)

    n_samples = len(X)
    if n_samples < splitter.min_samples:
        logger.warning(f"Not enough data for tuning ({n_samples} < {splitter.min_samples})")
        return {}

    # Get first fold
    first_split = next(splitter.split(n_samples))
    X_train = X[first_split.train_indices]
    y_train = y[first_split.train_indices]
    X_val = X[first_split.val_indices]
    y_val = y[first_split.val_indices]

    # Feature selection before tuning (optional, reduces search space)
    tuner = XGBoostTuner(n_trials=n_trials)
    best_params = tuner.tune(X_train, y_train, X_val, y_val)

    return best_params


def save_tuned_params(epic: str, timeframe: str, params: dict) -> None:
    """Save tuned hyperparameters to disk for reuse."""
    TUNED_PARAMS_DIR.mkdir(parents=True, exist_ok=True)
    path = TUNED_PARAMS_DIR / f"{epic}_{timeframe}.json"
    path.write_text(json.dumps(params, indent=2))
    logger.info(f"Saved tuned params to {path}")


def load_tuned_params(epic: str, timeframe: str) -> dict | None:
    """Load previously tuned params. Returns None if not found."""
    path = TUNED_PARAMS_DIR / f"{epic}_{timeframe}.json"
    if path.exists():
        params = json.loads(path.read_text())
        logger.info(f"Loaded tuned params from {path}")
        return params
    return None


def train_asset(
    trainer: ModelTrainer,
    epic: str,
    timeframe: str,
    data_access: DataAccessLayer,
    xgb_params: dict | None = None,
) -> bool:
    """Train XGBoost model for a single asset. Returns True on success."""
    logger.info(f"\n{'='*60}")
    logger.info(f"Training {epic}/{timeframe}")
    if xgb_params:
        logger.info(f"Using tuned params: {xgb_params}")
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

    # Create model with tuned or default params
    if xgb_params:
        model = XGBoostClassifier(
            max_depth=xgb_params.get("max_depth", 4),
            learning_rate=xgb_params.get("learning_rate", 0.05),
            n_estimators=xgb_params.get("n_estimators", 1000),
            subsample=xgb_params.get("subsample", 0.7),
            colsample_bytree=xgb_params.get("colsample_bytree", 0.6),
            min_child_weight=xgb_params.get("min_child_weight", 20),
            reg_alpha=xgb_params.get("reg_alpha", 1.0),
            reg_lambda=xgb_params.get("reg_lambda", 5.0),
            early_stopping_rounds=50,
        )
    else:
        model = XGBoostClassifier(
            max_depth=4,
            learning_rate=0.05,
            n_estimators=1000,
            subsample=0.7,
            colsample_bytree=0.6,
            min_child_weight=20,
            early_stopping_rounds=50,
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
    logger.info("MANTIS AI - Model Training")
    if args.tune:
        logger.info(f"  Optuna tuning: {args.tune_trials} trials per asset")
    logger.info(f"  Prediction horizon: {args.horizon} bars")
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

    # Train each asset
    results = {}
    for epic in assets:
        splitter = get_walk_forward_splitter(timeframe, epic, horizon_bars=args.horizon)
        logger.info(f"Walk-forward config for {epic}: {splitter.describe(0)}")

        # Optuna hyperparameter tuning
        xgb_params = None
        if args.tune:
            # Try to load cached params first
            if not args.retune:
                xgb_params = load_tuned_params(epic, timeframe)

            if xgb_params is None:
                xgb_params = tune_hyperparameters(
                    epic, timeframe, feature_builder, splitter,
                    args.tune_trials, horizon_bars=args.horizon,
                )
                if xgb_params:
                    save_tuned_params(epic, timeframe, xgb_params)

        target_builder = TargetBuilder(horizon_bars=args.horizon)
        trainer = ModelTrainer(
            feature_builder=feature_builder,
            target_builder=target_builder,
            versioning=versioning,
            splitter=splitter,
        )
        success = train_asset(trainer, epic, timeframe, data_access, xgb_params)
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
        default=ACTIVE_ASSETS,
        help="Asset epics to train (default: 20 active assets, excludes EURUSD)",
    )
    parser.add_argument(
        "--timeframe",
        default="1h",
        help="Timeframe for training (default: 1h)",
    )
    parser.add_argument(
        "--tune", action="store_true",
        help="Enable Optuna hyperparameter tuning (80 trials per asset)",
    )
    parser.add_argument(
        "--tune-trials", type=int, default=80,
        help="Number of Optuna trials per asset (default: 80)",
    )
    parser.add_argument(
        "--retune", action="store_true",
        help="Force re-tuning even if cached params exist",
    )
    parser.add_argument(
        "--horizon", type=int, default=12,
        help="Prediction horizon in bars (default: 12). Try 3 for short-term, 6 for medium",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args)
