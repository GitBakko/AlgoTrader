# MANTIS-EVOLUTION: TD3 DRL Agent
"""Twin Delayed DDPG agent — best for low-volatility and accumulation regimes."""

from __future__ import annotations

from typing import Any

from loguru import logger

from src.drl.base_drl_agent import MantisDRLAgent, HAS_SB3
from src.drl.schemas import DRLConfig

if HAS_SB3:
    from stable_baselines3 import TD3  # noqa: F401


class TD3Agent(MantisDRLAgent):
    """
    TD3 agent for low-volatility and accumulation market regimes.

    Twin Delayed DDPG addresses overestimation bias in DDPG by using two
    critic networks and delaying policy updates. It is well-suited for
    stable, slow-moving market conditions where precise value estimation
    matters more than exploration.

    NOTE: TD3 requires a Box (continuous) action space — use Pendulum-v1
    or a custom continuous trading env. Not compatible with Discrete spaces.
    """

    algorithm_name = "TD3"
    best_regime = ["LOW_VOLATILITY", "ACCUMULATION"]

    DEFAULT_CONFIG: dict[str, Any] = {
        "learning_rate": 1e-3,
        "buffer_size": 100_000,
        "batch_size": 100,
        "tau": 0.005,
        "gamma": 0.99,
        "policy_delay": 2,
    }

    def _create_model(self) -> Any:
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 is required for TD3Agent")
        params = {**self.DEFAULT_CONFIG, **(self._config.extra_params or {})}
        logger.debug(f"[TD3] Creating model with params={list(params.keys())}")
        return TD3(
            policy=self._config.policy,
            env=self._env,
            verbose=0,
            **params,
        )

    def _load_model(self, path: str) -> Any:
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 is required for TD3Agent")
        return TD3.load(path, env=self._env)
