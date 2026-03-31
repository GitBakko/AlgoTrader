"""Tests for PSI-based feature drift monitor."""

import numpy as np
import pytest

from src.regime.drift_monitor import DriftMonitor


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(42)


def test_no_drift_on_same_distribution(rng: np.random.Generator) -> None:
    """Train and live from same N(0,1) — should be safe with low PSI."""
    monitor = DriftMonitor(psi_threshold=0.20)
    train = {"feat_a": rng.standard_normal(5000)}
    monitor.fit(train)

    live = {"feat_a": rng.standard_normal(5000)}
    report = monitor.check(live)

    assert report.is_safe is True
    assert report.overall_drift_score < 0.1
    assert len(report.drifted_features) == 0


def test_high_drift_on_shifted_distribution(rng: np.random.Generator) -> None:
    """Train N(0,1) vs live N(5,1) — should detect drift."""
    monitor = DriftMonitor(psi_threshold=0.20)
    monitor.fit({"feat_a": rng.standard_normal(5000)})

    live = {"feat_a": rng.normal(5.0, 1.0, size=5000)}
    report = monitor.check(live)

    assert report.is_safe is False
    assert report.per_feature_psi["feat_a"] > 0.2
    assert "feat_a" in report.drifted_features


def test_multiple_features(rng: np.random.Generator) -> None:
    """One stable feature + one drifted — only drifted one flagged."""
    monitor = DriftMonitor(psi_threshold=0.20)
    monitor.fit(
        {
            "stable": rng.standard_normal(5000),
            "drifted": rng.standard_normal(5000),
        }
    )

    live = {
        "stable": rng.standard_normal(5000),
        "drifted": rng.normal(5.0, 1.0, size=5000),
    }
    report = monitor.check(live)

    assert "drifted" in report.drifted_features
    assert "stable" not in report.drifted_features


def test_empty_features_is_safe() -> None:
    """No features provided — should be safe."""
    monitor = DriftMonitor()
    monitor.fit({})
    report = monitor.check({})

    assert report.is_safe is True
    assert report.overall_drift_score == 0.0
    assert len(report.drifted_features) == 0


def test_save_and_load(tmp_path, rng: np.random.Generator) -> None:
    """Persist and reload monitor — results should match."""
    monitor = DriftMonitor(psi_threshold=0.20)
    train = {"feat_a": rng.standard_normal(5000)}
    monitor.fit(train)

    live = {"feat_a": rng.normal(5.0, 1.0, size=5000)}
    report_before = monitor.check(live)

    save_path = tmp_path / "drift_hists.pkl"
    monitor.save(save_path)

    loaded = DriftMonitor.load(save_path, psi_threshold=0.20)
    report_after = loaded.check(live)

    assert report_before.is_safe == report_after.is_safe
    assert report_before.per_feature_psi == pytest.approx(report_after.per_feature_psi)
    assert report_before.drifted_features == report_after.drifted_features
