"""Tests for FeatureSelector (gain-based feature pruning)."""

import numpy as np
import pytest

from src.models.feature_selector import FeatureSelector


def test_fit_drops_correct_count():
    """Should drop exactly drop_pct fraction of features."""
    names = [f"f{i}" for i in range(10)]
    importance = {f"f{i}": float(i) for i in range(10)}  # f0=0, f9=9

    selector = FeatureSelector(drop_pct=0.30)
    selected = selector.fit(importance, names)

    assert len(selected) == 7  # drop 3 out of 10
    # Lowest importance (f0, f1, f2) should be dropped
    assert "f0" not in selected
    assert "f1" not in selected
    assert "f2" not in selected
    assert "f9" in selected


def test_fit_zero_drop():
    """drop_pct=0 should keep all features."""
    names = ["a", "b", "c"]
    importance = {"a": 1.0, "b": 2.0, "c": 3.0}

    selector = FeatureSelector(drop_pct=0.0)
    selected = selector.fit(importance, names)

    assert selected == names


def test_transform_selects_columns():
    """transform() should correctly slice the feature matrix."""
    names = ["a", "b", "c", "d"]
    importance = {"a": 0.0, "b": 5.0, "c": 0.0, "d": 10.0}

    selector = FeatureSelector(drop_pct=0.50)
    selector.fit(importance, names)

    X = np.array([
        [1.0, 2.0, 3.0, 4.0],
        [5.0, 6.0, 7.0, 8.0],
    ])
    X_out = selector.transform(X)

    assert X_out.shape == (2, 2)
    # Should keep b (col 1) and d (col 3)
    np.testing.assert_array_equal(X_out[:, 0], [2.0, 6.0])
    np.testing.assert_array_equal(X_out[:, 1], [4.0, 8.0])


def test_transform_before_fit_raises():
    """transform() without fit() should raise RuntimeError."""
    selector = FeatureSelector(drop_pct=0.25)
    with pytest.raises(RuntimeError, match="Call fit"):
        selector.transform(np.zeros((2, 3)))


def test_missing_features_treated_as_zero():
    """Features missing from importance dict should get importance=0."""
    names = ["present", "missing1", "missing2"]
    importance = {"present": 10.0}  # missing1, missing2 not in dict

    selector = FeatureSelector(drop_pct=0.50)
    selected = selector.fit(importance, names)

    assert len(selected) == 2  # drop 1 out of 3
    assert "present" in selected
