# MANTIS-EVOLUTION: DRL Agent tests (PPO, SAC, A2C, TD3)
"""TDD tests for the four concrete DRL agent wrappers."""
from __future__ import annotations

import pytest
import numpy as np
import gymnasium as gym

from src.drl.schemas import DRLConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def discrete_env():
    """CartPole-v1 — Discrete action space. Compatible with PPO / A2C."""
    env = gym.make("CartPole-v1")
    yield env
    env.close()


@pytest.fixture(scope="module")
def continuous_env():
    """Pendulum-v1 — Box action space. Required for SAC / TD3."""
    env = gym.make("Pendulum-v1")
    yield env
    env.close()


# ---------------------------------------------------------------------------
# PPO Agent Tests
# ---------------------------------------------------------------------------

class TestPPOAgent:

    def test_ppo_algorithm_name(self):
        """PPOAgent.algorithm_name must be 'PPO'."""
        from src.drl.agents.ppo_agent import PPOAgent
        assert PPOAgent.algorithm_name == "PPO"

    def test_ppo_best_regime(self):
        """PPOAgent.best_regime must include TRENDING_UP."""
        from src.drl.agents.ppo_agent import PPOAgent
        assert "TRENDING_UP" in PPOAgent.best_regime

    def test_ppo_default_config_keys(self):
        """PPOAgent.DEFAULT_CONFIG contains expected hyperparameter keys."""
        from src.drl.agents.ppo_agent import PPOAgent
        required_keys = {"learning_rate", "n_steps", "batch_size", "n_epochs",
                         "gamma", "gae_lambda", "clip_range", "ent_coef"}
        assert required_keys.issubset(PPOAgent.DEFAULT_CONFIG.keys())

    def test_ppo_train_smoke(self, discrete_env):
        """PPOAgent trains 200 steps on CartPole without crashing."""
        from src.drl.agents.ppo_agent import PPOAgent
        agent = PPOAgent(discrete_env)
        result = agent.train(total_timesteps=200)
        assert result.converged is True
        assert result.algorithm == "PPO"
        assert result.total_timesteps == 200

    def test_ppo_predict(self, discrete_env):
        """After training, predict returns (int, dict)."""
        from src.drl.agents.ppo_agent import PPOAgent
        agent = PPOAgent(discrete_env)
        agent.train(total_timesteps=200)
        obs, _ = discrete_env.reset()
        action, info = agent.predict(np.array(obs, dtype=np.float32))
        assert isinstance(action, int)
        assert isinstance(info, dict)
        assert "confidence" in info

    def test_ppo_is_trained_after_train(self, discrete_env):
        """is_trained becomes True after training."""
        from src.drl.agents.ppo_agent import PPOAgent
        agent = PPOAgent(discrete_env)
        assert agent.is_trained is False
        agent.train(total_timesteps=200)
        assert agent.is_trained is True

    def test_ppo_save_load_cycle(self, discrete_env, tmp_path):
        """Train, save, load, then predict — full round-trip."""
        from src.drl.agents.ppo_agent import PPOAgent
        model_path = tmp_path / "ppo_test"

        # Train and save
        agent = PPOAgent(discrete_env)
        agent.train(total_timesteps=200)
        agent.save(str(model_path))

        # Load into a fresh agent
        agent2 = PPOAgent(discrete_env)
        agent2.load(str(model_path))
        assert agent2.is_trained is True

        obs, _ = discrete_env.reset()
        action, info = agent2.predict(np.array(obs, dtype=np.float32))
        assert isinstance(action, int)


# ---------------------------------------------------------------------------
# SAC Agent Tests
# ---------------------------------------------------------------------------

