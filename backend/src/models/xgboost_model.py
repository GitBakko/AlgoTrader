"""
XGBoost classifier for AlgoTrader AI.
First ML model: fast, robust, no GPU needed, good feature importance.
"""

import json
from pathlib import Path

import numpy as np
import xgboost as xgb
from loguru import logger

from src.models.base_model import BaseMLModel
from src.models.schemas import SignalClass


class XGBoostClassifier(BaseMLModel):
    """
    XGBoost multi-class classifier for market direction prediction.

    Predicts 5 classes: STRONG_SELL, SELL, HOLD, BUY, STRONG_BUY
    using ATR-relative targets.
    """

    def __init__(
        self,
        max_depth: int = 6,
        learning_rate: float = 0.1,
        n_estimators: int = 500,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        min_child_weight: int = 5,
        reg_alpha: float = 0.1,
        reg_lambda: float = 1.0,
        early_stopping_rounds: int = 50,
        n_classes: int = 5,
        feature_names: list[str] | None = None,
        random_state: int = 42,
    ):
        self.n_classes = n_classes
        self.feature_names = feature_names
        self.early_stopping_rounds = early_stopping_rounds
        self.random_state = random_state

        self.params = {
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "n_estimators": n_estimators,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "min_child_weight": min_child_weight,
            "reg_alpha": reg_alpha,
            "reg_lambda": reg_lambda,
            "objective": "multi:softprob",
            "num_class": n_classes,
            "eval_metric": "mlogloss",
            "tree_method": "hist",
            "random_state": random_state,
            "verbosity": 0,
        }

        self._model: xgb.XGBClassifier | None = None
        self._fitted = False

    @property
    def model_type(self) -> str:
        return "xgboost"

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> dict:
        """
        Train XGBoost classifier.

        Uses class weights to handle HOLD class imbalance.
        Uses early stopping on validation set if provided.
        """
        # Compute class weights (inverse frequency)
        class_counts = np.bincount(y_train.astype(int), minlength=self.n_classes)
        total = len(y_train)
        sample_weights = np.ones(len(y_train), dtype=np.float64)

        for cls_idx in range(self.n_classes):
            if class_counts[cls_idx] > 0:
                weight = total / (self.n_classes * class_counts[cls_idx])
                mask = y_train.astype(int) == cls_idx
                sample_weights[mask] = weight

        # Build classifier
        self._model = xgb.XGBClassifier(**self.params)

        # Fit
        fit_params = {
            "X": X_train,
            "y": y_train,
            "sample_weight": sample_weights,
            "verbose": False,
        }

        if X_val is not None and y_val is not None:
            fit_params["eval_set"] = [(X_val, y_val)]
            self._model.set_params(early_stopping_rounds=self.early_stopping_rounds)

        self._model.fit(**fit_params)
        self._fitted = True

        # Training info
        info = {
            "n_estimators_used": self._model.best_iteration + 1
            if hasattr(self._model, "best_iteration") and self._model.best_iteration is not None
            else self.params["n_estimators"],
            "class_distribution": {
                SignalClass(i).name: int(c) for i, c in enumerate(class_counts)
            },
        }

        logger.info(
            f"XGBoost trained: {info['n_estimators_used']} trees, "
            f"classes={info['class_distribution']}"
        )

        return info

    def predict(self, X: np.ndarray) -> np.ndarray:
        """Predict class labels."""
        if not self._fitted or self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return self._model.predict(X)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        if not self._fitted or self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        return self._model.predict_proba(X)

    def save(self, path: Path) -> None:
        """
        Save model to disk.

        Saves:
        - model.json: XGBoost model file
        - params.json: Hyperparameters and feature names
        """
        if not self._fitted or self._model is None:
            raise RuntimeError("Model not fitted. Cannot save.")

        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save XGBoost model
        model_path = path / "model.json"
        self._model.save_model(str(model_path))

        # Save params and metadata
        meta = {
            "params": self.params,
            "feature_names": self.feature_names,
            "n_classes": self.n_classes,
            "early_stopping_rounds": self.early_stopping_rounds,
        }
        meta_path = path / "params.json"
        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info(f"XGBoost model saved to {path}")

    def load(self, path: Path) -> None:
        """Load model from disk."""
        path = Path(path)

        model_path = path / "model.json"
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

        # Load params
        meta_path = path / "params.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            self.params = meta.get("params", self.params)
            self.feature_names = meta.get("feature_names")
            self.n_classes = meta.get("n_classes", 5)

        # Load XGBoost model
        self._model = xgb.XGBClassifier(**self.params)
        self._model.load_model(str(model_path))
        self._fitted = True

        logger.info(f"XGBoost model loaded from {path}")

    def get_feature_importance(self) -> dict[str, float]:
        """
        Get feature importance scores (gain-based).

        Returns:
            Dict mapping feature name to importance score
        """
        if not self._fitted or self._model is None:
            raise RuntimeError("Model not fitted.")

        importance = self._model.get_booster().get_score(importance_type="gain")

        # Map feature indices to names if available
        if self.feature_names:
            named_importance = {}
            for key, value in importance.items():
                # XGBoost uses "f0", "f1", etc. or actual names
                if key.startswith("f") and key[1:].isdigit():
                    idx = int(key[1:])
                    if idx < len(self.feature_names):
                        named_importance[self.feature_names[idx]] = value
                else:
                    named_importance[key] = value
            return named_importance

        return importance

    def get_hyperparameters(self) -> dict:
        """Get current hyperparameters."""
        return dict(self.params)
