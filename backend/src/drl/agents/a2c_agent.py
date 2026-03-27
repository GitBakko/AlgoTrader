# MANTIS-EVOLUTION: A2C DRL Agent
"""Advantage Actor-Critic agent — best for breakout and high-momentum regimes."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.drl.base_drl_agent import MantisDRLAgent, HAS_SB3
from src.drl.schemas import DRLConfig

if HAS_SB3:
    from stable_baselines3 import A2C  # noqa: F401


class A2CAgent(MantisDRLAgent):
    """
    A2C agent for breakout and high-momentum market regimes.

    Advantage Actor-Critic is a synchronous, deterministic variant of A3C.
    It uses a small n_steps rollout, making it reactive to sudden momentum
    shifts — ideal for breakout and high-momentum market conditions.
    Works with both Discrete and Box action spaces.
    """

    algorithm_name = "A2C"
    best_regime = ["BREAKOUT", "HIGH_MOMENTUM"]

    DEFAULT_CONFIG: dict[str, Any] = {
        "learning_rate": 7e-4,
        "n_steps": 5,
        "gamma": 0.99,
        "gae_lambda": 1.0,
        "ent_coef": 0.01,
    }

    def _create_model(self) -> Any:
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 is required for A2CAgent")
        params = {**self.DEFAULT_CONFIG, **(self._config.extra_params or {})}
        logger.debug(f"[A2C] Creating model with params={list(params.keys())}")
        return A2C(
            policy=self._config.policy,
            env=self._env,
            verbose=0,
            **params,
        )

    def _load_model(self, path: str) -> Any:
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 is required for A2CAgent")
        return A2C.load(path, env=self._env)
