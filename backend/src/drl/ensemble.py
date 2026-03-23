# MANTIS-EVOLUTION: DRL Ensemble with regime-based routing
"""Ensemble of DRL agents with dynamic voting based on market regime."""
from __future__ import annotations

from typing import Literal

import numpy as np
from loguru import logger

from src.drl.base_drl_agent import MantisDRLAgent
from src.drl.schemas import DRLEnsembleSignal


class MantisDRLEnsemble:
    """
    Ensemble of DRL agents with 3 voting modes.

    Voting modes:
    - REGIME_ROUTING: select agents whose best_regime matches the current regime.
      If multiple match, use weighted vote among them.
      If none match, fall back to WEIGHTED_VOTE among all agents.
    - WEIGHTED_VOTE: all agents vote with equal weight.
      Action with most votes wins; confidence = agreement ratio.
    - CONFIDENCE_GATE: like WEIGHTED_VOTE but returns HOLD when confidence < threshold.
    """

    def __init__(
        self,
        agents: dict[str, MantisDRLAgent],
        voting_mode: Literal["REGIME_ROUTING", "WEIGHTED_VOTE", "CONFIDENCE_GATE"] = "REGIME_ROUTING",
        confidence_threshold: float = 0.6,
    ) -> None:
        self.agents = agents
        self.voting_mode = voting_mode
        self.confidence_threshold = confidence_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def predict(
        self,
        observation: np.ndarray,
        current_regime: str = "UNKNOWN",
    ) -> DRLEnsembleSignal:
        """
        Produce an ensemble signal from all registered agents.

        Parameters
        ----------
        observation:
            Feature vector passed to each agent's predict().
        current_regime:
            Market regime label (e.g. "TRENDING_UP", "RANGING").
            Used only in REGIME_ROUTING mode.

        Returns
        -------
        DRLEnsembleSignal with action (0=HOLD, 1=BUY, 2=SELL), confidence,
        contributing_agents, agent_votes, voting_mode, and regime_match.
        """
        if not self.agents:
            return DRLEnsembleSignal(action=0, confidence=0.0)

        # Collect one vote per agent (HOLD on failure)
        votes: dict[str, int] = {}
        for name, agent in self.agents.items():
            try:
                action, _info = agent.predict(observation)
                votes[name] = int(action)
            except Exception as exc:
                logger.warning(f"[DRLEnsemble] Agent '{name}' predict failed: {exc!r} — voting HOLD")
                votes[name] = 0  # HOLD on failure

        if self.voting_mode == "REGIME_ROUTING":
            return self._regime_routing(votes, current_regime)
        elif self.voting_mode == "CONFIDENCE_GATE":
            return self._confidence_gate(votes)
        else:  # WEIGHTED_VOTE (default)
            return self._weighted_vote(votes)

    # ------------------------------------------------------------------
    # Voting strategies
    # ------------------------------------------------------------------

    def _regime_routing(
        self, votes: dict[str, int], current_regime: str
    ) -> DRLEnsembleSignal:
        """Route to agents whose best_regime includes current_regime."""
        regime_upper = current_regime.upper()
        matching_votes = {
            name: votes[name]
            for name, agent in self.agents.items()
            if any(r.upper() == regime_upper for r in agent.best_regime)
        }

        if matching_votes:
            signal = self._tally_votes(matching_votes)
            signal.regime_match = True
            signal.voting_mode = "REGIME_ROUTING"
        else:
            # No agent specialises in this regime — fall back to all
            signal = self._tally_votes(votes)
            signal.regime_match = False
            signal.voting_mode = "REGIME_ROUTING"

        return signal

    def _weighted_vote(self, votes: dict[str, int]) -> DRLEnsembleSignal:
        """Equal-weight vote among all agents."""
        signal = self._tally_votes(votes)
        signal.voting_mode = "WEIGHTED_VOTE"
        return signal

    def _confidence_gate(self, votes: dict[str, int]) -> DRLEnsembleSignal:
        """Like WEIGHTED_VOTE but forces HOLD when confidence is too low."""
        signal = self._tally_votes(votes)
        if signal.confidence < self.confidence_threshold:
            signal.action = 0  # HOLD
        signal.voting_mode = "CONFIDENCE_GATE"
        return signal

    # ------------------------------------------------------------------
    # Core tallying
    # ------------------------------------------------------------------

    def _tally_votes(self, votes: dict[str, int]) -> DRLEnsembleSignal:
        """Count votes and determine the winning action."""
        if not votes:
            return DRLEnsembleSignal(action=0, confidence=0.0)

        action_counts: dict[int, int] = {}
        for action in votes.values():
            action_counts[action] = action_counts.get(action, 0) + 1

        winner = max(action_counts, key=lambda a: action_counts[a])
        agreement = action_counts[winner] / len(votes)

        return DRLEnsembleSignal(
            action=winner,
            confidence=agreement,
            contributing_agents=[name for name, a in votes.items() if a == winner],
            agent_votes=dict(votes),
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def agent_count(self) -> int:
        """Number of agents registered in this ensemble."""
        return len(self.agents)
