"""Tests for XGBoostTuner (Optuna-based hyperparameter tuning)."""

import numpy as np
import pytest

from src.models.tuner import XGBoostTuner


@pytest.fixture
def synthetic_data():
    """Create synthetic 3-class classification data."""
    rng = np.random.RandomState(42)
    n_train, n_val = 500, 150
    n_features = 20

    X_train = rng.randn(n_train, n_features)
    X_val = rng.randn(n_val, n_features)

    # Make targets weakly correlated with first 3 features
    scores = X_train[:, 0] + 0.5 * X_train[:, 1] - 0.3 * X_train[:, 2]
    y_train = np.digitize(scores, bins=[-0.5, 0.5]).astype(np.int32)

    scores_val = X_val[:, 0] + 0.5 * X_val[:, 1] - 0.3 * X_val[:, 2]
    y_val = np.digitize(scores_val, bins=[-0.5, 0.5]).astype(np.int32)

    return X_train, y_train, X_val, y_val


def test_tuner_returns_params(synthetic_data):
    """Tuner should return a dict with expected XGBoost parameter keys."""
    X_train, y_train, X_val, y_val = synthetic_data

    tuner = XGBoostTuner(n_trials=5, timeout_seconds=60)
    result = tuner.tune(X_train, y_train, X_val, y_val)

    assert isinstance(result, dict)
    expected_keys = {
        "max_depth", "learning_rate", "n_estimators",
        "subsample", "colsample_bytree", "min_child_weight",
        "reg_alpha", "reg_lambda", "gamma",
    }
    assert expected_keys == set(result.keys())


def test_tuner_param_ranges(synthetic_data):
    """Best params should be within the search space."""
    X_train, y_train, X_val, y_val = synthetic_data

    tuner = XGBoostTuner(n_trials=5, timeout_seconds=60)
    result = tuner.tune(X_train, y_train, X_val, y_val)

    assert 3 <= result["max_depth"] <= 5
    assert 0.01 <= result["learning_rate"] <= 0.1
    assert 500 <= result["n_estimators"] <= 1500
    assert 0.5 <= result["subsample"] <= 0.8
    assert 0.4 <= result["colsample_bytree"] <= 0.7
    assert 10 <= result["min_child_weight"] <= 50
    assert 0.5 <= result["reg_alpha"] <= 10.0
    assert 3.0 <= result["reg_lambda"] <= 15.0
    assert 0.1 <= result["gamma"] <= 2.0


def test_tuner_respects_timeout():
    """Tuner should respect timeout setting."""
    rng = np.random.RandomState(42)
    X = rng.randn(200, 10)
    y = rng.randint(0, 3, 200).astype(np.int32)

    tuner = XGBoostTuner(n_trials=1000, timeout_seconds=5)
    result = tuner.tune(X, y, X[:50], y[:50])

    # Should return params even with timeout
    assert isinstance(result, dict)
    assert "max_depth" in result
