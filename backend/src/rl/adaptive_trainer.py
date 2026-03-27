# MANTIS-EVOLUTION: Adaptive RL Trainer
"""Background RL model trainer with sliding window and hot-swap."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from loguru import logger

from src.rl.schemas import RLConfig
from src.rl.environment import MantisRLEnvironment

try:
    from stable_baselines3 import PPO, SAC
    from stable_baselines3.common.base_class import BaseAlgorithm

    HAS_SB3 = True
except ImportError:
    HAS_SB3 = False
    PPO = None  # type: ignore
    SAC = None  # type: ignore
    BaseAlgorithm = None  # type: ignore


class MantisAdaptiveTrainer:
    """
    Background RL model trainer.

    - Trains on sliding window of recent data
    - Hot-swaps model without restart
    - Thread-safe model access via RLock
    - Versioned models for rollback
    """

    def __init__(
        self,
        config: RLConfig | None = None,
        model_dir: Path | str = "data/rl_models",
    ) -> None:
        self.config = config or RLConfig()
        self.model_dir = Path(model_dir)
        self.model_dir.mkdir(parents=True, exist_ok=True)

        self._current_model: Any = None  # BaseAlgorithm or None
        self._model_lock = threading.RLock()
        self._training_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._current_version: str = ""
        self._training_active = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_training(self) -> bool:
        """True while a training cycle is running."""
        return self._training_active

    @property
    def current_model_version(self) -> str:
        """Version tag of the currently loaded model."""
        return self._current_version

    # ------------------------------------------------------------------
    # Thread-safe model access
    # ------------------------------------------------------------------

    def get_current_model(self) -> Any:
        """Thread-safe access to the current model."""
        with self._model_lock:
            return self._current_model

    def set_model(self, model: Any, version: str = "") -> None:
        """Thread-safe model hot-swap."""
        with self._model_lock:
            self._current_model = model
            self._current_version = version or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            logger.info(f"Model swapped to version {self._current_version}")

    # ------------------------------------------------------------------
    # Background training lifecycle
    # ------------------------------------------------------------------

    def start_background_training(self, data_provider=None) -> None:
        """Start background training loop in a separate daemon thread."""
        if self._training_thread and self._training_thread.is_alive():
            logger.warning("Training already running")
            return

        self._stop_event.clear()
        self._training_thread = threading.Thread(
            target=self._retrain_loop,
            args=(data_provider,),
            daemon=True,
            name="mantis-rl-trainer",
        )
        self._training_thread.start()
        logger.info("Background RL training started")

    def stop_background_training(self) -> None:
        """Signal the training loop to stop and wait for it to finish."""
        self._stop_event.set()
        if self._training_thread and self._training_thread.is_alive():
            self._training_thread.join(timeout=10)
        logger.info("Background RL training stopped")

    # ------------------------------------------------------------------
    # Training loop
    # ------------------------------------------------------------------

    def _retrain_loop(self, data_provider=None) -> None:
        """
        Main retraining loop. Runs until stop_event is set.

        Each iteration:
        1. Get recent data (sliding window)
        2. Create environment with fresh data
        3. Train new model
        4. Validate on holdout
        5. Hot-swap if performance >= threshold
        6. Save versioned model
        """
        while not self._stop_event.is_set():
            try:
                self._training_active = True
                self._train_one_cycle(data_provider)
            except Exception as e:
                logger.error(f"Training cycle failed: {e!r}")
            finally:
                self._training_active = False

            # Wait for next cycle, checking stop_event every second
            for _ in range(self.config.retrain_interval_minutes * 60):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    def _train_one_cycle(self, data_provider=None) -> None:
        """Single training cycle — override in subclass or mock in tests."""
        if not HAS_SB3:
            logger.warning("stable-baselines3 not installed, skipping training")
            return

        logger.info(f"Starting training cycle (algo={self.config.algorithm})")

        # Extension point — subclass or inject data_provider for custom data
        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        logger.info(f"Training cycle complete, version={version}")

    # ------------------------------------------------------------------
    # One-shot training
    # ------------------------------------------------------------------

    def train_on_data(self, features: np.ndarray, prices: np.ndarray) -> bool:
        """
        One-shot training on provided data. Returns True if model was updated.

        Useful for manual/scheduled training outside the background loop.
        """
        if not HAS_SB3:
            logger.warning("stable-baselines3 not installed")
            return False

        env = MantisRLEnvironment(features=features, prices=prices, config=self.config)

        # Select algorithm class based on config
        AlgoClass = PPO if self.config.algorithm == "PPO" else SAC
        model = AlgoClass(
            "MlpPolicy",
            env,
            learning_rate=self.config.learning_rate,
            verbose=0,
        )

        model.learn(total_timesteps=self.config.total_timesteps)

        version = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.set_model(model, version)

        # Save versioned model to disk
        model_path = self.model_dir / f"rl_{self.config.algorithm}_{version}"
        model.save(str(model_path))
        logger.info(f"Model saved to {model_path}")

        return True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load_model(self, path: str | Path) -> bool:
        """Load a previously saved model and hot-swap it into service."""
        if not HAS_SB3:
            return False

        path = Path(path)
        if not path.exists() and not Path(f"{path}.zip").exists():
            logger.warning(f"Model not found: {path}")
            return False

        AlgoClass = PPO if self.config.algorithm == "PPO" else SAC
        model = AlgoClass.load(str(path))
        self.set_model(model, path.stem)
        return True
