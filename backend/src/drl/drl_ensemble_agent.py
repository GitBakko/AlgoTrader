# MANTIS-EVOLUTION: DRL Ensemble Agent for orchestrator integration
"""Integrates DRL ensemble into the multi-agent pipeline."""

from __future__ import annotations

import numpy as np
from loguru import logger

from src.agents.schemas import MarketContext
from src.drl.ensemble import MantisDRLEnsemble
from src.drl.schemas import DRLEnsembleSignal


class MantisDRLEnsembleAgent:
    """
    Integrates the DRL Ensemble into MantisAgentOrchestrator.

    Takes MarketContext, builds observation vector, detects regime,
    and runs ensemble prediction.

    Parameters
    ----------
    ensemble:
        A MantisDRLEnsemble instance (may contain zero or more trained agents).
    confidence_threshold:
        Minimum confidence to pass a non-HOLD action through. Signals whose
        confidence falls below this value are forced to HOLD (action=0).
    """

    def __init__(
        self,
        ensemble: MantisDRLEnsemble,
        confidence_threshold: float = 0.6,
    ) -> None:
        self.ensemble = ensemble
        self.confidence_threshold = confidence_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, context: MarketContext) -> DRLEnsembleSignal:
        """
        Run DRL ensemble analysis on the given market context.

        Returns
        -------
        DRLEnsembleSignal with action (0=HOLD, 1=BUY, 2=SELL), confidence,
        contributing agents, and voting metadata. On any error returns a safe
        HOLD signal with confidence=0.0.
        """
        try:
            observation = self._build_observation(context)
            regime = self._detect_regime(context)
            signal = self.ensemble.predict(observation, current_regime=regime)

            # Apply confidence threshold — low-confidence signals become HOLD
            if signal.confidence < self.confidence_threshold:
                signal.action = 0  # HOLD

            return signal
        except Exception as e:
            logger.warning(f"DRL ensemble failed: {e!r}")
            return DRLEnsembleSignal(action=0, confidence=0.0)

    # ------------------------------------------------------------------
    # Observation builder
    # ------------------------------------------------------------------

    def _build_observation(self, context: MarketContext) -> np.ndarray:
        """
        Build a fixed-size float32 observation vector from MarketContext.

        The vector has 6 elements (all normalised to roughly [0, 1]):
        0. RSI(14) / 100
        1. ADX(14) / 100
        2. EMA(9) / current_price
        3. EMA(21) / current_price
        4. ATR as % of price (clamped to 1.0)
        5. open_positions / 10
        """
        features = context.features or {}
        price = max(context.current_price, 1.0)

        obs = [
            features.get("rsi_14", 50.0) / 100.0,
            features.get("adx_14", 25.0) / 100.0,
            features.get("ema_9", price) / price,
            features.get("ema_21", price) / price,
            min(context.atr / price * 100.0, 1.0),
            context.open_positions / 10.0,
        ]
        return np.array(obs, dtype=np.float32)

    # ------------------------------------------------------------------
    # Regime detector
    # ------------------------------------------------------------------

    def _detect_regime(self, context: MarketContext) -> str:
        """
        Detect market regime for ensemble routing.

        If ``context.regime`` is already set it is returned verbatim.
        Otherwise a heuristic based on ADX and RSI is applied:

        - ADX > 35 and RSI > 60  → TRENDING_UP
        - ADX > 35 and RSI < 40  → TRENDING_DOWN
        - ADX > 35               → BREAKOUT
        - ADX < 20               → LOW_VOLATILITY
        - otherwise              → RANGING
        """
        if context.regime:
            return context.regime

        features = context.features or {}
        adx = features.get("adx_14", 25.0)
        rsi = features.get("rsi_14", 50.0)

        if adx > 35:
            if rsi > 60:
                return "TRENDING_UP"
            elif rsi < 40:
                return "TRENDING_DOWN"
            return "BREAKOUT"
        elif adx < 20:
            return "LOW_VOLATILITY"
        return "RANGING"