class TestSACAgent:

    def test_sac_algorithm_name(self):
        """SACAgent.algorithm_name must be 'SAC'."""
        from src.drl.agents.sac_agent import SACAgent
        assert SACAgent.algorithm_name == "SAC"

    def test_sac_best_regime(self):
        """SACAgent.best_regime must include RANGING."""
        from src.drl.agents.sac_agent import SACAgent
        assert "RANGING" in SACAgent.best_regime

    def test_sac_default_config_keys(self):
        """SACAgent.DEFAULT_CONFIG contains expected hyperparameter keys."""
        from src.drl.agents.sac_agent import SACAgent
        required_keys = {"learning_rate", "buffer_size", "batch_size", "tau",
                         "gamma", "ent_coef"}
        assert required_keys.issubset(SACAgent.DEFAULT_CONFIG.keys())

    def test_sac_train_smoke(self, continuous_env):
        """SACAgent trains 200 steps on Pendulum without crashing."""
        from src.drl.agents.sac_agent import SACAgent
        agent = SACAgent(continuous_env)
        result = agent.train(total_timesteps=200)
        assert result.converged is True
        assert result.algorithm == "SAC"

    def test_sac_predict(self, continuous_env):
        """After training, predict returns (int, dict)."""
        from src.drl.agents.sac_agent import SACAgent
        agent = SACAgent(continuous_env)
        agent.train(total_timesteps=200)
        obs, _ = continuous_env.reset()
        action, info = agent.predict(np.array(obs, dtype=np.float32))
        assert isinstance(action, int)
        assert "confidence" in info


# ---------------------------------------------------------------------------
# A2C Agent Tests
# ---------------------------------------------------------------------------

class TestA2CAgent:

    def test_a2c_algorithm_name(self):
        """A2CAgent.algorithm_name must be 'A2C'."""
        from src.drl.agents.a2c_agent import A2CAgent
        assert A2CAgent.algorithm_name == "A2C"

    def test_a2c_best_regime(self):
        """A2CAgent.best_regime must include BREAKOUT."""
        from src.drl.agents.a2c_agent import A2CAgent
        assert "BREAKOUT" in A2CAgent.best_regime

    def test_a2c_default_config_keys(self):
        """A2CAgent.DEFAULT_CONFIG contains expected hyperparameter keys."""
        from src.drl.agents.a2c_agent import A2CAgent
        required_keys = {"learning_rate", "n_steps", "gamma", "gae_lambda", "ent_coef"}
        assert required_keys.issubset(A2CAgent.DEFAULT_CONFIG.keys())

    def test_a2c_train_smoke(self, discrete_env):
        """A2CAgent trains 200 steps on CartPole without crashing."""
        from src.drl.agents.a2c_agent import A2CAgent
        agent = A2CAgent(discrete_env)
        result = agent.train(total_timesteps=200)
        assert result.converged is True
        assert result.algorithm == "A2C"

    def test_a2c_predict(self, discrete_env):
        """After training, predict returns (int, dict)."""
        from src.drl.agents.a2c_agent import A2CAgent
        agent = A2CAgent(discrete_env)
        agent.train(total_timesteps=200)
        obs, _ = discrete_env.reset()
        action, info = agent.predict(np.array(obs, dtype=np.float32))
        assert isinstance(action, int)
        assert "confidence" in info


# ---------------------------------------------------------------------------
# TD3 Agent Tests
# ---------------------------------------------------------------------------

class TestTD3Agent:

    def test_td3_algorithm_name(self):
        """TD3Agent.algorithm_name must be 'TD3'."""
        from src.drl.agents.td3_agent import TD3Agent
        assert TD3Agent.algorithm_name == "TD3"

    def test_td3_best_regime(self):
        """TD3Agent.best_regime must include LOW_VOLATILITY."""
        from src.drl.agents.td3_agent import TD3Agent
        assert "LOW_VOLATILITY" in TD3Agent.best_regime

    def test_td3_default_config_keys(self):
        """TD3Agent.DEFAULT_CONFIG contains expected hyperparameter keys."""
        from src.drl.agents.td3_agent import TD3Agent
        required_keys = {"learning_rate", "buffer_size", "batch_size", "tau",
                         "gamma", "policy_delay"}
        assert required_keys.issubset(TD3Agent.DEFAULT_CONFIG.keys())

    def test_td3_train_smoke(self, continuous_env):
        """TD3Agent trains 200 steps on Pendulum without crashing."""
        from src.drl.agents.td3_agent import TD3Agent
        agent = TD3Agent(continuous_env)
        result = agent.train(total_timesteps=200)
        assert result.converged is True
        assert result.algorithm == "TD3"

    def test_td3_predict(self, continuous_env):
        """After training, predict returns (int, dict)."""
        from src.drl.agents.td3_agent import TD3Agent
        agent = TD3Agent(continuous_env)
        agent.train(total_timesteps=200)
        obs, _ = continuous_env.reset()
        action, info = agent.predict(np.array(obs, dtype=np.float32))
        assert isinstance(action, int)
        assert "confidence" in info


