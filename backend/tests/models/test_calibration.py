"""Tests for confidence calibration module."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.models.calibration import (
    CalibrationMethod,
    ConfidenceCalibrator,
    _expected_calibration_error,
)


def _make_synthetic_data(n_samples=300, n_classes=3, seed=42):
    """Create synthetic probabilities and labels for testing."""
    rng = np.random.RandomState(seed)
    y_true = rng.randint(0, n_classes, n_samples)

    # Generate raw probabilities (slightly overconfident)
    y_proba = rng.dirichlet(np.ones(n_classes) * 0.5, n_samples)

    # Bias toward correct class to simulate a somewhat-trained model
    for i in range(n_samples):
        y_proba[i, y_true[i]] += 0.3
    # Re-normalize
    y_proba = y_proba / y_proba.sum(axis=1, keepdims=True)

    return y_true, y_proba


class TestConfidenceCalibrator:
    def test_fit_isotonic(self):
        y_true, y_proba = _make_synthetic_data()
        cal = ConfidenceCalibrator(n_classes=3, method=CalibrationMethod.ISOTONIC)
        stats = cal.fit(y_true, y_proba)

        assert cal.is_fitted
        assert "ece_before" in stats
        assert "ece_after" in stats
        assert stats["ece_before"] >= 0
        assert stats["ece_after"] >= 0

    def test_fit_sigmoid(self):
        y_true, y_proba = _make_synthetic_data()
        cal = ConfidenceCalibrator(n_classes=3, method=CalibrationMethod.SIGMOID)
        stats = cal.fit(y_true, y_proba)

        assert cal.is_fitted
        assert stats["ece_after"] >= 0

    def test_transform_shape(self):
        y_true, y_proba = _make_synthetic_data()
        cal = ConfidenceCalibrator(n_classes=3)
        cal.fit(y_true, y_proba)

        calibrated = cal.transform(y_proba)
        assert calibrated.shape == y_proba.shape

    def test_transform_sums_to_one(self):
        y_true, y_proba = _make_synthetic_data()
        cal = ConfidenceCalibrator(n_classes=3)
        cal.fit(y_true, y_proba)

        calibrated = cal.transform(y_proba)
        row_sums = calibrated.sum(axis=1)
        np.testing.assert_allclose(row_sums, 1.0, atol=1e-6)

    def test_transform_probabilities_valid(self):
        y_true, y_proba = _make_synthetic_data()
        cal = ConfidenceCalibrator(n_classes=3)
        cal.fit(y_true, y_proba)

        calibrated = cal.transform(y_proba)
        assert np.all(calibrated >= 0)
        assert np.all(calibrated <= 1)

    def test_transform_not_fitted_raises(self):
        cal = ConfidenceCalibrator(n_classes=3)
        y_proba = np.array([[0.3, 0.4, 0.3]])
        with pytest.raises(RuntimeError, match="not fitted"):
            cal.transform(y_proba)

    def test_fit_wrong_n_classes_raises(self):
        y_true, y_proba = _make_synthetic_data(n_classes=3)
        cal = ConfidenceCalibrator(n_classes=5)
        with pytest.raises(ValueError, match="Expected 5"):
            cal.fit(y_true, y_proba)

    def test_save_and_load(self):
        y_true, y_proba = _make_synthetic_data()
        cal = ConfidenceCalibrator(n_classes=3, method=CalibrationMethod.ISOTONIC)
        cal.fit(y_true, y_proba)

        original_output = cal.transform(y_proba[:5])

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "cal"
            cal.save(save_path)

            cal2 = ConfidenceCalibrator()
            cal2.load(save_path)

            assert cal2.is_fitted
            assert cal2.n_classes == 3
            assert cal2.method == CalibrationMethod.ISOTONIC

            loaded_output = cal2.transform(y_proba[:5])
            np.testing.assert_allclose(original_output, loaded_output, atol=1e-10)

    def test_single_sample_transform(self):
        y_true, y_proba = _make_synthetic_data()
        cal = ConfidenceCalibrator(n_classes=3)
        cal.fit(y_true, y_proba)

        single = y_proba[:1]
        result = cal.transform(single)
        assert result.shape == (1, 3)
        assert abs(result.sum() - 1.0) < 1e-6


class TestECE:
    def test_perfect_calibration(self):
        """Perfect predictions should have low ECE."""
        y_true = np.array([0, 1, 2, 0, 1, 2])
        y_proba = np.array([
            [0.9, 0.05, 0.05],
            [0.05, 0.9, 0.05],
            [0.05, 0.05, 0.9],
            [0.9, 0.05, 0.05],
            [0.05, 0.9, 0.05],
            [0.05, 0.05, 0.9],
        ])
        ece = _expected_calibration_error(y_true, y_proba, n_bins=10)
        assert ece < 0.15  # Should be low for correct confident predictions

    def test_bad_calibration_high_ece(self):
        """Overconfident wrong predictions should have high ECE."""
        y_true = np.array([0, 0, 0, 0, 0])
        y_proba = np.array([
            [0.1, 0.8, 0.1],  # Wrong, confident
            [0.1, 0.8, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.8, 0.1],
        ])
        ece = _expected_calibration_error(y_true, y_proba, n_bins=10)
        assert ece > 0.5  # Should be high

    def test_ece_bounded(self):
        """ECE should always be between 0 and 1."""
        rng = np.random.RandomState(42)
        y_true = rng.randint(0, 3, 100)
        y_proba = rng.dirichlet(np.ones(3), 100)
        ece = _expected_calibration_error(y_true, y_proba)
        assert 0.0 <= ece <= 1.0
