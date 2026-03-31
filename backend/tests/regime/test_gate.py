"""Tests for RegimeGate combining HMM confidence and PSI drift checks."""

from unittest.mock import MagicMock

import polars as pl

from src.regime.drift_monitor import DriftReport
from src.regime.gate import RegimeGate
from src.regime.hmm_detector import MarketRegime, RegimeState


def _make_dummy_df() -> pl.DataFrame:
    """Create a minimal DataFrame for gate calls."""
    return pl.DataFrame({"close": [1.0, 2.0, 3.0]})


def test_pass_when_both_ok():
    """HMM confidence=0.85 + no drift -> approved=True."""
    gate = RegimeGate(confidence_threshold=0.65, psi_threshold=0.20)

    # Mock HMM detector
    hmm = MagicMock()
    hmm.is_fitted = True
    hmm.predict.return_value = RegimeState(
        regime=MarketRegime.TRENDING_UP,
        confidence=0.85,
        regime_duration=5,
        is_tradeable=True,
        state_probabilities=dict.fromkeys(MarketRegime, 0.05),
    )
    gate.hmm_detector = hmm

    # Mock drift monitor
    drift = MagicMock()
    drift._training_hists = {"rsi_14": True}  # non-empty so drift_fitted=True
    drift.check.return_value = DriftReport(
        overall_drift_score=0.05,
        drifted_features=[],
        per_feature_psi={"rsi_14": 0.05},
        is_safe=True,
    )
    gate.drift_monitor = drift

    decision = gate.check(_make_dummy_df(), feature_columns={"rsi_14": [1, 2, 3]})

    assert decision.approved is True
    assert decision.regime == MarketRegime.TRENDING_UP
    assert decision.regime_confidence == 0.85
    assert decision.drift_score == 0.05
    assert decision.drifted_features == []
    assert gate.passed_count == 1
    assert gate.blocked_count == 0


def test_block_low_confidence():
    """HMM confidence=0.40 -> approved=False, 'confidence' in reason."""
    gate = RegimeGate(confidence_threshold=0.65, psi_threshold=0.20)

    hmm = MagicMock()
    hmm.is_fitted = True
    hmm.predict.return_value = RegimeState(
        regime=MarketRegime.HIGH_VOLATILITY,
        confidence=0.40,
        regime_duration=2,
        is_tradeable=False,
        state_probabilities=dict.fromkeys(MarketRegime, 0.25),
    )
    gate.hmm_detector = hmm

    decision = gate.check(_make_dummy_df())

    assert decision.approved is False
    assert "confidence" in decision.reason.lower()
    assert decision.regime_confidence == 0.40
    assert gate.blocked_count == 1
    assert gate.blocked_by_hmm == 1


def test_block_drift():
    """drift_score=0.35, drifted_features=['rsi_14','atr_14'] -> blocked, 'drift' in reason."""
    gate = RegimeGate(confidence_threshold=0.65, psi_threshold=0.20)

    # HMM passes
    hmm = MagicMock()
    hmm.is_fitted = True
    hmm.predict.return_value = RegimeState(
        regime=MarketRegime.TRENDING_UP,
        confidence=0.90,
        regime_duration=10,
        is_tradeable=True,
        state_probabilities=dict.fromkeys(MarketRegime, 0.05),
    )
    gate.hmm_detector = hmm

    # Drift fails
    drift = MagicMock()
    drift._training_hists = {"rsi_14": True, "atr_14": True}
    drift.check.return_value = DriftReport(
        overall_drift_score=0.35,
        drifted_features=["rsi_14", "atr_14"],
        per_feature_psi={"rsi_14": 0.40, "atr_14": 0.30},
        is_safe=False,
    )
    gate.drift_monitor = drift

    decision = gate.check(
        _make_dummy_df(),
        feature_columns={"rsi_14": [1, 2], "atr_14": [3, 4]},
    )

    assert decision.approved is False
    assert "drift" in decision.reason.lower()
    assert decision.drift_score == 0.35
    assert decision.drifted_features == ["rsi_14", "atr_14"]
    assert gate.blocked_count == 1
    assert gate.blocked_by_drift == 1


def test_pass_when_disabled():
    """No detectors fitted -> approved=True, 'disabled' in reason."""
    gate = RegimeGate()

    decision = gate.check(_make_dummy_df())

    assert decision.approved is True
    assert "disabled" in decision.reason.lower()
    assert gate.passed_count == 1
    assert gate.blocked_count == 0