# ---------------------------------------------------------------------------
# Cross-agent interface tests
# ---------------------------------------------------------------------------

class TestAllAgentsInterface:

    def test_all_agents_share_interface(self, discrete_env, continuous_env):
        """All 4 agents expose train, predict, save, load methods."""
        from src.drl.agents.ppo_agent import PPOAgent
        from src.drl.agents.sac_agent import SACAgent
        from src.drl.agents.a2c_agent import A2CAgent
        from src.drl.agents.td3_agent import TD3Agent

        agents = [
            PPOAgent(discrete_env),
            SACAgent(continuous_env),
            A2CAgent(discrete_env),
            TD3Agent(continuous_env),
        ]
        for agent in agents:
            assert callable(getattr(agent, "train", None))
            assert callable(getattr(agent, "predict", None))
            assert callable(getattr(agent, "save", None))
            assert callable(getattr(agent, "load", None))

    def test_all_agents_have_algorithm_name(self):
        """All 4 agents declare a non-empty algorithm_name class attribute."""
        from src.drl.agents.ppo_agent import PPOAgent
        from src.drl.agents.sac_agent import SACAgent
        from src.drl.agents.a2c_agent import A2CAgent
        from src.drl.agents.td3_agent import TD3Agent

        for cls in (PPOAgent, SACAgent, A2CAgent, TD3Agent):
            assert isinstance(cls.algorithm_name, str)
            assert len(cls.algorithm_name) > 0

    def test_all_agents_have_best_regime(self):
        """All 4 agents declare a non-empty best_regime class attribute."""
        from src.drl.agents.ppo_agent import PPOAgent
        from src.drl.agents.sac_agent import SACAgent
        from src.drl.agents.a2c_agent import A2CAgent
        from src.drl.agents.td3_agent import TD3Agent

        for cls in (PPOAgent, SACAgent, A2CAgent, TD3Agent):
            assert isinstance(cls.best_regime, list)
            assert len(cls.best_regime) > 0

    def test_agents_importable_from_package(self):
        """All 4 agents are importable from src.drl.agents package."""
        from src.drl.agents import PPOAgent, SACAgent, A2CAgent, TD3Agent
        assert PPOAgent.algorithm_name == "PPO"
        assert SACAgent.algorithm_name == "SAC"
        assert A2CAgent.algorithm_name == "A2C"
        assert TD3Agent.algorithm_name == "TD3"

    def test_agents_importable_from_drl_package(self):
        """All 4 agents are importable directly from src.drl."""
        from src.drl import PPOAgent, SACAgent, A2CAgent, TD3Agent
        assert PPOAgent is not None
        assert SACAgent is not None
        assert A2CAgent is not None
        assert TD3Agent is not None

    def test_extra_params_override_defaults(self, discrete_env):
        """extra_params in DRLConfig properly override agent DEFAULT_CONFIG."""
        from src.drl.agents.ppo_agent import PPOAgent
        cfg = DRLConfig(extra_params={"n_steps": 64, "batch_size": 32})
        agent = PPOAgent(discrete_env, config=cfg)
        # Training should complete — verifies extra_params don't break model creation
        result = agent.train(total_timesteps=200)
        assert result.converged is True
