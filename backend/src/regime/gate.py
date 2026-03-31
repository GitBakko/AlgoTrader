"""RegimeGate — single pass/fail gate combining HMM regime and PSI drift checks."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import polars as pl
from loguru import logger

if TYPE_CHECKING:
    import numpy as np

from src.regime.drift_monitor import DriftMonitor
from src.regime.hmm_detector import HMMRegimeDetector, MarketRegime


@dataclass
class GateDecision:
    """Result of the regime gate check."""

    approved: bool
    reason: str
    regime: MarketRegime | None = None
    regime_confidence: float = 0.0
    drift_score: float = 0.0
    drifted_features: list[str] = field(default_factory=list)


class RegimeGate:
    """Combines HMM regime confidence and PSI drift into a single trading gate."""

    def __init__(
        self,
        confidence_threshold: float = 0.65,
        psi_threshold: float = 0.20,
    ) -> None:
        self.confidence_threshold = confidence_threshold
        self.psi_threshold = psi_threshold
        self.hmm_detector: HMMRegimeDetector | None = None
        self.drift_monitor: DriftMonitor | None = None

        # Tracking counters
        self.blocked_count: int = 0
        self.passed_count: int = 0
        self.blocked_by_hmm: int = 0
        self.blocked_by_drift: int = 0

    def check(
        self,
        df: pl.DataFrame,
        feature_columns: dict[str, np.ndarray] | None = None,
    ) -> GateDecision:
        """Run regime and drift checks, returning a single pass/fail decision.

        Args:
            df: OHLCV DataFrame for HMM regime detection.
            feature_columns: Dict of feature_name -> values for drift checking.

        Returns:
            GateDecision with approval status and metadata.
        """
        hmm_fitted = self.hmm_detector is not None and self.hmm_detector.is_fitted
        drift_fitted = (
            self.drift_monitor is not None and len(self.drift_monitor._training_hists) > 0
        )

        # If neither detector is fitted, gate is disabled
        if not hmm_fitted and not drift_fitted:
            self.passed_count += 1
            return GateDecision(
                approved=True,
                reason="Gate disabled (no detectors fitted)",
            )

        # --- HMM regime check ---
        regime: MarketRegime | None = None
        regime_confidence: float = 0.0

        if hmm_fitted:
            try:
                state = self.hmm_detector.predict(df)  # type: ignore[union-attr]
                regime = state.regime
                regime_confidence = state.confidence
                if not state.is_tradeable:
                    self.blocked_count += 1
                    self.blocked_by_hmm += 1
                    return GateDecision(
                        approved=False,
                        reason=(
                            f"HMM confidence too low: {regime_confidence:.2f} "
                            f"< {self.confidence_threshold:.2f}"
                        ),
                        regime=regime,
                        regime_confidence=regime_confidence,
                    )
            except Exception as exc:
                logger.debug(f"HMM check failed (non-blocking): {exc}")

        # --- Drift check ---
        drift_score: float = 0.0
        drifted_features: list[str] = []

        if drift_fitted and feature_columns is not None:
            try:
                report = self.drift_monitor.check(feature_columns)  # type: ignore[union-attr]
                drift_score = report.overall_drift_score
                drifted_features = report.drifted_features
                if not report.is_safe:
                    self.blocked_count += 1
                    self.blocked_by_drift += 1
                    return GateDecision(
                        approved=False,
                        reason=(
                            f"Feature drift detected: score={drift_score:.3f}, "
                            f"drifted={drifted_features}"
                        ),
                        regime=regime,
                        regime_confidence=regime_confidence,
                        drift_score=drift_score,
                        drifted_features=drifted_features,
                    )
            except Exception as exc:
                logger.debug(f"Drift check failed (non-blocking): {exc}")

        # Both checks passed
        self.passed_count += 1
        return GateDecision(
            approved=True,
            reason="All checks passed",
            regime=regime,
            regime_confidence=regime_confidence,
            drift_score=drift_score,
            drifted_features=drifted_features,
        )

    def get_stats(self) -> dict:
        """Return gate statistics."""
        total = self.blocked_count + self.passed_count
        return {
            "total_checks": total,
            "blocked": self.blocked_count,
            "passed": self.passed_count,
            "blocked_by_hmm": self.blocked_by_hmm,
            "blocked_by_drift": self.blocked_by_drift,
            "block_rate": self.blocked_count / total if total > 0 else 0.0,
        }
