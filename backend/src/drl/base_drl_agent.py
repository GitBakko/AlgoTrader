# MANTIS-EVOLUTION: DRL Base Agent ABC
"""Abstract base class for all DRL agents in the ensemble."""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from src.drl.schemas import DRLConfig, PerformanceMetrics, PerformanceSnapshot, TrainingResult

try:
    import gymnasium as gym  # noqa: F401
    from stable_baselines3.common.base_class import BaseAlgorithm  # noqa: F401
    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False


class MantisDRLAgent(ABC):
    """
    Abstract base for DRL ensemble agents.
    Wraps stable-baselines3 algorithms with a unified interface.
    """

    algorithm_name: str = "BASE"
    best_regime: list[str] = []

    def __init__(self, env: Any, config: DRLConfig | None = None) -> None:
        self._env = env
        self._config = config or DRLConfig()
        self._model: Any = None  # BaseAlgorithm instance when trained
        self._performance_history: list[PerformanceSnapshot] = []
        self._is_trained = False

    # ------------------------------------------------------------------
    # Abstract interface — each concrete agent must implement both
    # ------------------------------------------------------------------

    @abstractmethod
    def _create_model(self) -> Any:
        """Create the SB3 model instance. Implemented by each agent."""
        ...

    @abstractmethod
    def _load_model(self, path: str) -> Any:
        """Load the SB3 model from path. Implemented by each agent."""
        ...

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, total_timesteps: int | None = None) -> TrainingResult:
        """Train the model for the given number of timesteps."""
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 required for DRL training")

        steps = total_timesteps or self._config.total_timesteps

        if self._model is None:
            self._model = self._create_model()

        start = time.time()
        try:
            self._model.learn(total_timesteps=steps)
            self._is_trained = True
            elapsed = time.time() - start

            return TrainingResult(
                algorithm=self.algorithm_name,
                total_timesteps=steps,
                training_time_seconds=elapsed,
                converged=True,
            )
        except Exception as exc:
            logger.warning(f"[{self.algorithm_name}] Training failed: {exc!r}")
            return TrainingResult(
                algorithm=self.algorithm_name,
                total_timesteps=steps,
                training_time_seconds=time.time() - start,
                converged=False,
            )

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, observation: np.ndarray, deterministic: bool = True) -> tuple[int, dict]:
        """
        Predict an action from the given observation.

        Returns:
            (action, info_dict) where action is 0=HOLD, 1=BUY, 2=SELL.
            If the model is untrained, returns (0, {"confidence": 0.0}).
        """
        if self._model is None:
            return 0, {"confidence": 0.0}  # HOLD

        action, _states = self._model.predict(observation, deterministic=deterministic)
        return int(action), {"confidence": 0.7 if deterministic else 0.5}

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Serialize model and metadata to disk."""
        if self._model is None:
            raise ValueError("No model to save — train first")

        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._model.save(str(path))

        meta: dict[str, Any] = {
            "algorithm": self.algorithm_name,
            "best_regime": self.best_regime,
            "is_trained": self._is_trained,
        }
        meta_path = path.with_suffix(".meta.json")
        with open(meta_path, "w") as fh:
            json.dump(meta, fh)

        logger.info(f"[{self.algorithm_name}] Model saved to {path}")

    def load(self, path: str | Path) -> None:
        """Load model from disk and mark as trained."""
        if not HAS_SB3:
            raise RuntimeError("stable-baselines3 required")

        path = Path(path)
        self._model = self._load_model(str(path))
        self._is_trained = True
        logger.info(f"[{self.algorithm_name}] Model loaded from {path}")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_trained(self) -> bool:
        """True once the model has been trained or loaded."""
        return self._is_trained

    @property
    def performance_history(self) -> list[PerformanceSnapshot]:
        """Ordered list of performance snapshots recorded during training."""
        return list(self._performance_history)
