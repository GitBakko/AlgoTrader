# MANTIS-EVOLUTION: DRL Ensemble tests
"""Tests for MantisDRLEnsemble — all agents are mocked (no real training)."""
from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import MagicMock

from src.drl.base_drl_agent import MantisDRLAgent
from src.drl.ensemble import MantisDRLEnsemble
from src.drl.schemas import DRLEnsembleSignal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OBS = np.zeros(10, dtype=np.float32)


def make_mock_agent(
    algorithm_name: str,
    best_regime: list[str],
    action: int = 0,
) -> MagicMock:
    agent = MagicMock(spec=MantisDRLAgent)
    agent.algorithm_name = algorithm_name
    agent.best_regime = best_regime
    agent.predict.return_value = (action, {"confidence": 0.7})
    return agent


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMantisDRLEnsemble:

    # 1. Empty ensemble -------------------------------------------------------

    def test_empty_ensemble(self):
        ensemble = MantisDRLEnsemble(agents={})
        signal = ensemble.predict(OBS)
        assert signal.action == 0
        assert signal.confidence == 0.0

    # 2-4. WEIGHTED_VOTE — unanimous / split ----------------------------------

    def test_weighted_vote_unanimous_buy(self):
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=1),
            "sac": make_mock_agent("SAC", ["RANGING"], action=1),
            "a2c": make_mock_agent("A2C", ["TRENDING_DOWN"], action=1),
            "td3": make_mock_agent("TD3", ["TRENDING_UP"], action=1),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="WEIGHTED_VOTE")
        signal = ensemble.predict(OBS)
        assert signal.action == 1
        assert signal.confidence == 1.0

    def test_weighted_vote_unanimous_sell(self):
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=2),
            "sac": make_mock_agent("SAC", ["RANGING"], action=2),
            "a2c": make_mock_agent("A2C", ["TRENDING_DOWN"], action=2),
            "td3": make_mock_agent("TD3", ["TRENDING_UP"], action=2),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="WEIGHTED_VOTE")
        signal = ensemble.predict(OBS)
        assert signal.action == 2
        assert signal.confidence == 1.0

    def test_weighted_vote_split(self):
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=1),
            "sac": make_mock_agent("SAC", ["RANGING"], action=1),
            "a2c": make_mock_agent("A2C", ["TRENDING_DOWN"], action=1),
            "td3": make_mock_agent("TD3", ["TRENDING_UP"], action=2),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="WEIGHTED_VOTE")
        signal = ensemble.predict(OBS)
        assert signal.action == 1
        assert signal.confidence == pytest.approx(0.75)

    # 5. Tie ------------------------------------------------------------------

    def test_weighted_vote_tie(self):
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=1),
            "sac": make_mock_agent("SAC", ["RANGING"], action=1),
            "a2c": make_mock_agent("A2C", ["TRENDING_DOWN"], action=2),
            "td3": make_mock_agent("TD3", ["TRENDING_UP"], action=2),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="WEIGHTED_VOTE")
        signal = ensemble.predict(OBS)
        # Either 1 or 2 is acceptable; confidence must be 0.5
        assert signal.action in (1, 2)
        assert signal.confidence == pytest.approx(0.5)

    # 6-9. REGIME_ROUTING -----------------------------------------------------

    def test_regime_routing_trending(self):
        """PPO (BUY, TRENDING_UP) matches; SAC (SELL, RANGING) does not."""
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=1),
            "sac": make_mock_agent("SAC", ["RANGING"], action=2),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="REGIME_ROUTING")
        signal = ensemble.predict(OBS, current_regime="TRENDING_UP")
        assert signal.action == 1  # PPO wins (only matcher)

    def test_regime_routing_ranging(self):
        """SAC matches RANGING regime → uses SAC's SELL vote."""
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=1),
            "sac": make_mock_agent("SAC", ["RANGING"], action=2),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="REGIME_ROUTING")
        signal = ensemble.predict(OBS, current_regime="RANGING")
        assert signal.action == 2  # SAC wins (only matcher)

    def test_regime_routing_no_match(self):
        """Unknown regime → falls back to all agents (WEIGHTED_VOTE)."""
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=1),
            "sac": make_mock_agent("SAC", ["RANGING"], action=1),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="REGIME_ROUTING")
        signal = ensemble.predict(OBS, current_regime="UNKNOWN_REGIME_XYZ")
        # Both fallback to weighted vote → both vote BUY
        assert signal.action == 1
        assert signal.confidence == 1.0

    def test_regime_routing_sets_regime_match_true(self):
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=1),
            "sac": make_mock_agent("SAC", ["RANGING"], action=2),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="REGIME_ROUTING")
        signal = ensemble.predict(OBS, current_regime="TRENDING_UP")
        assert signal.regime_match is True

    def test_regime_routing_sets_regime_match_false_on_fallback(self):
        agents = {
            "ppo": make_mock_agent("PPO", ["TRENDING_UP"], action=1),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="REGIME_ROUTING")
        signal = ensemble.predict(OBS, current_regime="TOTALLY_UNKNOWN")
        assert signal.regime_match is False

    # 10-11. CONFIDENCE_GATE --------------------------------------------------

    def test_confidence_gate_above_threshold(self):
        """Unanimous vote → confidence 1.0 > 0.6 → action passes through."""
        agents = {
            "ppo": make_mock_agent("PPO", [], action=1),
            "sac": make_mock_agent("SAC", [], action=1),
        }
        ensemble = MantisDRLEnsemble(
            agents=agents,
            voting_mode="CONFIDENCE_GATE",
            confidence_threshold=0.6,
        )
        signal = ensemble.predict(OBS)
        assert signal.action == 1
        assert signal.voting_mode == "CONFIDENCE_GATE"

    def test_confidence_gate_below_threshold(self):
        """2 BUY vs 2 SELL → confidence 0.5 < 0.6 → HOLD (action=0)."""
        agents = {
            "ppo": make_mock_agent("PPO", [], action=1),
            "sac": make_mock_agent("SAC", [], action=1),
            "a2c": make_mock_agent("A2C", [], action=2),
            "td3": make_mock_agent("TD3", [], action=2),
        }
        ensemble = MantisDRLEnsemble(
            agents=agents,
            voting_mode="CONFIDENCE_GATE",
            confidence_threshold=0.6,
        )
        signal = ensemble.predict(OBS)
        assert signal.action == 0  # HOLD due to low confidence

    # 12. Agent failure -------------------------------------------------------

    def test_agent_failure_returns_hold(self):
        """Agent that raises gets HOLD vote; remaining agents still count."""
        bad_agent = MagicMock(spec=MantisDRLAgent)
        bad_agent.algorithm_name = "BAD"
        bad_agent.best_regime = []
        bad_agent.predict.side_effect = RuntimeError("model exploded")

        agents = {
            "bad": bad_agent,
            "ppo": make_mock_agent("PPO", [], action=1),
            "sac": make_mock_agent("SAC", [], action=1),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="WEIGHTED_VOTE")
        signal = ensemble.predict(OBS)
        # bad→HOLD(0), ppo→BUY(1), sac→BUY(1): BUY wins 2/3
        assert signal.action == 1
        assert signal.confidence == pytest.approx(2 / 3)

    # 13. Contributing agents -------------------------------------------------

    def test_contributing_agents_listed(self):
        agents = {
            "ppo": make_mock_agent("PPO", [], action=1),
            "sac": make_mock_agent("SAC", [], action=1),
            "a2c": make_mock_agent("A2C", [], action=2),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="WEIGHTED_VOTE")
        signal = ensemble.predict(OBS)
        assert signal.action == 1
        assert set(signal.contributing_agents) == {"ppo", "sac"}

    # 14. Agent votes recorded ------------------------------------------------

    def test_agent_votes_recorded(self):
        agents = {
            "ppo": make_mock_agent("PPO", [], action=1),
            "sac": make_mock_agent("SAC", [], action=2),
        }
        ensemble = MantisDRLEnsemble(agents=agents, voting_mode="WEIGHTED_VOTE")
        signal = ensemble.predict(OBS)
        assert signal.agent_votes == {"ppo": 1, "sac": 2}

    # 15. agent_count property ------------------------------------------------

    def test_agent_count_property(self):
        agents = {
            "ppo": make_mock_agent("PPO", [], action=1),
            "sac": make_mock_agent("SAC", [], action=2),
            "a2c": make_mock_agent("A2C", [], action=0),
        }
        ensemble = MantisDRLEnsemble(agents=agents)
        assert ensemble.agent_count == 3
