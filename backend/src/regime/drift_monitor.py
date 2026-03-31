"""PSI-based feature distribution drift detector.

Computes Population Stability Index (PSI) between training and live
feature distributions to detect when the model's input has shifted
enough to warrant retraining.
"""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class DriftReport:
    """Result of a drift check."""

    overall_drift_score: float
    drifted_features: list[str]
    per_feature_psi: dict[str, float]
    is_safe: bool


class DriftMonitor:
    """Monitors feature distributions for drift using PSI."""

    N_BINS: int = 20

    def __init__(self, psi_threshold: float = 0.20) -> None:
        self.psi_threshold = psi_threshold
        self._training_hists: dict[str, tuple[np.ndarray, np.ndarray]] = {}

    def fit(self, feature_arrays: dict[str, np.ndarray]) -> None:
        """Compute and store training histograms for each feature."""
        self._training_hists = {}
        for name, values in feature_arrays.items():
            counts, bin_edges = np.histogram(values, bins=self.N_BINS)
            proportions = counts / counts.sum()
            proportions = np.maximum(proportions, 1e-8)
            self._training_hists[name] = (proportions, bin_edges)

    def compute_psi(self, name: str, live_values: np.ndarray) -> float:
        """Compute PSI for a single feature against its training distribution."""
        train_proportions, bin_edges = self._training_hists[name]
        live_counts, _ = np.histogram(live_values, bins=bin_edges)
        live_proportions = live_counts / live_counts.sum()
        live_proportions = np.maximum(live_proportions, 1e-8)
        psi = np.sum(
            (live_proportions - train_proportions) * np.log(live_proportions / train_proportions)
        )
        return float(psi)

    def check(self, feature_arrays: dict[str, np.ndarray]) -> DriftReport:
        """Check live features for drift against training distributions."""
        if not feature_arrays:
            return DriftReport(
                overall_drift_score=0.0,
                drifted_features=[],
                per_feature_psi={},
                is_safe=True,
            )

        per_feature_psi: dict[str, float] = {}
        drifted: list[str] = []

        for name, values in feature_arrays.items():
            if name not in self._training_hists:
                continue
            psi = self.compute_psi(name, values)
            per_feature_psi[name] = psi
            if psi > self.psi_threshold:
                drifted.append(name)

        if not per_feature_psi:
            return DriftReport(
                overall_drift_score=0.0,
                drifted_features=[],
                per_feature_psi={},
                is_safe=True,
            )

        overall = float(np.mean(list(per_feature_psi.values())))
        is_safe = overall <= self.psi_threshold and len(drifted) == 0

        return DriftReport(
            overall_drift_score=overall,
            drifted_features=drifted,
            per_feature_psi=per_feature_psi,
            is_safe=is_safe,
        )

    def save(self, path: str | Path) -> None:
        """Persist training histograms to disk."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(self._training_hists, f)

    @classmethod
    def load(cls, path: str | Path, psi_threshold: float = 0.20) -> DriftMonitor:
        """Load a previously saved DriftMonitor."""
        monitor = cls(psi_threshold=psi_threshold)
        with open(path, "rb") as f:
            monitor._training_hists = pickle.load(f)
        return monitor
