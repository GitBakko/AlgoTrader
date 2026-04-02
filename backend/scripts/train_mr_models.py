"""
Train XGBoost binary classifiers for MR setup quality scoring.
Uses 4h timeframe and MR targets (GOOD_SETUP vs BAD_SETUP).

Usage:
    cd backend
    .venv/Scripts/python.exe scripts/train_mr_models.py [--epic XAUUSD]
"""

import argparse
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
from loguru import logger

from src.data.data_access import DataAccessLayer
from src.features.builder import FeatureBuilder
from src.models.calibration import ConfidenceCalibrator
from src.models.mr_target_builder import MRTargetBuilder
from src.models.walk_forward import WalkForwardSplitter
from src.models.xgboost_model import XGBoostClassifier
from src.utils.constants import TRADABLE_ASSETS

# Walk-forward windows for 4h data (~6 bars/day)
# ~250 days train, ~62 days val, ~21 days test
WF_PARAMS = {
    "train_window": 1500,
    "val_window": 375,
    "test_window": 125,
    "step_size": 125,
    "purge_gap": 30,
    "embargo": 12,
}

# Features to exclude from training (OHLCV + target + regime one-hot)
EXCLUDE_FEATURES = {
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "target",
    "z_score_target",
    "regime_trending_up",
    "regime_trending_down",
    "regime_ranging",
    "regime",
}


def _make_binary_model() -> XGBoostClassifier:
    """Create an XGBoostClassifier configured for binary classification."""
    model = XGBoostClassifier(
        max_depth=4,
        learning_rate=0.05,
        n_estimators=500,
        subsample=0.7,
        colsample_bytree=0.6,
        min_child_weight=20,
        reg_alpha=1.0,
        reg_lambda=5.0,
        early_stopping_rounds=50,
        n_classes=2,
    )
    # Override: binary:logistic is more appropriate for 2-class than multi:softprob
    model.params["objective"] = "binary:logistic"
    model.params["eval_metric"] = "logloss"
    model.params.pop("num_class", None)
    return model


def train_for_epic(epic: str, timeframe: str = "4h") -> dict | None:
    """Train MR quality model for one epic."""
    logger.info(f"\n{'=' * 60}")
    logger.info(f"Training MR model: {epic}/{timeframe}")
    logger.info(f"{'=' * 60}")

    start = time.monotonic()
    dal = DataAccessLayer()
    builder = FeatureBuilder(data_access=dal)

    # 1. Build features
    try:
        df, feature_meta = builder.build_features(
            epic=epic,
            timeframe=timeframe,
            normalize=True,
            include_regime=True,
            cross_asset=True,
        )
    except Exception as e:
        logger.error(f"[{epic}] Feature build failed: {e}")
        return None

    if df.is_empty():
        logger.warning(f"[{epic}] No data, skipping")
        return None

    logger.info(f"[{epic}] Features: {len(df)} bars, {len(feature_meta.feature_names)} features")

    # 2. Build MR targets
    mr_builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12, mean_column="bb_middle")
    df = mr_builder.build_targets(df)
    dist = mr_builder.get_class_distribution(df)
    logger.info(f"[{epic}] Target distribution: {dist}")

    if dist.get("setup_bars", 0) < 100:
        logger.warning(f"[{epic}] Not enough MR setups ({dist.get('setup_bars', 0)}), skipping")
        return None

    # 3. Filter to setup bars only (target != NaN)
    df_setups = df.filter(~df["target"].is_null() & ~df["target"].is_nan())
    logger.info(f"[{epic}] Setup bars for training: {len(df_setups)}")

    # 4. Prepare feature matrix
    feature_cols = [
        c
        for c in feature_meta.feature_names
        if c in df_setups.columns and c not in EXCLUDE_FEATURES
    ]
    X = df_setups.select(feature_cols).to_numpy().astype(np.float32)
    y = df_setups["target"].to_numpy().astype(np.int32)

    # Replace NaN/inf in features
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    logger.info(f"[{epic}] Training matrix: {X.shape[0]} samples, {X.shape[1]} features")

    # 5. Walk-forward training
    splitter = WalkForwardSplitter(**WF_PARAMS)
    n_samples = len(X)

    if n_samples < splitter.min_samples:
        logger.warning(
            f"[{epic}] Not enough data for walk-forward "
            f"({n_samples} < {splitter.min_samples}), doing simple split"
        )
        return _train_simple_split(epic, X, y, feature_cols, dist, start)

    n_folds = splitter.get_n_splits(n_samples)
    if n_folds < 2:
        logger.warning(f"[{epic}] Only {n_folds} fold(s), doing simple split")
        return _train_simple_split(epic, X, y, feature_cols, dist, start)

    logger.info(f"[{epic}] Walk-forward: {n_folds} folds")

    best_accuracy = 0.0
    best_model = None
    fold_results = []

    for split in splitter.split(n_samples):
        X_train = X[split.train_indices]
        y_train = y[split.train_indices]
        X_val = X[split.val_indices]
        y_val = y[split.val_indices]
        X_test = X[split.test_indices]
        y_test = y[split.test_indices]

        model = _make_binary_model()
        model.feature_names = feature_cols
        model.fit(X_train, y_train, X_val, y_val)

        # Calibrate on validation set
        try:
            calibrator = ConfidenceCalibrator(n_classes=2)
            proba = model.predict_proba(X_val)
            calibrator.fit(y_val, proba)
        except Exception:
            pass

        # Evaluate on test
        test_preds = model.predict(X_test)
        accuracy = float((test_preds == y_test).mean())
        fold_results.append(accuracy)

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_model = model

        logger.info(
            f"  Fold {split.fold_index}/{n_folds - 1}: "
            f"accuracy={accuracy:.3f} "
            f"(train={len(X_train)}, val={len(X_val)}, test={len(X_test)})"
        )

    avg_accuracy = float(np.mean(fold_results))
    logger.info(f"[{epic}] Avg OOS accuracy: {avg_accuracy:.3f} (best: {best_accuracy:.3f})")

    # Save best model
    if best_model is not None:
        model_id = _save_model(best_model, epic)
        elapsed = time.monotonic() - start
        logger.success(
            f"[{epic}] MR model saved: {model_id} "
            f"(avg_acc={avg_accuracy:.3f}, folds={n_folds}, {elapsed:.1f}s)"
        )
        return {
            "epic": epic,
            "accuracy": avg_accuracy,
            "best_accuracy": best_accuracy,
            "model_id": model_id,
            "folds": n_folds,
            "setup_bars": dist.get("setup_bars", 0),
            "reversion_rate": dist.get("reversion_rate", 0),
        }

    return None


