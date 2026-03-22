# MANTIS-EVOLUTION: Adaptive RL Trainer Tests
"""Tests for MantisAdaptiveTrainer — all SB3 calls are mocked (not installed)."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.rl.schemas import RLConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_trainer(tmp_path: Path, config: RLConfig | None = None):
    """Import and construct trainer fresh to avoid HAS_SB3 caching issues."""
    from src.rl.adaptive_trainer import MantisAdaptiveTrainer

    return MantisAdaptiveTrainer(config=config, model_dir=tmp_path / "rl_models")


# ---------------------------------------------------------------------------
# 1. Initialisation
# ---------------------------------------------------------------------------


def test_init_defaults(tmp_path):
    """Creates trainer with default config; model_dir is created."""
    trainer = make_trainer(tmp_path)
    assert trainer.config is not None
    assert isinstance(trainer.config, RLConfig)
    assert trainer.model_dir.exists()


def test_model_dir_created(tmp_path):
    """model_dir is created even if it didn't exist beforehand."""
    new_dir = tmp_path / "deep" / "nested" / "rl"
    from src.rl.adaptive_trainer import MantisAdaptiveTrainer

    trainer = MantisAdaptiveTrainer(model_dir=new_dir)
    assert new_dir.exists()


# ---------------------------------------------------------------------------
# 2. Model access
# ---------------------------------------------------------------------------


def test_get_current_model_none_initially(tmp_path):
    """No model loaded at startup."""
    trainer = make_trainer(tmp_path)
    assert trainer.get_current_model() is None


def test_set_model_thread_safe(tmp_path):
    """set_model updates internal model and sets a version string."""
    trainer = make_trainer(tmp_path)
    mock_model = MagicMock(name="FakeModel")
    trainer.set_model(mock_model, version="v_test")
    assert trainer.current_model_version == "v_test"


def test_get_model_after_set(tmp_path):
    """get_current_model returns exactly what was set."""
    trainer = make_trainer(tmp_path)
    mock_model = MagicMock(name="FakeModel")
    trainer.set_model(mock_model, version="v1")
    assert trainer.get_current_model() is mock_model


def test_set_model_auto_version(tmp_path):
    """When no version is provided, set_model generates a timestamp version."""
    trainer = make_trainer(tmp_path)
    trainer.set_model(MagicMock(), version="")
    assert trainer.current_model_version != ""


def test_current_model_version(tmp_path):
    """current_model_version reflects the last set_model call."""
    trainer = make_trainer(tmp_path)
    trainer.set_model(MagicMock(), version="alpha")
    trainer.set_model(MagicMock(), version="beta")
    assert trainer.current_model_version == "beta"


# ---------------------------------------------------------------------------
# 3. Background training lifecycle
# ---------------------------------------------------------------------------


def test_start_stop_background(tmp_path):
    """start_background_training creates a thread; stop signals it to exit."""
    trainer = make_trainer(tmp_path)
    trainer.start_background_training()
    assert trainer._training_thread is not None
    assert trainer._training_thread.is_alive()
    trainer.stop_background_training()
    # After stop, thread should no longer be alive (within join timeout)
    assert not trainer._training_thread.is_alive()


def test_training_thread_is_daemon(tmp_path):
    """The background thread is a daemon (won't block process exit)."""
    trainer = make_trainer(tmp_path)
    trainer.start_background_training()
    assert trainer._training_thread.daemon is True
    trainer.stop_background_training()


def test_training_does_not_block_main(tmp_path):
    """start_background_training returns immediately — does not block."""
    trainer = make_trainer(tmp_path)
    t0 = time.monotonic()
    trainer.start_background_training()
    elapsed = time.monotonic() - t0
    trainer.stop_background_training()
    assert elapsed < 1.0, f"start_background_training blocked for {elapsed:.2f}s"


def test_stop_event_stops_loop(tmp_path):
    """Setting _stop_event causes the retrain loop to exit."""
    trainer = make_trainer(tmp_path)
    trainer.start_background_training()
    # Give thread a moment to enter the loop
    time.sleep(0.05)
    trainer.stop_background_training()
    # Thread must have exited within the join(timeout=10)
    assert not trainer._training_thread.is_alive()


