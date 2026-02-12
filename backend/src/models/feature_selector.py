"""
Feature selection based on XGBoost gain importance.

Fits on the first walk-forward fold's trained model, then prunes
low-importance features for subsequent folds.
"""

import numpy as np
from loguru import logger


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
