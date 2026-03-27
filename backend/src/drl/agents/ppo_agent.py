# MANTIS-EVOLUTION: PPO DRL Agent
"""Proximal Policy Optimization agent — best for trending markets."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.drl.base_drl_agent import MantisDRLAgent, HAS_SB3
from src.drl.schemas import DRLConfig

if HAS_SB3:
    from stable_baselines3 import PPO  # noqa: F401


class PPOAgent(MantisDRLAgent):
    """
    PPO agent for trending market regimes.

    Proximal Policy Optimization is an on-policy algorithm well-suited for
    trending environments where the agent can exploit momentum signals.
    Works with both Discrete and Box action spaces.
    """

    algorithm_name = "PPO"
    best_regime = ["TRENDING_UP", "TRENDING_DOWN"]

    DEFAULT_CONFIG: dict[str, Any] = {
        "learning_rate": 3e-4,
        "n_steps": 2048,
        "batch_size": 64,
        "n_epochs": 10,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_range": 0.2,
        "ent_coef": 0.01,
    }

    def _create_model(self) -> Any:
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 is required for PPOAgent")
        params = {**self.DEFAULT_CONFIG, **(self._config.extra_params or {})}
        logger.debug(f"[PPO] Creating model with params={list(params.keys())}")
        return PPO(
            policy=self._config.policy,
            env=self._env,
            verbose=0,
            **params,
        )

    def _load_model(self, path: str) -> Any:
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 is required for PPOAgent")
        return PPO.load(path, env=self._env)
