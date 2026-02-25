"""
Model training orchestrator.
Coordinates feature building, target generation, walk-forward training, and evaluation.
"""

import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import polars as pl
from loguru import logger

from src.features.builder import FeatureBuilder
from src.models.base_model import BaseMLModel
from src.models.calibration import ConfidenceCalibrator
from src.models.evaluator import ModelEvaluator
from src.models.feature_selector import EXCLUDE_FEATURES
from src.models.schemas import FoldResult, ModelMetadata, TrainingResult
from src.models.target_builder import TargetBuilder
from src.models.versioning import ModelVersioning
from src.models.walk_forward import WalkForwardSplitter


class ModelTrainer:
    """
    Orchestrates the full training pipeline:
    1. Build features via FeatureBuilder
    2. Generate targets via TargetBuilder
    3. Walk-forward split
    4. Train + evaluate per fold
    5. Select best model
    6. Save via ModelVersioning
    """

    def __init__(
        self,
        feature_builder: FeatureBuilder | None = None,
        target_builder: TargetBuilder | None = None,
        splitter: WalkForwardSplitter | None = None,
        versioning: ModelVersioning | None = None,
    ):
        self.feature_builder = feature_builder or FeatureBuilder()
        self.target_builder = target_builder or TargetBuilder()
        self.splitter = splitter or WalkForwardSplitter()
        self.versioning = versioning or ModelVersioning()
        self.evaluator = ModelEvaluator()

    def train(
        self,
        model: BaseMLModel,
        epic: str,
        timeframe: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        save_best: bool = True,
        multi_timeframe: bool = False,
        include_sentiment: bool = False,
    ) -> TrainingResult:
        """
        Run the full training pipeline.

        Args:
            model: ML model instance to train (will be mutated)
            epic: Asset epic
            timeframe: Timeframe
            start_date: Training data start
            end_date: Training data end
            save_best: Save the best model to disk
            multi_timeframe: Include higher-timeframe features (4h, 1d)
            include_sentiment: Include sentiment features (NVDA/TSLA only)

        Returns:
            TrainingResult with all fold metrics
        """
        start_time = time.time()

        # Step 1: Build features
        logger.info(f"Building features for {epic}/{timeframe} (multi_tf={multi_timeframe}, sentiment={include_sentiment})...")
        df, feature_meta = self.feature_builder.build_features(
            epic=epic,
            timeframe=timeframe,
            start_date=start_date,
            end_date=end_date,
            normalize=True,
            include_regime=True,
            multi_timeframe=multi_timeframe,
            include_sentiment=include_sentiment,
        )

        if df.is_empty():
            raise ValueError(f"No data available for {epic}/{timeframe}")

        # Step 2: Generate targets
        logger.info("Generating targets...")
        df = self.target_builder.build_targets(df)

        # Step 3: Prepare feature matrix
        result = self._train_on_dataframe(
            model=model,
            df=df,
            feature_meta=feature_meta,
            epic=epic,
            timeframe=timeframe,
            save_best=save_best,
        )

        result.training_duration_seconds = time.time() - start_time
        logger.info(
            f"Training complete: {result.num_folds} folds, "
            f"avg F1={result.avg_val_metrics.get('f1_macro', 0):.4f}, "
            f"duration={result.training_duration_seconds:.1f}s"
        )

        return result

    def train_on_dataframe(
        self,
        model: BaseMLModel,
        df: pl.DataFrame,
        feature_names: list[str],
        epic: str,
        timeframe: str,
        save_best: bool = True,
    ) -> TrainingResult:
        """
        Train on a pre-built DataFrame (useful for testing).

        Args:
            model: ML model instance
            df: DataFrame with features and 'target' column
            feature_names: List of feature column names
            epic: Asset epic
            timeframe: Timeframe
            save_best: Save the best model

        Returns:
            TrainingResult
        """
        from src.features.schemas import FeatureMatrix

        feature_meta = FeatureMatrix(
            epic=epic,
            timeframe=timeframe,
            feature_names=feature_names,
            num_rows=len(df),
            num_features=len(feature_names),
        )

        return self._train_on_dataframe(
            model=model,
            df=df,
            feature_meta=feature_meta,
            epic=epic,
            timeframe=timeframe,
            save_best=save_best,
        )

    def _train_on_dataframe(
        self,
        model: BaseMLModel,
        df: pl.DataFrame,
        feature_meta,
        epic: str,
        timeframe: str,
        save_best: bool,
    ) -> TrainingResult:
        """Internal: run walk-forward training on a prepared DataFrame."""
        # Filter rows with valid targets
        df_valid = df.filter(pl.col("target").is_not_null())

        if df_valid.is_empty():
            raise ValueError("No valid target labels found.")

        # Identify feature columns (normalized z-score columns preferred, fallback to raw)
        zscore_features = [c for c in feature_meta.feature_names if c.endswith("_zscore")]
        raw_features = [
            c for c in feature_meta.feature_names
            if not c.endswith("_zscore") and c != "regime" and f"{c}_zscore" not in df.columns
        ]

        # Use z-score features where available, raw features otherwise
        # Sort each group for deterministic ordering across environments
        feature_cols = sorted(zscore_features) + sorted(raw_features)
        feature_cols = [c for c in feature_cols if c in df_valid.columns]

        # Exclude known problematic features (e.g. collinear regime one-hots)
        feature_cols = [c for c in feature_cols if c not in EXCLUDE_FEATURES]

        if not feature_cols:
            raise ValueError("No feature columns found in DataFrame.")

        # Extract numpy arrays
        X = df_valid.select(feature_cols).to_numpy().astype(np.float64)
        y = df_valid["target"].to_numpy().astype(np.int32)

        # Handle NaN in features (from leading rolling window periods)
        nan_count = int(np.isnan(X).sum())
        if nan_count > 0:
            nan_pct = nan_count / X.size * 100
            if nan_pct > 5.0:
                raise ValueError(
                    f"Feature matrix has {nan_pct:.1f}% NaN values ({nan_count} total). "
                    "This likely indicates a data pipeline issue. Threshold: 5%."
                )
            logger.warning(f"Found {nan_count} NaN values ({nan_pct:.1f}% of feature matrix). Filling with 0.")
        X = np.nan_to_num(X, nan=0.0)

        n_samples = len(X)
        logger.info(f"Training data: {n_samples} samples, {len(feature_cols)} features")

        # Walk-forward splits
        if n_samples < self.splitter.min_samples:
            raise ValueError(
                f"Need at least {self.splitter.min_samples} samples, got {n_samples}. "
                "Reduce window sizes or get more data."
            )

        fold_results = []
        best_val_f1 = -1.0
        best_fold_idx = 0
        best_model_path: Path | None = None
        last_split = None

        # Get timestamps for fold metadata
        timestamps = df_valid["timestamp"].to_list() if "timestamp" in df_valid.columns else None

        # Temp dir for saving best fold's model weights
        tmp_dir = Path(tempfile.mkdtemp(prefix="algotrader_train_"))

        for split in self.splitter.split(n_samples):
            last_split = split
            logger.info(
                f"Fold {split.fold_index}: train[{split.train_start}:{split.train_end}] "
                f"val[{split.val_start}:{split.val_end}] "
                f"test[{split.test_start}:{split.test_end}]"
            )

            X_train = X[split.train_indices]
            y_train = y[split.train_indices]
            X_val = X[split.val_indices]
            y_val = y[split.val_indices]
            X_test = X[split.test_indices]
            y_test = y[split.test_indices]

            # Train
            model.fit(X_train, y_train, X_val, y_val)

            # Evaluate on validation
            y_val_pred = model.predict(X_val)
            y_val_proba = model.predict_proba(X_val)
            # Sequence models (LSTM) may return fewer predictions than input samples;
            # align y by trimming from the front (sequences use last element's label)
            y_val_aligned = y_val[-len(y_val_pred):]
            if len(y_val_aligned) != len(y_val_pred):
                raise ValueError(
                    f"Val alignment mismatch: {len(y_val_aligned)} vs {len(y_val_pred)}"
                )
            val_metrics = self.evaluator.evaluate(y_val_aligned, y_val_pred, y_val_proba)

            # Evaluate on test
            y_test_pred = model.predict(X_test)
            y_test_proba = model.predict_proba(X_test)
            y_test_aligned = y_test[-len(y_test_pred):]
            if len(y_test_aligned) != len(y_test_pred):
                raise ValueError(
                    f"Test alignment mismatch: {len(y_test_aligned)} vs {len(y_test_pred)}"
                )
            test_metrics = self.evaluator.evaluate(y_test_aligned, y_test_pred, y_test_proba)

            fold_result = FoldResult(
                fold_index=split.fold_index,
                train_size=len(X_train),
                val_size=len(X_val),
                test_size=len(X_test),
                train_start=timestamps[split.train_start] if timestamps else None,
                train_end=timestamps[split.train_end - 1] if timestamps else None,
                val_start=timestamps[split.val_start] if timestamps else None,
                val_end=timestamps[split.val_end - 1] if timestamps else None,
                test_start=timestamps[split.test_start] if timestamps else None,
                test_end=timestamps[split.test_end - 1] if timestamps else None,
                val_metrics={k: v for k, v in val_metrics.items()
                             if isinstance(v, (int, float))},
                test_metrics={k: v for k, v in test_metrics.items()
                              if isinstance(v, (int, float))},
            )
            fold_results.append(fold_result)

            val_f1 = val_metrics.get("f1_macro", 0.0)
            if val_f1 > best_val_f1:
                best_val_f1 = val_f1
                best_fold_idx = split.fold_index
                # Save best fold's weights to temp dir
                best_model_path = tmp_dir / f"fold_{split.fold_index}"
                model.save(best_model_path)

            logger.info(
                f"  Val F1={val_metrics['f1_macro']:.4f}, "
                f"Test F1={test_metrics['f1_macro']:.4f}"
            )

        # Restore best fold's model weights
        if best_model_path is not None and best_model_path.exists():
            model.load(best_model_path)
            logger.info(f"Restored best model from fold {best_fold_idx} (F1={best_val_f1:.4f})")

        # Clean up temp directory
        try:
            shutil.rmtree(tmp_dir)
        except OSError as e:
            logger.warning(f"Failed to clean up temp dir {tmp_dir}: {e}")

        # Fit confidence calibrator on last fold's validation set
        calibrator = None
        X_cal = X[last_split.val_indices]
        y_cal = y[last_split.val_indices]
        if len(X_cal) >= 30:
            try:
                cal_proba = model.predict_proba(X_cal)
                y_cal_aligned = y_cal[-len(cal_proba):]
                calibrator = ConfidenceCalibrator(n_classes=len(np.unique(y)))
                cal_stats = calibrator.fit(y_cal_aligned, cal_proba)
                logger.info(
                    f"Confidence calibration: ECE {cal_stats['ece_before']:.4f} -> "
                    f"{cal_stats['ece_after']:.4f}"
                )
            except Exception as e:
                logger.warning(f"Calibration fitting failed: {e}")
                calibrator = None

        # Aggregate metrics
        avg_val = self._average_metrics([f.val_metrics for f in fold_results])
        avg_test = self._average_metrics([f.test_metrics for f in fold_results])

        # Set feature names on model
        model.feature_names = feature_cols

        # Build training result
        result = TrainingResult(
            epic=epic,
            timeframe=timeframe,
            model_type=model.model_type,
            num_folds=len(fold_results),
            fold_results=fold_results,
            avg_val_metrics=avg_val,
            avg_test_metrics=avg_test,
            best_fold_index=best_fold_idx,
            feature_names=feature_cols,
            num_features=len(feature_cols),
            total_train_samples=n_samples,
            hyperparameters=model.get_hyperparameters()
            if hasattr(model, "get_hyperparameters")
            else {},
        )

        # Save best model + calibrator
        if save_best:
            model_id = ModelVersioning.generate_model_id(model.model_type, epic)
            metadata = ModelMetadata(
                model_id=model_id,
                model_type=model.model_type,
                epic=epic,
                timeframe=timeframe,
                feature_names=feature_cols,
                num_features=len(feature_cols),
                horizon_bars=self.target_builder.horizon_bars,
                hyperparameters=result.hyperparameters,
                training_result=result,
            )
            save_path = self.versioning.save_model(model, metadata)
            if calibrator is not None and save_path is not None:
                calibrator.save(save_path / "calibration")
                logger.info(f"Saved calibrator to {save_path / 'calibration'}")

        return result

    @staticmethod
    def _average_metrics(metrics_list: list[dict]) -> dict:
        """Average numeric metrics across folds."""
        if not metrics_list:
            return {}

        all_keys = set()
        for m in metrics_list:
            all_keys.update(k for k, v in m.items() if isinstance(v, (int, float)))

        avg = {}
        for key in all_keys:
            values = [m[key] for m in metrics_list if key in m]
            if values:
                avg[key] = sum(values) / len(values)

        return avg
