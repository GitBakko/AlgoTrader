# MANTIS-EVOLUTION: DRL base agent + schema tests
"""TDD tests for DRL schemas and MantisDRLAgent — run before implementation."""
from __future__ import annotations

import pytest
import numpy as np

from src.drl.schemas import (
    DRLConfig,
    TrainingResult,
    PerformanceMetrics,
    PerformanceSnapshot,
    DRLEnsembleSignal,
    ComparisonReport,
    BacktestConfig,
    BacktestResult,
)


# ---------------------------------------------------------------------------
# Minimal concrete subclass for testing the ABC
# ---------------------------------------------------------------------------

def _make_dummy_agent():
    """Import and build a DummyDRLAgent with CartPole env."""
    import gymnasium as gym
    from src.drl.base_drl_agent import MantisDRLAgent

    class DummyDRLAgent(MantisDRLAgent):
        algorithm_name = "DUMMY"
        best_regime = ["TEST"]

        def _create_model(self):
            from stable_baselines3 import PPO
            return PPO("MlpPolicy", self._env, verbose=0)

        def _load_model(self, path: str):
            from stable_baselines3 import PPO
            return PPO.load(path, env=self._env)

    env = gym.make("CartPole-v1")
    return DummyDRLAgent(env)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestDRLSchemas:

    def test_schema_drl_config(self):
        """DRLConfig creation with defaults."""
        cfg = DRLConfig()
        assert cfg.algorithm == "PPO"
        assert cfg.policy == "MlpPolicy"
        assert cfg.learning_rate == pytest.approx(3e-4)
        assert cfg.total_timesteps == 50000
        assert cfg.gamma == pytest.approx(0.99)
        assert cfg.extra_params == {}

    def test_schema_drl_config_custom(self):
        """DRLConfig accepts custom values."""
        cfg = DRLConfig(algorithm="SAC", total_timesteps=10000, extra_params={"n_steps": 128})
        assert cfg.algorithm == "SAC"
        assert cfg.total_timesteps == 10000
        assert cfg.extra_params == {"n_steps": 128}

    def test_schema_training_result(self):
        """TrainingResult creation with defaults."""
        result = TrainingResult(algorithm="PPO", total_timesteps=50000)
        assert result.algorithm == "PPO"
        assert result.total_timesteps == 50000
        assert result.training_time_seconds == pytest.approx(0.0)
        assert result.final_reward == pytest.approx(0.0)
        assert result.converged is False
        assert result.model_path is None

    def test_schema_training_result_converged(self):
        """TrainingResult with converged=True and model_path."""
        result = TrainingResult(
            algorithm="SAC",
            total_timesteps=100000,
            training_time_seconds=42.5,
            converged=True,
            model_path="/tmp/model.zip",
        )
        assert result.converged is True
        assert result.model_path == "/tmp/model.zip"
        assert result.training_time_seconds == pytest.approx(42.5)

    def test_schema_performance_metrics(self):
        """PerformanceMetrics defaults are all zero."""
        metrics = PerformanceMetrics()
        assert metrics.sharpe_ratio == pytest.approx(0.0)
        assert metrics.sortino_ratio == pytest.approx(0.0)
        assert metrics.calmar_ratio == pytest.approx(0.0)
        assert metrics.max_drawdown == pytest.approx(0.0)
        assert metrics.win_rate == pytest.approx(0.0)
        assert metrics.profit_factor == pytest.approx(0.0)
        assert metrics.total_return == pytest.approx(0.0)
        assert metrics.num_trades == 0
        assert metrics.avg_trade_duration_hours == pytest.approx(0.0)

    def test_schema_performance_snapshot(self):
        """PerformanceSnapshot includes timestamp and metrics."""
        snap = PerformanceSnapshot(regime="TRENDING")
        assert snap.regime == "TRENDING"
        assert isinstance(snap.metrics, PerformanceMetrics)
        assert snap.timestamp is not None

    def test_schema_ensemble_signal(self):
        """DRLEnsembleSignal creation with defaults."""
        signal = DRLEnsembleSignal()
        assert signal.action == 0
        assert signal.confidence == pytest.approx(0.5)
        assert signal.contributing_agents == []
        assert signal.regime_match is False
        assert signal.voting_mode == "REGIME_ROUTING"
        assert signal.agent_votes == {}

    def test_schema_ensemble_signal_validation(self):
        """DRLEnsembleSignal confidence is clamped to [0, 1]."""
        signal = DRLEnsembleSignal(action=1, confidence=0.85, contributing_agents=["PPO", "SAC"])
        assert signal.action == 1
        assert signal.confidence == pytest.approx(0.85)
        assert signal.contributing_agents == ["PPO", "SAC"]

    def test_schema_ensemble_signal_invalid_confidence(self):
        """DRLEnsembleSignal rejects confidence outside [0, 1]."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DRLEnsembleSignal(confidence=1.5)
        with pytest.raises(ValidationError):
            DRLEnsembleSignal(confidence=-0.1)

    def test_schema_comparison_report(self):
        """ComparisonReport creation with defaults."""
        report = ComparisonReport()
        assert report.agent_metrics == {}
        assert report.best_by_regime == {}
        assert report.overall_best == ""
        assert report.timestamp is not None

    def test_schema_comparison_report_populated(self):
        """ComparisonReport with agent metrics."""
        metrics = {"PPO": PerformanceMetrics(sharpe_ratio=1.2, win_rate=0.55)}
        report = ComparisonReport(
            agent_metrics=metrics,
            best_by_regime={"TRENDING": "PPO"},
            overall_best="PPO",
        )
        assert report.overall_best == "PPO"
        assert report.best_by_regime["TRENDING"] == "PPO"
        assert report.agent_metrics["PPO"].sharpe_ratio == pytest.approx(1.2)

    def test_schema_backtest_config(self):
        """BacktestConfig defaults."""
        cfg = BacktestConfig()
        assert cfg.initial_balance == pytest.approx(10000.0)
        assert cfg.commission_pct == pytest.approx(0.001)
        assert cfg.slippage_pct == pytest.approx(0.0005)
        assert cfg.max_position_size == pytest.approx(1.0)
        assert cfg.use_ensemble is True

    def test_schema_backtest_result(self):
        """BacktestResult creation with defaults."""
        result = BacktestResult()
        assert isinstance(result.config, BacktestConfig)
        assert isinstance(result.metrics, PerformanceMetrics)
        assert result.equity_curve == []
        assert result.trades == []
        assert result.benchmark_return == pytest.approx(0.0)
        assert result.agent_returns == {}


# ---------------------------------------------------------------------------
# Base agent tests
# ---------------------------------------------------------------------------

class TestMantisDRLAgentBase:

    def test_base_agent_is_abstract(self):
        """MantisDRLAgent cannot be instantiated directly (ABC)."""
        import gymnasium as gym
        from src.drl.base_drl_agent import MantisDRLAgent

        env = gym.make("CartPole-v1")
        with pytest.raises(TypeError):
            MantisDRLAgent(env)  # type: ignore[abstract]

    def test_base_agent_predict_untrained(self):
        """predict() without training returns HOLD action (0)."""
        agent = _make_dummy_agent()
        obs = np.zeros(4, dtype=np.float32)  # CartPole has 4-dim obs
        action, info = agent.predict(obs)
        assert action == 0  # HOLD
        assert "confidence" in info
        assert info["confidence"] == pytest.approx(0.0)

    def test_base_agent_save_untrained_raises(self):
        """save() without a trained model raises ValueError."""
        agent = _make_dummy_agent()
        with pytest.raises(ValueError, match="No model to save"):
            agent.save("/tmp/mantis_test_model")

    def test_base_agent_properties(self):
        """is_trained starts as False."""
        agent = _make_dummy_agent()
        assert agent.is_trained is False

    def test_base_agent_algorithm_name(self):
        """algorithm_name is set on the concrete class."""
        agent = _make_dummy_agent()
        assert agent.algorithm_name == "DUMMY"

    def test_base_agent_best_regime(self):
        """best_regime is set on the concrete class."""
        agent = _make_dummy_agent()
        assert agent.best_regime == ["TEST"]

    def test_base_agent_config_default(self):
        """Agent uses default DRLConfig when none provided."""
        agent = _make_dummy_agent()
        assert isinstance(agent._config, DRLConfig)
        assert agent._config.algorithm == "PPO"

    def test_base_agent_config_custom(self):
        """Agent accepts custom DRLConfig."""
        import gymnasium as gym
        from src.drl.base_drl_agent import MantisDRLAgent

        class DummyAgent(MantisDRLAgent):
            algorithm_name = "DUMMY2"
            best_regime = []

            def _create_model(self):
                return None

            def _load_model(self, path):
                return None

        env = gym.make("CartPole-v1")
        cfg = DRLConfig(algorithm="SAC", total_timesteps=1000)
        agent = DummyAgent(env, config=cfg)
        assert agent._config.algorithm == "SAC"
        assert agent._config.total_timesteps == 1000
