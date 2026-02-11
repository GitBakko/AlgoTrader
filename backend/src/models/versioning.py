"""
Model versioning and persistence.
Handles saving/loading models with metadata, and model comparison.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from loguru import logger

from src.models.base_model import BaseMLModel
from src.models.evaluator import ModelEvaluator
from src.models.schemas import ModelMetadata, TrainingResult
from src.utils.config import get_settings


class ModelVersioning:
    """
    Manages model persistence and versioning.

    Directory structure:
    data/models/{epic}/{model_id}/
        model.json      (or model weights)
        params.json     (hyperparameters)
        metadata.json   (ModelMetadata)
    """

    def __init__(self, base_dir: str | None = None):
        """
        Args:
            base_dir: Base directory for model storage (default: settings.model_dir)
        """
        self.base_dir = Path(base_dir or get_settings().model_dir)

    def save_model(
        self,
        model: BaseMLModel,
        metadata: ModelMetadata,
    ) -> Path:
        """
        Save a model with its metadata.

        Args:
            model: Trained model to save
            metadata: Model metadata

        Returns:
            Path to saved model directory
        """
        model_dir = self.base_dir / metadata.epic / metadata.model_id
        model_dir.mkdir(parents=True, exist_ok=True)

        # Save model weights
        model.save(model_dir)

        # Save metadata
        meta_path = model_dir / "metadata.json"
        meta_path.write_text(metadata.model_dump_json(indent=2))

        logger.info(f"Model saved: {metadata.model_id} -> {model_dir}")
        return model_dir

    def load_model(
        self,
        model_class: type[BaseMLModel],
        epic: str,
        model_id: str,
    ) -> tuple[BaseMLModel, ModelMetadata]:
        """
        Load a model and its metadata.

        Args:
            model_class: Class of the model to instantiate
            epic: Asset epic
            model_id: Model identifier

        Returns:
            Tuple of (model instance, metadata)
        """
        model_dir = self.base_dir / epic / model_id

        if not model_dir.exists():
            raise FileNotFoundError(f"Model not found: {model_dir}")

        # Load metadata
        meta_path = model_dir / "metadata.json"
        if not meta_path.exists():
            raise FileNotFoundError(f"Metadata not found: {meta_path}")

        metadata = ModelMetadata.model_validate_json(meta_path.read_text())

        # Instantiate and load model
        model = model_class()
        model.load(model_dir)

        logger.info(f"Model loaded: {model_id} from {model_dir}")
        return model, metadata

    def list_models(self, epic: str | None = None) -> list[ModelMetadata]:
        """
        List all saved models, optionally filtered by asset.

        Args:
            epic: Filter by asset epic (None for all)

        Returns:
            List of ModelMetadata objects
        """
        models = []

        if epic:
            search_dirs = [self.base_dir / epic]
        else:
            search_dirs = [d for d in self.base_dir.iterdir() if d.is_dir()]

        for epic_dir in search_dirs:
            if not epic_dir.exists():
                continue

            for model_dir in epic_dir.iterdir():
                if not model_dir.is_dir():
                    continue

                meta_path = model_dir / "metadata.json"
                if meta_path.exists():
                    try:
                        metadata = ModelMetadata.model_validate_json(meta_path.read_text())
                        models.append(metadata)
                    except Exception as e:
                        logger.warning(f"Failed to load metadata from {meta_path}: {e}")

        return sorted(models, key=lambda m: m.created_at, reverse=True)

    def compare_models(
        self,
        model_a: BaseMLModel,
        model_b: BaseMLModel,
        X_test: np.ndarray,
        y_test: np.ndarray,
    ) -> dict:
        """
        Compare two models on the same test set.

        Args:
            model_a: First model
            model_b: Second model
            X_test: Test features
            y_test: Test labels

        Returns:
            Dict with metrics for both models and comparison
        """
        evaluator = ModelEvaluator()

        # Evaluate model A
        y_pred_a = model_a.predict(X_test)
        y_proba_a = model_a.predict_proba(X_test)
        metrics_a = evaluator.evaluate(y_test, y_pred_a, y_proba_a)

        # Evaluate model B
        y_pred_b = model_b.predict(X_test)
        y_proba_b = model_b.predict_proba(X_test)
        metrics_b = evaluator.evaluate(y_test, y_pred_b, y_proba_b)

        return {
            "model_a": {
                "type": model_a.model_type,
                "metrics": metrics_a,
            },
            "model_b": {
                "type": model_b.model_type,
                "metrics": metrics_b,
            },
            "comparison": {
                "accuracy_diff": metrics_a["accuracy"] - metrics_b["accuracy"],
                "f1_macro_diff": metrics_a["f1_macro"] - metrics_b["f1_macro"],
                "better_model": "A" if metrics_a["f1_macro"] > metrics_b["f1_macro"] else "B",
            },
        }

    @staticmethod
    def generate_model_id(model_type: str, epic: str) -> str:
        """Generate a unique model ID based on type, asset, and timestamp."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{model_type}_{epic}_{ts}"
