"""Tests for LSTM classifier model."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from src.models.lstm_model import LSTMClassifier


def _make_synthetic_data(n_samples=200, n_features=10, n_classes=3, seed=42):
    """Create synthetic sequential data for testing."""
    rng = np.random.RandomState(seed)

    X = rng.randn(n_samples, n_features).astype(np.float32)
    # Simple linear relationship for labels
    scores = X[:, 0] + 0.5 * X[:, 1] - 0.3 * X[:, 2]
    y = np.digitize(scores, bins=[-0.5, 0.5]) .astype(np.int64)
    y = np.clip(y, 0, n_classes - 1)

    return X, y


class TestLSTMClassifier:
    def test_init(self):
        model = LSTMClassifier(seq_len=12, hidden_size=32)
        assert model.model_type == "lstm"
        assert model.is_fitted is False
        assert model.seq_len == 12
        assert model.hidden_size == 32

    def test_fit(self):
        X, y = _make_synthetic_data(n_samples=150, n_features=8)
        model = LSTMClassifier(
            seq_len=10, hidden_size=16, num_layers=1,
            max_epochs=3, batch_size=32,
        )

        train_info = model.fit(X[:100], y[:100], X[100:], y[100:])

        assert model.is_fitted
        assert "epochs_trained" in train_info
        assert train_info["epochs_trained"] > 0

    def test_predict(self):
        X, y = _make_synthetic_data(n_samples=150, n_features=8)
        model = LSTMClassifier(
            seq_len=10, hidden_size=16, num_layers=1,
            max_epochs=3, batch_size=32,
        )
        model.fit(X[:100], y[:100])

        preds = model.predict(X[100:])
        # Output has fewer samples due to sequence windowing
        expected_len = len(X[100:]) - model.seq_len + 1
        assert len(preds) == expected_len
        assert all(p in range(3) for p in preds)

    def test_predict_proba(self):
        X, y = _make_synthetic_data(n_samples=150, n_features=8)
        model = LSTMClassifier(
            seq_len=10, hidden_size=16, num_layers=1,
            max_epochs=3, batch_size=32,
        )
        model.fit(X[:100], y[:100])

        proba = model.predict_proba(X[100:])
        expected_len = len(X[100:]) - model.seq_len + 1
        assert proba.shape == (expected_len, 3)
        # Probabilities sum to 1
        np.testing.assert_allclose(proba.sum(axis=1), 1.0, atol=1e-5)
        # All non-negative
        assert np.all(proba >= 0)

    def test_predict_single(self):
        X, y = _make_synthetic_data(n_samples=100, n_features=8)
        model = LSTMClassifier(
            seq_len=10, hidden_size=16, num_layers=1,
            max_epochs=3, batch_size=32,
        )
        model.fit(X[:80], y[:80])

        # Pass a sequence window
        result = model.predict_single(X[80:90])  # shape (10, 8)
        assert result.signal_class in range(3)
        assert 0 < result.confidence <= 1.0
        assert len(result.probabilities) == 3

    def test_save_and_load(self):
        X, y = _make_synthetic_data(n_samples=100, n_features=8)
        model = LSTMClassifier(
            seq_len=10, hidden_size=16, num_layers=1,
            max_epochs=3, batch_size=32,
        )
        model.feature_names = [f"f_{i}" for i in range(8)]
        model.fit(X[:80], y[:80])

        original_proba = model.predict_proba(X[80:])

        with tempfile.TemporaryDirectory() as tmpdir:
            save_path = Path(tmpdir) / "lstm_test"
            model.save(save_path)

            model2 = LSTMClassifier()
            model2.load(save_path)

            assert model2.is_fitted
            assert model2.seq_len == 10
            assert model2.hidden_size == 16
            assert model2.feature_names == model.feature_names

            loaded_proba = model2.predict_proba(X[80:])
            np.testing.assert_allclose(original_proba, loaded_proba, atol=1e-5)

    def test_early_stopping(self):
        X, y = _make_synthetic_data(n_samples=200, n_features=8)
        model = LSTMClassifier(
            seq_len=10, hidden_size=16, num_layers=1,
            max_epochs=100, patience=3, batch_size=32,
        )

        info = model.fit(X[:140], y[:140], X[140:], y[140:])
        # Should train and return epoch count
        assert info["epochs_trained"] > 0
        assert info["epochs_trained"] <= 100
        assert info["best_val_loss"] is not None

    def test_create_sequences(self):
        model = LSTMClassifier(seq_len=5)
        X = np.arange(30).reshape(10, 3).astype(np.float32)
        y = np.array([0, 1, 2, 0, 1, 2, 0, 1, 2, 0])

        X_seq, y_seq = model._create_sequences(X, y)
        assert X_seq.shape == (6, 5, 3)  # 10 - 5 + 1 = 6 sequences
        assert y_seq.shape == (6,)
        # y_seq should start from index 4 (seq_len - 1)
        np.testing.assert_array_equal(y_seq, y[4:])

    def test_not_fitted_raises(self):
        model = LSTMClassifier(seq_len=5)
        X = np.random.randn(20, 5).astype(np.float32)
        with pytest.raises(RuntimeError, match="not fitted"):
            model.predict_proba(X)

    def test_too_few_samples_raises(self):
        model = LSTMClassifier(seq_len=50)
        X = np.random.randn(20, 5).astype(np.float32)
        y = np.zeros(20, dtype=np.int64)
        with pytest.raises(ValueError, match="Not enough samples"):
            model.fit(X, y)

    def test_get_feature_importance(self):
        model = LSTMClassifier()
        model.feature_names = ["a", "b", "c"]
        importance = model.get_feature_importance()
        assert len(importance) == 3
        assert abs(sum(importance.values()) - 1.0) < 1e-6

    def test_get_hyperparameters(self):
        model = LSTMClassifier(seq_len=12, hidden_size=32, max_epochs=20)
        hp = model.get_hyperparameters()
        assert hp["seq_len"] == 12
        assert hp["hidden_size"] == 32
        assert hp["max_epochs"] == 20
