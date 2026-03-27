"""
Ensemble stacking classifier for multi-model prediction.
Combines LSTM + TFT + XGBoost with a meta-learner (XGBoost).

Architecture:
1. Base models (Level 0): LSTM, TFT, XGBoost
   - Each trained independently on full training data
2. Meta-learner (Level 1): XGBoost
   - Trained on stacked predictions from base models (on validation set)
   - Learns how to combine base model outputs optimally
"""

from pathlib import Path

import numpy as np
from loguru import logger

from src.models.base_model import BaseMLModel
from src.models.lstm_model import LSTMClassifier
from src.models.tft_model import TFTClassifier
from src.models.xgboost_model import XGBoostClassifier


class EnsembleClassifier(BaseMLModel):
    """
    Stacking ensemble: LSTM + TFT + XGBoost → Meta-learner XGBoost.

    The meta-learner is trained on out-of-fold predictions from base models,
    learning to weight each model's predictions optimally.
    """

    @property
    def model_type(self) -> str:
        return "ensemble"

    @property
    def is_fitted(self) -> bool:
        return (
            self.meta_learner is not None
            and self.meta_learner.is_fitted
            and len(self.base_models) > 0
        )

    def __init__(
        self,
        base_models: dict[str, BaseMLModel] | None = None,
        meta_learner: XGBoostClassifier | None = None,
    ):
        """
        Initialize ensemble classifier.

        Args:
            base_models: Dictionary of base models {"lstm": LSTMClassifier, "tft": TFTClassifier, "xgboost": XGBoostClassifier}
            meta_learner: Meta-learner model (XGBoostClassifier)
        """
        self.base_models = base_models or {}
        self.meta_learner = meta_learner

    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> dict:
        """
        Train ensemble using stacking strategy.

        Training procedure:
        1. Train each base model independently on training data
        2. Generate predictions on validation set
        3. Stack predictions as features for meta-learner
        4. Train meta-learner on stacked predictions

        Args:
            X_train: Training features
            y_train: Training labels (-1, 0, 1)
            X_val: Validation features (required for stacking)
            y_val: Validation labels (required for stacking)

        Returns:
            Training metrics
        """
        if X_val is None or y_val is None:
            raise ValueError("Ensemble requires validation set for stacking")

        logger.info("Training ensemble with stacking strategy...")

        # Step 1: Train each base model independently
        for name, model in self.base_models.items():
            logger.info(f"Training base model: {name}")
            model.fit(X_train, y_train, X_val, y_val)

        # Step 2: Generate stacked predictions on validation set
        logger.info("Generating stacked predictions on validation set...")
        stacked_features = self._stack_predictions(X_val)

        # Step 3: Train meta-learner on stacked predictions
        logger.info("Training meta-learner...")
        self.meta_learner = XGBoostClassifier()
        meta_results = self.meta_learner.fit(stacked_features, y_val)

        # Evaluate ensemble on validation set
        ensemble_acc = self._evaluate_accuracy(X_val, y_val)

        logger.success(
            f"Ensemble training complete - Meta F1: {meta_results.get('f1_macro', 0.0):.4f}, "
            f"Ensemble Accuracy: {ensemble_acc:.4f}"
        )

        return {
            "meta_f1": meta_results.get("f1_macro", 0.0),
            "ensemble_accuracy": ensemble_acc,
            "base_models": list(self.base_models.keys()),
        }

    def _stack_predictions(self, X: np.ndarray) -> np.ndarray:
        """
        Stack predictions from all base models into feature matrix.

        For each base model, we get probability predictions (n_samples, 3).
        We concatenate all predictions horizontally to create stacked features.

        Args:
            X: Input features

        Returns:
            Stacked predictions of shape (n_samples, 3 * n_base_models)
        """
        stacked = []
        for name, model in self.base_models.items():
            logger.debug(f"Generating predictions from {name}...")
            proba = model.predict_proba(X)  # (n_samples, 3)
            stacked.append(proba)

        # Concatenate horizontally: (n_samples, 3) + (n_samples, 3) + ... → (n_samples, 3*n)
        stacked_features = np.hstack(stacked)
        logger.debug(
            f"Stacked features shape: {stacked_features.shape} "
            f"({len(self.base_models)} models × 3 classes)"
        )
        return stacked_features

    def _evaluate_accuracy(self, X: np.ndarray, y: np.ndarray) -> float:
        """Evaluate ensemble accuracy on given data."""
        predictions = self.predict(X)
        accuracy = (predictions == y).mean()
        return accuracy

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class probabilities using ensemble.

        Args:
            X: Input features

        Returns:
            Probabilities of shape (n_samples, 3)
        """
        if not self.is_fitted:
            raise ValueError("Ensemble not fitted yet")

        # Generate stacked predictions from base models
        stacked = self._stack_predictions(X)

        # Use meta-learner to combine predictions
        return self.meta_learner.predict_proba(stacked)

    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class labels using ensemble.

        Args:
            X: Input features

        Returns:
            Predicted labels (-1, 0, 1)
        """
        proba = self.predict_proba(X)
        predictions = np.argmax(proba, axis=1)
        # Map {0, 1, 2} back to {-1, 0, 1}
        return predictions - 1

    def save(self, path: Path) -> None:
        """
        Save ensemble to disk.

        Saves each base model in its own subdirectory:
        - ensemble/lstm/
        - ensemble/tft/
        - ensemble/xgboost/
        - ensemble/meta/
        """
        if not self.is_fitted:
            raise ValueError("No ensemble to save")

        path.mkdir(parents=True, exist_ok=True)

        # Save each base model
        for name, model in self.base_models.items():
            model_dir = path / name
            logger.debug(f"Saving base model: {name} to {model_dir}")
            model.save(model_dir)

        # Save meta-learner
        meta_dir = path / "meta"
        logger.debug(f"Saving meta-learner to {meta_dir}")
        self.meta_learner.save(meta_dir)

        logger.info(f"Ensemble saved to {path} ({len(self.base_models)} base models + meta)")

    def load(self, path: Path) -> None:
        """
        Load ensemble from disk.

        Loads all base models and meta-learner from their respective subdirectories.
        """
        logger.info(f"Loading ensemble from {path}...")

        # Load base models
        self.base_models = {}
        for name in ["lstm", "tft", "xgboost"]:
            model_dir = path / name
            if not model_dir.exists():
                logger.warning(f"Base model directory not found: {model_dir}, skipping")
                continue

            # Instantiate appropriate model class
            if name == "lstm":
                model = LSTMClassifier()
            elif name == "tft":
                model = TFTClassifier()
            elif name == "xgboost":
                model = XGBoostClassifier()
            else:
                logger.warning(f"Unknown model type: {name}, skipping")
                continue

            # Load model weights
            try:
                model.load(model_dir)
                self.base_models[name] = model
                logger.debug(f"Loaded base model: {name}")
            except Exception as e:
                logger.error(f"Failed to load {name}: {e}")

        # Load meta-learner
        meta_dir = path / "meta"
        if not meta_dir.exists():
            raise FileNotFoundError(f"Meta-learner directory not found: {meta_dir}")

        self.meta_learner = XGBoostClassifier()
        self.meta_learner.load(meta_dir)
        logger.debug("Loaded meta-learner")

        logger.success(f"Ensemble loaded from {path} ({len(self.base_models)} base models + meta)")

    def get_feature_importance(self) -> dict[str, float]:
        """
        Get feature importance from meta-learner.

        The meta-learner's feature importance shows how much weight
        each base model's predictions contribute to the final decision.

        Returns:
            Dictionary mapping feature names to importance scores
        """
        if self.meta_learner is None:
            return {}

        # Get raw importance from meta-learner
        meta_importance = self.meta_learner.get_feature_importance()

        # Map stacked feature indices back to base model names
        # Stacked features: [lstm_0, lstm_1, lstm_2, tft_0, tft_1, tft_2, xgb_0, xgb_1, xgb_2]
        importance_by_model = {}
        model_names = list(self.base_models.keys())

        for idx, (_feat_name, score) in enumerate(meta_importance.items()):
            model_idx = idx // 3  # Each model contributes 3 features (proba for 3 classes)
            if model_idx < len(model_names):
                model_name = model_names[model_idx]
                if model_name not in importance_by_model:
                    importance_by_model[model_name] = 0.0
                importance_by_model[model_name] += score

        logger.debug(f"Base model importance: {importance_by_model}")
        return importance_by_model
