# MANTIS-EVOLUTION: DRL Training Pipeline
"""Train-test-compare pipeline for DRL agents."""
from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger

from src.drl.base_drl_agent import MantisDRLAgent
from src.drl.performance_analyzer import MantisPerformanceAnalyzer
from src.drl.schemas import ComparisonReport, PerformanceMetrics, TrainingResult


class MantisDRLTrainer:
    """
    Train-test-compare pipeline for DRL agents.
    Trains all agents on the same env for a fair comparison.
    """

    def __init__(self) -> None:
        self.analyzer = MantisPerformanceAnalyzer()
        self._training_results: dict[str, TrainingResult] = {}

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train_all_agents(
        self,
        agents: dict[str, MantisDRLAgent],
        total_timesteps: int = 50000,
    ) -> dict[str, TrainingResult]:
        """
        Train all agents sequentially on their environments.

        Args:
            agents: Mapping of name → agent instance.
            total_timesteps: Number of timesteps per agent.

        Returns:
            Mapping of name → TrainingResult.
        """
        results: dict[str, TrainingResult] = {}
        for name, agent in agents.items():
            logger.info(f"[MantisDRLTrainer] Training {name} for {total_timesteps} steps …")
            result = agent.train(total_timesteps=total_timesteps)
            results[name] = result
            status = "converged" if result.converged else "failed"
            logger.info(
                f"[MantisDRLTrainer] [{name}] Training {status} "
                f"in {result.training_time_seconds:.1f}s"
            )
        self._training_results = results
        return results

    # ------------------------------------------------------------------
    # Evaluation & comparison
    # ------------------------------------------------------------------

    def evaluate_and_compare(
        self,
        agents: dict[str, MantisDRLAgent],
        eval_env: Any,
        n_episodes: int = 5,
    ) -> ComparisonReport:
        """
        Evaluate all agents on the same eval environment and compare.

        Args:
            agents: Mapping of name → agent instance.
            eval_env: A gymnasium-compatible environment (reset/step interface).
            n_episodes: Number of evaluation episodes per agent.

        Returns:
            ComparisonReport with per-agent metrics, overall_best, and
            regime-to-best-agent mapping.
        """
        report = ComparisonReport()
        best_sharpe = -float("inf")

        for name, agent in agents.items():
            try:
                metrics = self._evaluate_agent(agent, eval_env, n_episodes)
                report.agent_metrics[name] = metrics
                if metrics.sharpe_ratio > best_sharpe:
                    best_sharpe = metrics.sharpe_ratio
                    report.overall_best = name
                logger.debug(
                    f"[MantisDRLTrainer] [{name}] sharpe={metrics.sharpe_ratio:.3f} "
                    f"total_return={metrics.total_return:.3%}"
                )
            except Exception as exc:
                logger.warning(f"[MantisDRLTrainer] [{name}] Evaluation failed: {exc!r}")
                report.agent_metrics[name] = PerformanceMetrics()

        report.best_by_regime = self._auto_select_for_regimes(agents, report)
        return report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _evaluate_agent(
        self,
        agent: MantisDRLAgent,
        env: Any,
        n_episodes: int,
    ) -> PerformanceMetrics:
        """Roll out n_episodes and collect per-step rewards for metric calc."""
        all_rewards: list[float] = []

        for _ in range(n_episodes):
            obs, _ = env.reset()
            done = False
            while not done:
                action, _ = agent.predict(np.asarray(obs, dtype=np.float32))
                obs, reward, terminated, truncated, _ = env.step(action)
                all_rewards.append(float(reward))
                done = terminated or truncated

        returns = np.array(all_rewards, dtype=np.float64)
        if len(returns) == 0:
            return PerformanceMetrics()

        return self.analyzer.generate_report(returns)

    def _auto_select_for_regimes(
        self,
        agents: dict[str, MantisDRLAgent],
        report: ComparisonReport,
    ) -> dict[str, str]:
        """
        Build a regime → best-agent mapping.

        For each regime claimed by at least one agent, the agent with the
        highest Sharpe ratio in the report wins.  Ties are broken by
        iteration order (first seen wins).
        """
        regime_map: dict[str, str] = {}

        for name, agent in agents.items():
            agent_sharpe = report.agent_metrics.get(name, PerformanceMetrics()).sharpe_ratio
            for regime in agent.best_regime:
                if regime not in regime_map:
                    regime_map[regime] = name
                else:
                    current_best = regime_map[regime]
                    current_sharpe = report.agent_metrics.get(
                        current_best, PerformanceMetrics()
                    ).sharpe_ratio
                    if agent_sharpe > current_sharpe:
                        regime_map[regime] = name

        return regime_map
