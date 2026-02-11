"""
Abstract base class for all ML models in AlgoTrader AI.
Defines the interface that all models must implement.
"""

from abc import ABC, abstractmethod
from pathlib import Path

import numpy as np

from src.models.schemas import PredictionResult


class BaseMLModel(ABC):
    """
    Abstract base class for ML models.

    All models must implement:
    - fit: Train the model
    - predict: Get class predictions
    - predict_proba: Get class probabilities
    - save / load: Persistence
    - get_feature_importance: Feature ranking
    """

    @property
    @abstractmethod
    def model_type(self) -> str:
        """Return model type identifier (e.g., 'xgboost', 'lstm')."""
        ...

    @property
    @abstractmethod
    def is_fitted(self) -> bool:
        """Whether the model has been trained."""
        ...

    @abstractmethod
    def fit(
        self,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_val: np.ndarray | None = None,
        y_val: np.ndarray | None = None,
    ) -> dict:
        """
        Train the model.

        Args:
            X_train: Training features (n_samples, n_features)
            y_train: Training labels (n_samples,)
            X_val: Validation features (optional, for early stopping)
            y_val: Validation labels (optional)

        Returns:
            Dict with training info (e.g., best_iteration, train_loss)
        """
        ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class labels.

        Args:
            X: Features (n_samples, n_features)

        Returns:
            Array of predicted class labels
        """
        ...

    @abstractmethod
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Predict class probabilities.

        Args:
            X: Features (n_samples, n_features)

        Returns:
            Array of shape (n_samples, n_classes) with probabilities
        """
        ...

    def predict_single(self, X: np.ndarray) -> PredictionResult:
        """
        Predict for a single sample and return a PredictionResult.

        Args:
            X: Features (1, n_features) or (n_features,)

        Returns:
            PredictionResult with signal class, confidence, and probabilities
        """
        from src.models.schemas import SIGNAL_CLASS_NAMES, SignalClass

        if X.ndim == 1:
            X = X.reshape(1, -1)

        proba = self.predict_proba(X)[0]
        pred_class = int(np.argmax(proba))
        confidence = float(proba[pred_class])

        prob_dict = {}
        for cls in SignalClass:
            if cls.value < len(proba):
                prob_dict[SIGNAL_CLASS_NAMES[cls]] = float(proba[cls.value])

        return PredictionResult(
            signal_class=pred_class,
            signal_name=SIGNAL_CLASS_NAMES.get(SignalClass(pred_class), f"CLASS_{pred_class}"),
            confidence=confidence,
            probabilities=prob_dict,
        )

    @abstractmethod
    def save(self, path: Path) -> None:
        """Save model to disk."""
        ...

    @abstractmethod
    def load(self, path: Path) -> None:
        """Load model from disk."""
        ...

    @abstractmethod
    def get_feature_importance(self) -> dict[str, float]:
        """
        Get feature importance scores.

        Returns:
            Dict mapping feature name to importance score
        """
        ...