def test_double_start_is_ignored(tmp_path):
    """Calling start twice does not spawn a second thread."""
    trainer = make_trainer(tmp_path)
    trainer.start_background_training()
    first_thread = trainer._training_thread
    trainer.start_background_training()  # second call — should be ignored
    assert trainer._training_thread is first_thread
    trainer.stop_background_training()


# ---------------------------------------------------------------------------
# 4. is_training flag
# ---------------------------------------------------------------------------


def test_is_training_flag(tmp_path):
    """is_training is False initially and True during a cycle."""
    trainer = make_trainer(tmp_path)
    assert not trainer.is_training

    # Patch _train_one_cycle to observe the flag mid-execution
    flag_during = []

    def slow_cycle(_data=None):
        flag_during.append(trainer.is_training)
        time.sleep(0.05)

    trainer._train_one_cycle = slow_cycle
    trainer.start_background_training()
    time.sleep(0.15)
    trainer.stop_background_training()
    assert any(flag_during), "is_training was never True during a cycle"


# ---------------------------------------------------------------------------
# 5. train_on_data without SB3
# ---------------------------------------------------------------------------


def test_train_on_data_without_sb3(tmp_path):
    """train_on_data returns False when stable-baselines3 is not available."""
    from src.rl import adaptive_trainer as mod

    original = mod.HAS_SB3
    try:
        mod.HAS_SB3 = False
        trainer = make_trainer(tmp_path)
        features = np.random.randn(100, 10).astype(np.float32)
        prices = np.random.uniform(100, 200, 100).astype(np.float32)
        result = trainer.train_on_data(features, prices)
        assert result is False
    finally:
        mod.HAS_SB3 = original


# ---------------------------------------------------------------------------
# 6. train_on_data WITH SB3 mocked
# ---------------------------------------------------------------------------


def test_train_on_data_with_sb3_mocked(tmp_path):
    """train_on_data creates env, trains model, saves it — all mocked."""
    from src.rl import adaptive_trainer as mod

    mock_model_instance = MagicMock()
    mock_algo_class = MagicMock(return_value=mock_model_instance)
    mock_env = MagicMock()

    with (
        patch.object(mod, "HAS_SB3", True),
        patch.object(mod, "PPO", mock_algo_class, create=True),
        patch("src.rl.adaptive_trainer.MantisRLEnvironment", return_value=mock_env),
    ):
        trainer = make_trainer(tmp_path, config=RLConfig(algorithm="PPO", total_timesteps=100))
        features = np.random.randn(50, 10).astype(np.float32)
        prices = np.random.uniform(100, 200, 50).astype(np.float32)
        result = trainer.train_on_data(features, prices)

    assert result is True
    mock_model_instance.learn.assert_called_once_with(total_timesteps=100)
    mock_model_instance.save.assert_called_once()
    assert trainer.get_current_model() is mock_model_instance


# ---------------------------------------------------------------------------
# 7. load_model
# ---------------------------------------------------------------------------


def test_load_model_without_sb3(tmp_path):
    """load_model returns False when SB3 not available."""
    from src.rl import adaptive_trainer as mod

    original = mod.HAS_SB3
    try:
        mod.HAS_SB3 = False
        trainer = make_trainer(tmp_path)
        assert trainer.load_model(tmp_path / "nonexistent") is False
    finally:
        mod.HAS_SB3 = original


def test_load_model_missing_file(tmp_path):
    """load_model returns False if file does not exist (even with SB3)."""
    from src.rl import adaptive_trainer as mod

    with patch.object(mod, "HAS_SB3", True):
        trainer = make_trainer(tmp_path)
        assert trainer.load_model(tmp_path / "ghost_model") is False


def test_load_model_with_sb3_mocked(tmp_path):
    """load_model loads a model and hot-swaps it."""
    from src.rl import adaptive_trainer as mod

    mock_loaded = MagicMock(name="LoadedModel")
    mock_algo_class = MagicMock()
    mock_algo_class.load = MagicMock(return_value=mock_loaded)

    # Create a fake model file so path.exists() returns True
    fake_path = tmp_path / "rl_ppo_20260101_120000"
    fake_path.mkdir()  # exists() is True

    with (
        patch.object(mod, "HAS_SB3", True),
        patch.object(mod, "PPO", mock_algo_class, create=True),
    ):
        trainer = make_trainer(tmp_path, config=RLConfig(algorithm="PPO"))
        result = trainer.load_model(fake_path)

    assert result is True
    assert trainer.get_current_model() is mock_loaded
