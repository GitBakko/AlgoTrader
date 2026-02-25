"""Tests for feature selection: FeatureSelector class and select_top_features function."""

import numpy as np
import pytest

from src.models.feature_selector import (
    EXCLUDE_FEATURES,
    FeatureSelector,
    select_top_features,
)


# ---------------------------------------------------------------------------
# Tests for FeatureSelector class (percentage-based pruning)
# ---------------------------------------------------------------------------


class TestFeatureSelector:
    def test_fit_drops_correct_count(self):
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

    def test_fit_zero_drop(self):
        """drop_pct=0 should keep all features."""
        names = ["a", "b", "c"]
        importance = {"a": 1.0, "b": 2.0, "c": 3.0}

        selector = FeatureSelector(drop_pct=0.0)
        selected = selector.fit(importance, names)

        assert selected == names

    def test_transform_selects_columns(self):
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

    def test_transform_before_fit_raises(self):
        """transform() without fit() should raise RuntimeError."""
        selector = FeatureSelector(drop_pct=0.25)
        with pytest.raises(RuntimeError, match="Call fit"):
            selector.transform(np.zeros((2, 3)))

    def test_missing_features_treated_as_zero(self):
        """Features missing from importance dict should get importance=0."""
        names = ["present", "missing1", "missing2"]
        importance = {"present": 10.0}  # missing1, missing2 not in dict

        selector = FeatureSelector(drop_pct=0.50)
        selected = selector.fit(importance, names)

        assert len(selected) == 2  # drop 1 out of 3
        assert "present" in selected


# ---------------------------------------------------------------------------
# Tests for select_top_features function (top-N selection)
# ---------------------------------------------------------------------------


class TestSelectTopFeatures:
    def test_selects_top_n(self):
        """Should select top N features by importance."""

        class MockModel:
            def get_feature_importance(self):
                return {
                    "rsi_14": 100,
                    "macd_line": 80,
                    "ema_8": 60,
                    "noise_1": 1,
                    "noise_2": 0,
                }

        selected = select_top_features(
            MockModel(),
            ["rsi_14", "macd_line", "ema_8", "noise_1", "noise_2"],
            max_features=3,
        )
        assert selected == ["rsi_14", "macd_line", "ema_8"]
        assert "noise_1" not in selected
        assert "noise_2" not in selected

    def test_keeps_all_when_fewer_than_max(self):
        """Should keep all features when fewer than max."""

        class MockModel:
            def get_feature_importance(self):
                return {"rsi_14": 100, "macd_line": 80}

        selected = select_top_features(
            MockModel(),
            ["rsi_14", "macd_line"],
            max_features=10,
        )
        assert len(selected) == 2

    def test_empty_importance_returns_all(self):
        """Should return all features if no importance data."""

        class MockModel:
            def get_feature_importance(self):
                return {}

        features = ["a", "b", "c"]
        selected = select_top_features(MockModel(), features, max_features=2)
        assert selected == features

    def test_ordering_by_importance(self):
        """Should return features in descending importance order."""

        class MockModel:
            def get_feature_importance(self):
                return {"c": 10, "a": 100, "b": 50}

        selected = select_top_features(MockModel(), ["a", "b", "c"], max_features=3)
        assert selected == ["a", "b", "c"]

    def test_default_max_features(self):
        """Default max_features is 80."""

        class MockModel:
            def get_feature_importance(self):
                return {f"f{i}": float(100 - i) for i in range(100)}

        features = [f"f{i}" for i in range(100)]
        selected = select_top_features(MockModel(), features)
        assert len(selected) == 80
        # Top feature should be first
        assert selected[0] == "f0"
        # Feature at index 79 should be last
        assert selected[-1] == "f79"


# ---------------------------------------------------------------------------
# Tests for EXCLUDE_FEATURES constant
# ---------------------------------------------------------------------------


class TestExcludeFeatures:
    def test_regime_features_excluded(self):
        """Regime one-hot features should be in exclusion set."""
        assert "regime_trending_up" in EXCLUDE_FEATURES
        assert "regime_trending_down" in EXCLUDE_FEATURES
        assert "regime_ranging" in EXCLUDE_FEATURES

    def test_regime_zscore_features_excluded(self):
        """Z-score versions of regime features should be excluded."""
        assert "regime_trending_up_zscore" in EXCLUDE_FEATURES
        assert "regime_trending_down_zscore" in EXCLUDE_FEATURES
        assert "regime_ranging_zscore" in EXCLUDE_FEATURES

    def test_exclusion_in_feature_selection(self):
        """EXCLUDE_FEATURES should filter out regime features from a column list."""
        feature_cols = [
            "rsi_14_zscore",
            "macd_zscore",
            "regime_trending_up_zscore",
            "regime_ranging_zscore",
            "ema_8_zscore",
        ]
        filtered = [c for c in feature_cols if c not in EXCLUDE_FEATURES]
        assert "regime_trending_up_zscore" not in filtered
        assert "regime_ranging_zscore" not in filtered
        assert len(filtered) == 3

    def test_non_regime_features_not_excluded(self):
        """Regular features should not appear in EXCLUDE_FEATURES."""
        assert "rsi_14" not in EXCLUDE_FEATURES
        assert "macd_line_zscore" not in EXCLUDE_FEATURES
        assert "ema_8" not in EXCLUDE_FEATURES

    def test_exclude_set_size(self):
        """Should contain exactly 6 features (3 raw + 3 zscore)."""
        assert len(EXCLUDE_FEATURES) == 6
