"""
Automatic weekly model retraining.
Runs walk-forward training for all active assets and reloads models
into PredictionService on completion.
"""

import asyncio
import time
from functools import partial

from loguru import logger

from src.data.data_access import DataAccessLayer
from src.data.storage import ParquetStorageManager
from src.features.builder import FeatureBuilder
from src.models.target_builder import TargetBuilder
from src.models.trainer import ModelTrainer
from src.models.versioning import ModelVersioning
from src.models.walk_forward import WalkForwardSplitter
from src.models.xgboost_model import XGBoostClassifier
from src.utils.constants import TRADABLE_ASSETS


# Stock epics with fewer trading hours per day
STOCK_EPICS = {"NVDA", "TSLA"}
LIMITED_HOURS_EPICS = {"NAS100"}

BARS_PER_DAY = {"1h": 24, "4h": 6, "1d": 1}
STOCK_BARS_PER_DAY = {"1h": 10, "4h": 3, "1d": 1}
LIMITED_HOURS_BARS_PER_DAY = {"1h": 5, "4h": 2, "1d": 1}


def _get_splitter(timeframe: str, epic: str, horizon_bars: int = 12) -> WalkForwardSplitter:
    """Create walk-forward splitter scaled to timeframe and asset type."""
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


def _train_single_asset(
    epic: str,
    timeframe: str = "1h",
    horizon_bars: int = 12,
    sil_data=None,
) -> tuple[str, bool, str]:
    """
    Train model for a single asset (blocking/sync).
    Returns: (epic, success, message)
    """
    try:
        storage = ParquetStorageManager()
        data_access = DataAccessLayer(storage=storage)
        feature_builder = FeatureBuilder(data_access=data_access)
        versioning = ModelVersioning()
        splitter = _get_splitter(timeframe, epic, horizon_bars=horizon_bars)
        target_builder = TargetBuilder(horizon_bars=horizon_bars)

        trainer = ModelTrainer(
            feature_builder=feature_builder,
            target_builder=target_builder,
            versioning=versioning,
            splitter=splitter,
        )

        # Check data availability
        df = data_access.get_candles(epic, timeframe)
        if df.is_empty():
            return (epic, False, "No data available")

        n_bars = len(df)
        if n_bars < splitter.min_samples:
            return (epic, False, f"Insufficient data ({n_bars} bars)")

        model = XGBoostClassifier(
            max_depth=4,
            learning_rate=0.05,
            n_estimators=1000,
            subsample=0.7,
            colsample_bytree=0.6,
            min_child_weight=20,
            early_stopping_rounds=50,
        )

        result = trainer.train(
            model=model,
            epic=epic,
            timeframe=timeframe,
            save_best=True,
            multi_timeframe=True,
            sil_data=sil_data,
        )

        avg_f1 = result.avg_test_metrics.get("f1_macro", 0.0)
        msg = f"Trained {result.num_folds} folds, avg F1={avg_f1:.4f}"
        return (epic, True, msg)

    except Exception as e:
        return (epic, False, str(e))


async def retrain_all_models(
    prediction_service=None,
    timeframe: str = "1h",
    horizon_bars: int = 12,
    sil_data=None,
) -> dict[str, bool]:
    """
    Retrain all active asset models in a background thread pool.
    After training, reloads models into PredictionService if provided.

    Returns: dict of {epic: success}
    """
    assets = list(TRADABLE_ASSETS)
    logger.info(f"Auto-retrain starting for {len(assets)} assets (tf={timeframe}, horizon={horizon_bars})")
    start = time.monotonic()

    results = {}
    for epic in assets:
        # Run CPU-intensive training in thread pool to avoid blocking event loop
        epic_result, success, msg = await asyncio.to_thread(
            _train_single_asset, epic, timeframe, horizon_bars, sil_data,
        )
        results[epic_result] = success
        status = "OK" if success else "FAIL"
        logger.info(f"  [{status}] {epic}: {msg}")

    elapsed = time.monotonic() - start
    successful = sum(1 for s in results.values() if s)
    logger.info(
        f"Auto-retrain complete: {successful}/{len(assets)} models trained "
        f"in {elapsed:.0f}s"
    )

    # Reload models into PredictionService
    if prediction_service is not None and successful > 0:
        try:
            loaded = prediction_service.load_models()
            logger.info(f"Reloaded {loaded} models into PredictionService")
        except Exception as e:
            logger.error(f"Failed to reload models: {e}")

    return results
