"""
Feature importance analysis and selection.

Provides two mechanisms:
1. FeatureSelector class — percentage-based pruning (used in walk_forward_backtest.py)
2. select_top_features() — keeps top N features by XGBoost gain importance
3. EXCLUDE_FEATURES — known problematic features to always exclude
"""

import numpy as np
from loguru import logger


# Features to always exclude (known problematic)
EXCLUDE_FEATURES = {
    # Regime one-hot: perfectly collinear (3 binary = 2 are redundant)
    "regime_trending_up",
    "regime_trending_down",
    "regime_ranging",
    # Z-score versions too (normalizer appends _zscore)
    "regime_trending_up_zscore",
    "regime_trending_down_zscore",
    "regime_ranging_zscore",
}


def select_top_features(
    model,
    feature_names: list[str],
    max_features: int = 80,
) -> list[str]:
    """
    Select top features by XGBoost gain importance.

    Args:
        model: Trained XGBoostClassifier (must have get_feature_importance())
        feature_names: All feature column names
        max_features: Maximum features to keep

    Returns:
        List of top feature names
    """
    importance = model.get_feature_importance()
    if not importance:
        logger.warning("No feature importance available, keeping all features")
        return feature_names

    # Sort by importance descending
    sorted_features = sorted(importance.items(), key=lambda x: x[1], reverse=True)

    # Keep top N
    selected = [name for name, _ in sorted_features[:max_features]]

    # Log dropped features
    dropped = len(feature_names) - len(selected)
    if dropped > 0:
        logger.info(
            f"Feature selection: kept {len(selected)}/{len(feature_names)} features "
            f"(dropped {dropped} low-importance)"
        )
        # Log bottom 10 dropped
        bottom = sorted_features[max_features:max_features + 10]
        for name, imp in bottom:
            logger.debug(f"  Dropped: {name} (importance={imp:.6f})")

    return selected


class FeatureSelector:
    """Selects features by dropping the bottom N% by XGBoost gain importance."""

    def __init__(self, drop_pct: float = 0.25):
        """
        Args:
            drop_pct: Fraction of features to drop (0.25 = drop bottom 25%).
        """
        self.drop_pct = drop_pct
        self.selected_indices: np.ndarray | None = None
        self.selected_names: list[str] | None = None

    def fit(
        self,
        importance_dict: dict[str, float],
        feature_names: list[str],
    ) -> list[str]:
        """
        Determine which features to keep based on gain importance.

        Args:
            importance_dict: Feature name -> gain from XGBoost get_feature_importance()
            feature_names: All feature column names (in order)

        Returns:
            List of selected feature names (ordered as in input)
        """
        importances = np.array([importance_dict.get(name, 0.0) for name in feature_names])

        n_drop = int(len(feature_names) * self.drop_pct)
        if n_drop == 0:
            self.selected_indices = np.arange(len(feature_names))
            self.selected_names = list(feature_names)
            return self.selected_names

        sorted_indices = np.argsort(importances)
        drop_set = set(sorted_indices[:n_drop].tolist())

        self.selected_indices = np.array(
            [i for i in range(len(feature_names)) if i not in drop_set]
        )
        self.selected_names = [feature_names[i] for i in self.selected_indices]

        n_zero = int((importances == 0.0).sum())
        logger.info(
            f"Feature selection: {len(feature_names)} -> {len(self.selected_names)} features "
            f"(dropped {n_drop}, {n_zero} had zero importance)"
        )

        return self.selected_names

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Select columns from feature matrix."""
        if self.selected_indices is None:
            raise RuntimeError("Call fit() first")
        return X[:, self.selected_indices]
