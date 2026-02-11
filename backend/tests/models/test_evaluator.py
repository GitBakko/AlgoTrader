"""Tests for model evaluator module."""

import numpy as np
import pytest

from src.models.evaluator import ModelEvaluator
from src.models.schemas import SignalClass


class TestModelEvaluator:
    def test_perfect_predictions(self):
        y_true = np.array([0, 1, 2, 3, 4, 2, 3, 1, 0, 4])
        y_pred = y_true.copy()

        metrics = ModelEvaluator.evaluate(y_true, y_pred)
        assert metrics["accuracy"] == 1.0
        assert metrics["f1_macro"] == 1.0

    def test_random_predictions(self):
        np.random.seed(42)
        y_true = np.random.randint(0, 5, 100)
        y_pred = np.random.randint(0, 5, 100)

        metrics = ModelEvaluator.evaluate(y_true, y_pred)
        assert 0.0 <= metrics["accuracy"] <= 1.0
        assert 0.0 <= metrics["f1_macro"] <= 1.0

    def test_confusion_matrix_shape(self):
        y_true = np.array([0, 1, 2, 3, 4])
        y_pred = np.array([0, 1, 2, 3, 4])

        metrics = ModelEvaluator.evaluate(y_true, y_pred)
        cm = metrics["confusion_matrix"]
        assert len(cm) == 5
        assert len(cm[0]) == 5

    def test_with_probabilities(self):
        y_true = np.array([0, 1, 2])
        y_pred = np.array([0, 1, 2])
        y_proba = np.array([
            [0.9, 0.02, 0.03, 0.02, 0.03],
            [0.02, 0.9, 0.03, 0.02, 0.03],
            [0.02, 0.02, 0.9, 0.03, 0.03],
        ])

        metrics = ModelEvaluator.evaluate(y_true, y_pred, y_proba)
        assert "log_loss" in metrics
        assert metrics["log_loss"] > 0

    def test_classification_report(self):
        y_true = np.array([0, 1, 2, 2, 3, 4])
        y_pred = np.array([0, 1, 2, 3, 3, 4])

        metrics = ModelEvaluator.evaluate(y_true, y_pred)
        assert "classification_report" in metrics
        report = metrics["classification_report"]
        assert "STRONG_SELL" in report
        assert "BUY" in report

    def test_per_class_f1(self):
        y_true = np.array([0, 1, 2, 3, 4])
        y_pred = np.array([0, 1, 2, 3, 4])

        metrics = ModelEvaluator.evaluate(y_true, y_pred)
        assert "f1_STRONG_SELL" in metrics
        assert "f1_HOLD" in metrics
        assert "f1_STRONG_BUY" in metrics

    def test_summarize(self):
        y_true = np.array([0, 1, 2, 3, 4])
        y_pred = np.array([0, 1, 2, 3, 4])

        metrics = ModelEvaluator.evaluate(y_true, y_pred)
        summary = ModelEvaluator.summarize(metrics)
        assert "Accuracy" in summary
        assert "F1 (macro)" in summary