def _train_simple_split(
    epic: str,
    X: np.ndarray,
    y: np.ndarray,
    feature_cols: list[str],
    dist: dict,
    start: float,
) -> dict | None:
    """Fallback: simple 80/20 split when walk-forward is not possible."""
    split_idx = int(len(X) * 0.8)
    X_train, X_val = X[:split_idx], X[split_idx:]
    y_train, y_val = y[:split_idx], y[split_idx:]

    model = _make_binary_model()
    model.feature_names = feature_cols
    model.fit(X_train, y_train, X_val, y_val)

    preds = model.predict(X_val)
    accuracy = float((preds == y_val).mean())
    logger.info(f"[{epic}] Simple split accuracy: {accuracy:.3f}")

    model_id = _save_model(model, epic)
    elapsed = time.monotonic() - start
    logger.success(f"[{epic}] MR model saved: {model_id} (accuracy={accuracy:.3f}, {elapsed:.1f}s)")
    return {
        "epic": epic,
        "accuracy": accuracy,
        "model_id": model_id,
        "folds": 1,
        "setup_bars": dist.get("setup_bars", 0),
        "reversion_rate": dist.get("reversion_rate", 0),
    }


def _save_model(model: XGBoostClassifier, epic: str) -> str:
    """Save model to data/models/{epic}/ and return model_id."""
    save_dir = Path(f"data/models/{epic}")
    save_dir.mkdir(parents=True, exist_ok=True)
    model_id = f"xgboost_mr_{epic}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    model.save(save_dir / model_id)
    return model_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Train MR quality models (4h)")
    parser.add_argument("--epic", type=str, default=None, help="Single epic to train")
    args = parser.parse_args()

    epics = [args.epic] if args.epic else list(TRADABLE_ASSETS)

    logger.info(f"{'=' * 60}")
    logger.info("MANTIS AI - Mean Reversion Model Training (4h)")
    logger.info(f"Assets: {epics}")
    logger.info(f"{'=' * 60}")

    results = []
    for epic in epics:
        r = train_for_epic(epic)
        if r:
            results.append(r)

    # Summary
    logger.info(f"\n{'=' * 60}")
    logger.info("MR MODEL TRAINING SUMMARY")
    logger.info(f"{'=' * 60}")
    for r in sorted(results, key=lambda x: x["accuracy"], reverse=True):
        logger.info(
            f"  {r['epic']:10s}: acc={r['accuracy']:.3f} "
            f"folds={r['folds']} setups={r.get('setup_bars', '?')} "
            f"reversion_rate={r.get('reversion_rate', 0):.1%}"
        )
    logger.info(f"Total: {len(results)}/{len(epics)} models trained")


if __name__ == "__main__":
    main()
