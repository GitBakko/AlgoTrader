# MANTIS-EVOLUTION: RL Agent Wrapper
"""RL agent that integrates with MantisAgentOrchestrator."""

from __future__ import annotations

import numpy as np
from loguru import logger

from src.agents.schemas import AgentRole, MarketContext
from src.rl.schemas import RLAction, RLSignal
from src.rl.adaptive_trainer import MantisAdaptiveTrainer
from src.rl.feature_pipeline import RLFeaturePipeline


class MantisRLAgent:
    """
    RL agent for the MantisAgentOrchestrator.

    Uses the trained model from AdaptiveTrainer to predict actions.

    Note: Does NOT inherit MantisBaseAgent (no LLM needed).
    Provides ``analyze()`` with the same async signature for orchestrator
    compatibility.
    """

    role = AgentRole.RL_ADAPTIVE

    def __init__(
        self,
        trainer: MantisAdaptiveTrainer | None = None,
    ) -> None:
        self._trainer = trainer
        self._feature_pipeline = RLFeaturePipeline()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def analyze(self, context: MarketContext) -> RLSignal | None:
        """
        Predict action using the current RL model.

        Returns ``None`` when:
        - no trainer is attached, or
        - the trainer has no model yet, or
        - prediction raises an unexpected error.
        """
        if self._trainer is None:
            return None

        model = self._trainer.get_current_model()
        if model is None:
            logger.debug("No RL model available yet")
            return None

        try:
            obs = self._build_observation(context)

            # deterministic=True → greedy policy (no exploration noise)
            action, _states = model.predict(obs, deterministic=True)
            action_int = int(action)

            mapped_action = self._map_action(action_int)
            confidence = self._estimate_confidence(action_int)

            return RLSignal(
                action=mapped_action,
                confidence=confidence,
                model_version=self._trainer.current_model_version,
                algorithm=self._trainer.config.algorithm,
                raw_action=action_int,
            )

        except Exception as exc:
            logger.warning(f"RL prediction failed: {exc!r}")
            return None

    # ------------------------------------------------------------------
    # Observation construction
    # ------------------------------------------------------------------

    def _build_observation(self, context: MarketContext) -> np.ndarray:
        """
        Build a flat observation vector from the MarketContext.

        The last four elements encode position state; for signal generation
        (no open position) these default to flat/zero.
        """
        features = self._feature_pipeline.extract_features(context)

        # position state: unrealised profit, position (-1/0/1), duration, vol_regime
        position_state = np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32)

        return np.concatenate([features, position_state])

    # ------------------------------------------------------------------
    # Action mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _map_action(action: int) -> str:
        """Map a raw RLAction integer to a BUY / SELL / HOLD string."""
        if action == RLAction.LONG_ENTRY:
            return "BUY"
        elif action == RLAction.SHORT_ENTRY:
            return "SELL"
        # LONG_EXIT, SHORT_EXIT, NEUTRAL all map to HOLD for signal generation
        return "HOLD"

    # ------------------------------------------------------------------
    # Confidence estimation
    # ------------------------------------------------------------------

    def _estimate_confidence(self, action: int) -> float:
        """
        Estimate confidence of the RL action.

        Uses a simple heuristic:
        - Entry actions (LONG_ENTRY, SHORT_ENTRY) → 0.7
        - Exit actions (LONG_EXIT, SHORT_EXIT)    → 0.6
        - Neutral                                 → 0.5
        - No model version present                → 0.3
        """
        if not self._trainer or not self._trainer.current_model_version:
            return 0.3

        if action in (RLAction.LONG_ENTRY, RLAction.SHORT_ENTRY):
            return 0.7
        if action in (RLAction.LONG_EXIT, RLAction.SHORT_EXIT):
            return 0.6
        return 0.5  # NEUTRAL
