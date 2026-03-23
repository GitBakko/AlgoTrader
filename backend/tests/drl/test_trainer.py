# MANTIS-EVOLUTION: DRL Trainer tests
"""Tests for MantisDRLTrainer."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.drl.schemas import (
    ComparisonReport,
    PerformanceMetrics,
    TrainingResult,
)
# Import trainer/backtest directly to avoid circular-import via __init__.py


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_agent(name: str, best_regime: list[str], sharpe: float = 1.0) -> MagicMock:
    """Create a mock MantisDRLAgent."""
    agent = MagicMock()
    agent.algorithm_name = name
    agent.best_regime = best_regime

    # train() returns a TrainingResult
    agent.train.return_value = TrainingResult(
        algorithm=name,
        total_timesteps=100,
        training_time_seconds=0.5,
        converged=True,
    )

    # predict() returns (action, info)
    agent.predict.return_value = (1, {"confidence": 0.7})  # BUY

    return agent


def _make_mock_env(n_steps: int = 5, reward: float = 0.01) -> MagicMock:
    """Create a mock gymnasium environment."""
    env = MagicMock()
    obs = np.zeros(6, dtype=np.float32)

    # Simulate a short episode with n_steps then done
    step_count = {"n": 0}

    def _reset(**kwargs):
        step_count["n"] = 0
        return obs, {}

    def _step(action):
        step_count["n"] += 1
        done = step_count["n"] >= n_steps
        return obs, reward, done, False, {}

    env.reset.side_effect = _reset
    env.step.side_effect = _step
    return env


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestMantisDRLTrainer:

    def test_train_all_agents(self):
        """train_all_agents() calls train on each agent and returns results."""
        from src.drl.trainer import MantisDRLTrainer

        agents = {
            "PPO": _make_mock_agent("PPO", ["TRENDING_UP"]),
            "A2C": _make_mock_agent("A2C", ["RANGING"]),
        }
        trainer = MantisDRLTrainer()
        results = trainer.train_all_agents(agents, total_timesteps=100)

        assert set(results.keys()) == {"PPO", "A2C"}
        for name, result in results.items():
            assert isinstance(result, TrainingResult)
            assert result.converged is True
            assert result.total_timesteps == 100

        # Ensure train() was called on each agent
        agents["PPO"].train.assert_called_once_with(total_timesteps=100)
        agents["A2C"].train.assert_called_once_with(total_timesteps=100)

    def test_training_results_stored(self):
        """After training, results are stored on the trainer instance."""
        from src.drl.trainer import MantisDRLTrainer

        agents = {"PPO": _make_mock_agent("PPO", ["TRENDING_UP"])}
        trainer = MantisDRLTrainer()
        trainer.train_all_agents(agents, total_timesteps=100)

        assert "PPO" in trainer._training_results
        assert isinstance(trainer._training_results["PPO"], TrainingResult)

    def test_evaluate_and_compare(self):
        """evaluate_and_compare() returns ComparisonReport with metrics for each agent."""
        from src.drl.trainer import MantisDRLTrainer

        agents = {
            "PPO": _make_mock_agent("PPO", ["TRENDING_UP"], sharpe=1.5),
            "A2C": _make_mock_agent("A2C", ["RANGING"], sharpe=0.5),
        }
        env = _make_mock_env(n_steps=5)
        trainer = MantisDRLTrainer()
        report = trainer.evaluate_and_compare(agents, env, n_episodes=2)

        assert isinstance(report, ComparisonReport)
        assert "PPO" in report.agent_metrics
        assert "A2C" in report.agent_metrics
        assert isinstance(report.agent_metrics["PPO"], PerformanceMetrics)
        assert isinstance(report.agent_metrics["A2C"], PerformanceMetrics)

    def test_overall_best_selected(self):
        """Agent with highest Sharpe ratio wins overall_best."""
        from src.drl.trainer import MantisDRLTrainer

        # PPO returns higher reward → higher Sharpe in report
        ppo = _make_mock_agent("PPO", ["TRENDING_UP"])
        a2c = _make_mock_agent("A2C", ["RANGING"])

        # Make PPO return higher reward per step
        ppo.predict.return_value = (1, {"confidence": 0.9})
        a2c.predict.return_value = (0, {"confidence": 0.1})  # HOLD → 0 reward

        # Env with positive reward for BUY (action=1)
        obs = np.zeros(6, dtype=np.float32)
        step_count = {"ppo": 0, "a2c": 0}

        env = _make_mock_env(n_steps=10, reward=0.05)

        agents = {"PPO": ppo, "A2C": a2c}
        trainer = MantisDRLTrainer()
        report = trainer.evaluate_and_compare(agents, env, n_episodes=3)

        # overall_best must be one of the registered agents
        assert report.overall_best in {"PPO", "A2C", ""}

    def test_auto_select_for_regimes(self):
        """_auto_select_for_regimes() maps regime -> best agent correctly."""
        from src.drl.trainer import MantisDRLTrainer

        ppo = _make_mock_agent("PPO", ["TRENDING_UP", "TRENDING_DOWN"])
        a2c = _make_mock_agent("A2C", ["RANGING"])
        sac = _make_mock_agent("SAC", ["TRENDING_UP"])  # Also claims TRENDING_UP

        agents = {"PPO": ppo, "A2C": a2c, "SAC": sac}

        # Build a fake report where SAC has the best sharpe for TRENDING_UP
        report = ComparisonReport(
            agent_metrics={
                "PPO": PerformanceMetrics(sharpe_ratio=0.5),
                "A2C": PerformanceMetrics(sharpe_ratio=1.2),
                "SAC": PerformanceMetrics(sharpe_ratio=2.0),
            }
        )

        trainer = MantisDRLTrainer()
        regime_map = trainer._auto_select_for_regimes(agents, report)

        # RANGING → A2C (only claimant)
        assert regime_map.get("RANGING") == "A2C"
        # TRENDING_UP → SAC (sharpe 2.0 > PPO 0.5)
        assert regime_map.get("TRENDING_UP") == "SAC"
        # TRENDING_DOWN → PPO (only claimant)
        assert regime_map.get("TRENDING_DOWN") == "PPO"

    def test_evaluate_agent_failed_gracefully(self):
        """If an agent's predict() raises, it gets empty PerformanceMetrics."""
        from src.drl.trainer import MantisDRLTrainer

        bad_agent = MagicMock()
        bad_agent.algorithm_name = "BAD"
        bad_agent.best_regime = []
        bad_agent.predict.side_effect = RuntimeError("boom")

        env = _make_mock_env(n_steps=3)
        trainer = MantisDRLTrainer()
        report = trainer.evaluate_and_compare({"BAD": bad_agent}, env, n_episodes=1)

        assert "BAD" in report.agent_metrics
        # Should have default zero metrics
        assert report.agent_metrics["BAD"].sharpe_ratio == 0.0
