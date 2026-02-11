"""Tests for XGBoost model."""

import numpy as np
import pytest

from src.models.schemas import SignalClass
from src.models.xgboost_model import XGBoostClassifier


@pytest.fixture
def synthetic_data():
    """Generate synthetic 3-class classification data."""
    np.random.seed(42)
    n_train = 500
    n_test = 100
    n_features = 10

    X_train = np.random.randn(n_train, n_features)
    X_test = np.random.randn(n_test, n_features)

    # Create 3-class labels based on a simple rule for testability
    y_train = np.where(
        X_train[:, 0] > 0.3, SignalClass.BUY,
        np.where(
            X_train[:, 0] < -0.3, SignalClass.SELL,
            SignalClass.HOLD
        )
    ).astype(np.int32)

    y_test = np.where(
        X_test[:, 0] > 0.3, SignalClass.BUY,
        np.where(
            X_test[:, 0] < -0.3, SignalClass.SELL,
            SignalClass.HOLD
        )
    ).astype(np.int32)

    return X_train, y_train, X_test, y_test


class TestXGBoostClassifier:
    def test_fit_predict(self, synthetic_data):
        X_train, y_train, X_test, y_test = synthetic_data
        model = XGBoostClassifier(n_estimators=50, max_depth=3)
        model.fit(X_train, y_train)

        assert model.is_fitted

        preds = model.predict(X_test)
        assert len(preds) == len(X_test)
        assert all(p in range(3) for p in preds)

    def test_predict_proba(self, synthetic_data):
        X_train, y_train, X_test, _ = synthetic_data
        model = XGBoostClassifier(n_estimators=50, max_depth=3)
        model.fit(X_train, y_train)

        proba = model.predict_proba(X_test)
        assert proba.shape == (len(X_test), 3)
        # Each row should sum to ~1
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-5)

    def test_predict_single(self, synthetic_data):
        X_train, y_train, X_test, _ = synthetic_data
        model = XGBoostClassifier(n_estimators=50, max_depth=3)
        model.fit(X_train, y_train)

        result = model.predict_single(X_test[0])
        assert result.signal_class in range(3)
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.probabilities) == 3

    def test_not_fitted_raises(self):
        model = XGBoostClassifier()
        with pytest.raises(RuntimeError, match="not fitted"):
            model.predict(np.array([[1, 2, 3]]))

    def test_fit_with_validation(self, synthetic_data):
        X_train, y_train, X_test, y_test = synthetic_data
        model = XGBoostClassifier(n_estimators=100, early_stopping_rounds=10)
        info = model.fit(X_train, y_train, X_test, y_test)
        assert "n_estimators_used" in info

    def test_save_and_load(self, synthetic_data, tmp_path):
        X_train, y_train, X_test, _ = synthetic_data
        model = XGBoostClassifier(n_estimators=50, max_depth=3)
        model.fit(X_train, y_train)

        # Save
        save_path = tmp_path / "test_model"
        model.save(save_path)
        assert (save_path / "model.json").exists()
        assert (save_path / "params.json").exists()

        # Load
        model2 = XGBoostClassifier()
        model2.load(save_path)
        assert model2.is_fitted

        # Predictions should match
        preds1 = model.predict(X_test)
        preds2 = model2.predict(X_test)
        np.testing.assert_array_equal(preds1, preds2)

    def test_feature_importance(self, synthetic_data):
        X_train, y_train, _, _ = synthetic_data
        model = XGBoostClassifier(
            n_estimators=50, max_depth=3,
            feature_names=[f"feat_{i}" for i in range(10)]
        )
        model.fit(X_train, y_train)

        importance = model.get_feature_importance()
        assert isinstance(importance, dict)
        assert len(importance) > 0

    def test_model_type(self):
        model = XGBoostClassifier()
        assert model.model_type == "xgboost"

    def test_accuracy_above_random(self, synthetic_data):
        """Model should beat random baseline (33% for 3 classes)."""
        X_train, y_train, X_test, y_test = synthetic_data
        model = XGBoostClassifier(n_estimators=100, max_depth=4)
        model.fit(X_train, y_train)

        preds = model.predict(X_test)
        accuracy = (preds == y_test).mean()
        assert accuracy > 0.45  # Should beat random (33%) by a good margin
