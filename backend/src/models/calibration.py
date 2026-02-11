"""
Post-hoc confidence calibration for ML model probabilities.

Uses isotonic regression or Platt scaling (sigmoid) to map raw
model probabilities to better-calibrated confidence scores.

Workflow:
  1. Train base model on training set
  2. Get raw probabilities on a held-out calibration set
  3. Fit calibrator on (raw_proba, true_labels)
  4. At inference: raw_proba -> calibrated_proba
"""

import json
from enum import Enum
from pathlib import Path

import numpy as np
from loguru import logger
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


class CalibrationMethod(str, Enum):
    ISOTONIC = "isotonic"
    SIGMOID = "sigmoid"  # Platt scaling


class ConfidenceCalibrator:
    """
    Per-class probability calibration using isotonic regression or Platt scaling.

    Fits one calibrator per class on held-out validation probabilities,
    then transforms raw probabilities at inference time and re-normalizes.
    """

    def __init__(
        self,
        n_classes: int = 3,
        method: CalibrationMethod = CalibrationMethod.ISOTONIC,
    ):
        self.n_classes = n_classes
        self.method = method
        self._calibrators: list = []
        self._fitted = False

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def fit(self, y_true: np.ndarray, y_proba: np.ndarray) -> dict:
        """
        Fit calibration mapping from raw probabilities to calibrated ones.

        Args:
            y_true: True labels (n_samples,) with values in [0, n_classes)
            y_proba: Raw model probabilities (n_samples, n_classes)

        Returns:
            Dict with calibration statistics
        """
        if y_proba.shape[1] != self.n_classes:
            raise ValueError(
                f"Expected {self.n_classes} probability columns, got {y_proba.shape[1]}"
            )

        self._calibrators = []

        for cls in range(self.n_classes):
            # Binary indicator: is this sample class `cls`?
            y_binary = (y_true == cls).astype(np.float64)
            p_raw = y_proba[:, cls]

            if self.method == CalibrationMethod.ISOTONIC:
                cal = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
                cal.fit(p_raw, y_binary)
            else:
                # Platt scaling: logistic regression on raw probabilities
                cal = LogisticRegression(C=1.0, solver="lbfgs", max_iter=1000)
                cal.fit(p_raw.reshape(-1, 1), y_binary)

            self._calibrators.append(cal)

        self._fitted = True

        # Compute calibration statistics
        calibrated = self.transform(y_proba)
        stats = self._compute_stats(y_true, y_proba, calibrated)
        logger.info(
            f"Calibration fitted ({self.method.value}): "
            f"ECE {stats['ece_before']:.4f} -> {stats['ece_after']:.4f}"
        )
        return stats

    def transform(self, y_proba: np.ndarray) -> np.ndarray:
        """
        Transform raw probabilities to calibrated probabilities.

        Args:
            y_proba: Raw probabilities (n_samples, n_classes)

        Returns:
            Calibrated probabilities (n_samples, n_classes), normalized to sum=1
        """
        if not self._fitted:
            raise RuntimeError("Calibrator not fitted. Call fit() first.")

        n_samples = y_proba.shape[0]
        calibrated = np.zeros_like(y_proba)

        for cls in range(self.n_classes):
            p_raw = y_proba[:, cls]
            cal = self._calibrators[cls]

            if self.method == CalibrationMethod.ISOTONIC:
                calibrated[:, cls] = cal.predict(p_raw)
            else:
                calibrated[:, cls] = cal.predict_proba(p_raw.reshape(-1, 1))[:, 1]

        # Re-normalize rows to sum to 1
        row_sums = calibrated.sum(axis=1, keepdims=True)
        row_sums = np.maximum(row_sums, 1e-10)  # Avoid division by zero
        calibrated = calibrated / row_sums

        return calibrated

    def save(self, path: Path) -> None:
        """Save calibrator to disk."""
        import joblib

        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save calibrators
        for i, cal in enumerate(self._calibrators):
            joblib.dump(cal, path / f"calibrator_class_{i}.joblib")

        # Save metadata
        meta = {
            "n_classes": self.n_classes,
            "method": self.method.value,
            "fitted": self._fitted,
        }
        (path / "calibration_meta.json").write_text(json.dumps(meta, indent=2))

    def load(self, path: Path) -> None:
        """Load calibrator from disk."""
        import joblib

        path = Path(path)

        meta = json.loads((path / "calibration_meta.json").read_text())
        self.n_classes = meta["n_classes"]
        self.method = CalibrationMethod(meta["method"])

        self._calibrators = []
        for i in range(self.n_classes):
            cal = joblib.load(path / f"calibrator_class_{i}.joblib")
            self._calibrators.append(cal)

        self._fitted = meta["fitted"]

    @staticmethod
    def _compute_stats(
        y_true: np.ndarray,
        raw_proba: np.ndarray,
        calibrated_proba: np.ndarray,
        n_bins: int = 10,
    ) -> dict:
        """Compute Expected Calibration Error (ECE) before and after."""
        ece_before = _expected_calibration_error(y_true, raw_proba, n_bins)
        ece_after = _expected_calibration_error(y_true, calibrated_proba, n_bins)

        # Average confidence shift
        raw_max = raw_proba.max(axis=1).mean()
        cal_max = calibrated_proba.max(axis=1).mean()

        return {
            "ece_before": float(ece_before),
            "ece_after": float(ece_after),
            "ece_improvement": float(ece_before - ece_after),
            "avg_raw_confidence": float(raw_max),
            "avg_calibrated_confidence": float(cal_max),
            "method": "isotonic" if isinstance(
                calibrated_proba, np.ndarray
            ) else "sigmoid",
        }


def _expected_calibration_error(
    y_true: np.ndarray, y_proba: np.ndarray, n_bins: int = 10
) -> float:
    """
    Compute multi-class Expected Calibration Error (ECE).

    ECE measures the gap between predicted confidence and actual accuracy.
    Lower is better (0 = perfectly calibrated).
    """
    predicted_class = np.argmax(y_proba, axis=1)
    confidences = y_proba[np.arange(len(y_true)), predicted_class]
    accuracies = (predicted_class == y_true).astype(float)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    total = len(y_true)

    for i in range(n_bins):
        lo, hi = bin_boundaries[i], bin_boundaries[i + 1]
        mask = (confidences > lo) & (confidences <= hi)
        n_in_bin = mask.sum()

        if n_in_bin == 0:
            continue

        avg_confidence = confidences[mask].mean()
        avg_accuracy = accuracies[mask].mean()
        ece += (n_in_bin / total) * abs(avg_accuracy - avg_confidence)

    return ece
