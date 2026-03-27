# MANTIS-EVOLUTION: SAC DRL Agent
"""Soft Actor-Critic agent — best for ranging and high-volatility markets."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.drl.base_drl_agent import HAS_SB3, MantisDRLAgent

if HAS_SB3:
    from stable_baselines3 import SAC  # noqa: F401


class SACAgent(MantisDRLAgent):
    """
    SAC agent for ranging and high-volatility market regimes.

    Soft Actor-Critic is an off-policy, entropy-regularized algorithm that
    excels in continuous action spaces and stochastic environments. It
    requires a Box (continuous) action space — use Pendulum-v1 or a
    custom continuous trading env.

    NOTE: SAC requires a Box action space. For discrete environments
    (e.g. CartPole-v1), use PPOAgent or A2CAgent instead.
    """

    algorithm_name = "SAC"
    best_regime = ["RANGING", "HIGH_VOLATILITY"]

    DEFAULT_CONFIG: dict[str, Any] = {
        "learning_rate": 3e-4,
        "buffer_size": 100_000,
        "batch_size": 256,
        "tau": 0.005,
        "gamma": 0.99,
        "ent_coef": "auto",
    }

    def _create_model(self) -> Any:
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 is required for SACAgent")
        params = {**self.DEFAULT_CONFIG, **(self._config.extra_params or {})}
        logger.debug(f"[SAC] Creating model with params={list(params.keys())}")
        return SAC(
            policy=self._config.policy,
            env=self._env,
            verbose=0,
            **params,
        )

    def _load_model(self, path: str) -> Any:
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 is required for SACAgent")
        return SAC.load(path, env=self._env)
