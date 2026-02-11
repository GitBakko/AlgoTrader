"""
Model evaluation module.
Computes classification metrics for multi-class signal prediction.
"""

import numpy as np
from loguru import logger
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)

from src.models.schemas import SIGNAL_CLASS_NAMES, SignalClass


class ModelEvaluator:
    """
    Evaluates ML model predictions against true labels.
    Computes accuracy, precision, recall, F1 (macro + per-class),
    confusion matrix, and classification report.
    """

    @staticmethod
    def evaluate(
        y_true: np.ndarray,
        y_pred: np.ndarray,
        y_proba: np.ndarray | None = None,
    ) -> dict:
        """
        Compute all evaluation metrics.

        Args:
            y_true: True labels
            y_pred: Predicted labels
            y_proba: Predicted probabilities (optional, for log loss)

        Returns:
            Dict with all metrics
        """
        labels = list(range(len(SignalClass)))
        target_names = [SIGNAL_CLASS_NAMES[SignalClass(i)] for i in labels]

        metrics = {
            "accuracy": float(accuracy_score(y_true, y_pred)),
            "f1_macro": float(f1_score(y_true, y_pred, average="macro", zero_division=0)),
            "f1_weighted": float(f1_score(y_true, y_pred, average="weighted", zero_division=0)),
            "precision_macro": float(
                precision_score(y_true, y_pred, average="macro", zero_division=0)
            ),
            "recall_macro": float(
                recall_score(y_true, y_pred, average="macro", zero_division=0)
            ),
        }

        # Per-class F1
        f1_per_class = f1_score(
            y_true, y_pred, average=None, labels=labels, zero_division=0
        )
        for i, f1 in enumerate(f1_per_class):
            metrics[f"f1_{target_names[i]}"] = float(f1)

        # Confusion matrix
        cm = confusion_matrix(y_true, y_pred, labels=labels)
        metrics["confusion_matrix"] = cm.tolist()

        # Classification report (as dict)
        report = classification_report(
            y_true, y_pred, labels=labels, target_names=target_names,
            output_dict=True, zero_division=0,
        )
        metrics["classification_report"] = report

        # Log loss if probabilities available
        if y_proba is not None:
            from sklearn.metrics import log_loss

            try:
                metrics["log_loss"] = float(
                    log_loss(y_true, y_proba, labels=labels)
                )
            except ValueError as e:
                logger.warning(f"Log loss computation failed: {e}")

        return metrics

    @staticmethod
    def summarize(metrics: dict) -> str:
        """
        Create a human-readable summary of metrics.

        Args:
            metrics: Dict from evaluate()

        Returns:
            Formatted string summary
        """
        lines = [
            f"Accuracy:         {metrics['accuracy']:.4f}",
            f"F1 (macro):       {metrics['f1_macro']:.4f}",
            f"F1 (weighted):    {metrics['f1_weighted']:.4f}",
            f"Precision (macro): {metrics['precision_macro']:.4f}",
            f"Recall (macro):   {metrics['recall_macro']:.4f}",
        ]

        if "log_loss" in metrics:
            lines.append(f"Log Loss:         {metrics['log_loss']:.4f}")

        # Per-class F1
        lines.append("\nPer-class F1:")
        for cls in SignalClass:
            key = f"f1_{SIGNAL_CLASS_NAMES[cls]}"
            if key in metrics:
                lines.append(f"  {SIGNAL_CLASS_NAMES[cls]:12s}: {metrics[key]:.4f}")

        return "\n".join(lines)
