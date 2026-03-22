"""
Tests for RL schema contracts.

Covers all Pydantic v2 models and enums used by the MANTIS AI
Reinforcement Learning system.
"""

import pytest
from pydantic import ValidationError

from src.rl.schemas import RLAction, RLConfig, EnvState, RLSignal


# ---------------------------------------------------------------------------
# RLAction
# ---------------------------------------------------------------------------

class TestRLAction:
    def test_all_values_exist(self):
        assert RLAction.LONG_ENTRY == 0
        assert RLAction.LONG_EXIT == 1
        assert RLAction.SHORT_ENTRY == 2
        assert RLAction.SHORT_EXIT == 3
        assert RLAction.NEUTRAL == 4

    def test_five_discrete_actions(self):
        assert len(RLAction) == 5

    def test_int_enum_identity(self):
        """RLAction members must be usable as plain ints."""
        assert int(RLAction.LONG_ENTRY) == 0
        assert int(RLAction.NEUTRAL) == 4

    def test_lookup_by_value(self):
        assert RLAction(0) == RLAction.LONG_ENTRY
        assert RLAction(3) == RLAction.SHORT_EXIT

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            RLAction(99)

    def test_names(self):
        names = {a.name for a in RLAction}
        assert names == {"LONG_ENTRY", "LONG_EXIT", "SHORT_ENTRY", "SHORT_EXIT", "NEUTRAL"}


# ---------------------------------------------------------------------------
# RLConfig
# ---------------------------------------------------------------------------

class TestRLConfig:
    def test_default_values(self):
        cfg = RLConfig()
        assert cfg.algorithm == "PPO"
        assert cfg.reward_function == "composite"
        assert cfg.sliding_window_size == 500
        assert cfg.retrain_interval_minutes == 60
        assert cfg.max_trades_per_session == 20
        assert cfg.target_hold_candles == 10
        assert cfg.max_drawdown_pct == pytest.approx(0.01)
        assert cfg.learning_rate == pytest.approx(3e-4)
        assert cfg.total_timesteps == 50_000

    def test_default_reward_weights(self):
        cfg = RLConfig()
        assert "scalping" in cfg.reward_weights
        assert "sharpe" in cfg.reward_weights
        assert "risk_adjusted" in cfg.reward_weights
        assert cfg.reward_weights["scalping"] == pytest.approx(0.4)
        assert cfg.reward_weights["sharpe"] == pytest.approx(0.4)
        assert cfg.reward_weights["risk_adjusted"] == pytest.approx(0.2)

    def test_custom_algorithm(self):
        cfg = RLConfig(algorithm="SAC")
        assert cfg.algorithm == "SAC"

    def test_custom_reward_function(self):
        for rf in ("scalping", "sharpe", "risk_adjusted", "composite"):
            cfg = RLConfig(reward_function=rf)
            assert cfg.reward_function == rf

    def test_invalid_algorithm_rejected(self):
        with pytest.raises(ValidationError):
            RLConfig(algorithm="DQN")

    def test_invalid_reward_function_rejected(self):
        with pytest.raises(ValidationError):
            RLConfig(reward_function="custom_invalid")

    def test_custom_numeric_fields(self):
        cfg = RLConfig(
            sliding_window_size=200,
            retrain_interval_minutes=30,
            max_trades_per_session=10,
            target_hold_candles=5,
            max_drawdown_pct=0.02,
            learning_rate=1e-3,
            total_timesteps=100_000,
        )
        assert cfg.sliding_window_size == 200
        assert cfg.retrain_interval_minutes == 30
        assert cfg.max_trades_per_session == 10
        assert cfg.target_hold_candles == 5
        assert cfg.max_drawdown_pct == pytest.approx(0.02)
        assert cfg.learning_rate == pytest.approx(1e-3)
        assert cfg.total_timesteps == 100_000

    def test_custom_reward_weights(self):
        weights = {"scalping": 0.5, "sharpe": 0.3, "risk_adjusted": 0.2}
        cfg = RLConfig(reward_weights=weights)
        assert cfg.reward_weights["scalping"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# EnvState
# ---------------------------------------------------------------------------

class TestEnvState:
    def test_default_values(self):
        state = EnvState()
        assert state.current_step == 0
        assert state.position == 0
        assert state.entry_price == pytest.approx(0.0)
        assert state.current_price == pytest.approx(0.0)
        assert state.current_profit == pytest.approx(0.0)
        assert state.trade_duration == 0
        assert state.total_trades == 0
        assert state.wins == 0
        assert state.losses == 0
        assert state.cumulative_pnl == pytest.approx(0.0)
        assert state.max_drawdown == pytest.approx(0.0)
        assert state.volatility_regime == 0
        assert state.returns_history == []

    def test_all_position_values(self):
        """position can be -1 (short), 0 (flat), or 1 (long)."""
        for pos in (-1, 0, 1):
            state = EnvState(position=pos)
            assert state.position == pos

    def test_all_volatility_regimes(self):
        """0=LOW, 1=MED, 2=HIGH, 3=EXTREME."""
        for regime in (0, 1, 2, 3):
            state = EnvState(volatility_regime=regime)
            assert state.volatility_regime == regime

    def test_full_creation(self):
        state = EnvState(
            current_step=42,
            position=1,
            entry_price=2350.0,
            current_price=2380.0,
            current_profit=0.0128,
            trade_duration=7,
            total_trades=15,
            wins=10,
            losses=5,
            cumulative_pnl=0.045,
            max_drawdown=0.008,
            volatility_regime=1,
            returns_history=[0.001, -0.002, 0.003],
        )
        assert state.current_step == 42
        assert state.position == 1
        assert state.entry_price == pytest.approx(2350.0)
        assert state.current_price == pytest.approx(2380.0)
        assert state.trade_duration == 7
        assert state.wins == 10
        assert state.losses == 5
        assert len(state.returns_history) == 3

    def test_returns_history_defaults_independent(self):
        """Each EnvState should get its own returns_history list."""
        s1 = EnvState()
        s2 = EnvState()
        s1.returns_history.append(0.01)
        assert s2.returns_history == []


# ---------------------------------------------------------------------------
# RLSignal
# ---------------------------------------------------------------------------

class TestRLSignal:
    def test_valid_buy_signal(self):
        sig = RLSignal(action="BUY", confidence=0.75, raw_action=0)
        assert sig.action == "BUY"
        assert sig.confidence == pytest.approx(0.75)
        assert sig.raw_action == 0

    def test_valid_sell_signal(self):
        sig = RLSignal(action="SELL", confidence=0.60, raw_action=2)
        assert sig.action == "SELL"
        assert sig.confidence == pytest.approx(0.60)

    def test_valid_hold_signal(self):
        sig = RLSignal(action="HOLD", confidence=0.50, raw_action=4)
        assert sig.action == "HOLD"

    def test_all_actions(self):
        for action in ("BUY", "SELL", "HOLD"):
            sig = RLSignal(action=action, confidence=0.5)
            assert sig.action == action

    def test_invalid_action_rejected(self):
        with pytest.raises(ValidationError):
            RLSignal(action="SHORT", confidence=0.5)

    def test_confidence_lower_bound(self):
        sig = RLSignal(action="HOLD", confidence=0.0)
        assert sig.confidence == pytest.approx(0.0)

    def test_confidence_upper_bound(self):
        sig = RLSignal(action="BUY", confidence=1.0)
        assert sig.confidence == pytest.approx(1.0)

    def test_confidence_below_zero_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            RLSignal(action="BUY", confidence=-0.01)
        errors = exc_info.value.errors()
        assert any("confidence" in str(e) for e in errors)

    def test_confidence_above_one_rejected(self):
        with pytest.raises(ValidationError) as exc_info:
            RLSignal(action="BUY", confidence=1.01)
        errors = exc_info.value.errors()
        assert any("confidence" in str(e) for e in errors)

    def test_default_optional_fields(self):
        sig = RLSignal(action="HOLD", confidence=0.5)
        assert sig.model_version == ""
        assert sig.algorithm == ""
        assert sig.raw_action == 0

    def test_full_signal(self):
        sig = RLSignal(
            action="BUY",
            confidence=0.82,
            model_version="ppo_v3",
            algorithm="PPO",
            raw_action=0,
        )
        assert sig.model_version == "ppo_v3"
        assert sig.algorithm == "PPO"


# ---------------------------------------------------------------------------
# Config settings integration (env-based)
# ---------------------------------------------------------------------------

class TestSettingsRLSection:
    """Verify RL settings are present in the main Settings object."""

    def test_rl_settings_exist(self):
        from src.utils.config import get_settings
        settings = get_settings()
        assert hasattr(settings, "rl_enabled")
        assert hasattr(settings, "rl_algorithm")
        assert hasattr(settings, "rl_reward_function")
        assert hasattr(settings, "rl_sliding_window_size")
        assert hasattr(settings, "rl_retrain_interval_minutes")
        assert hasattr(settings, "rl_max_trades_per_session")
        assert hasattr(settings, "rl_target_hold_candles")
        assert hasattr(settings, "rl_max_drawdown_pct")
        assert hasattr(settings, "rl_learning_rate")
        assert hasattr(settings, "rl_total_timesteps")

    def test_rl_defaults(self):
        from src.utils.config import get_settings
        settings = get_settings()
        assert settings.rl_enabled is False
        assert settings.rl_algorithm == "PPO"
        assert settings.rl_reward_function == "composite"
        assert settings.rl_sliding_window_size == 500
        assert settings.rl_retrain_interval_minutes == 60
        assert settings.rl_max_trades_per_session == 20
        assert settings.rl_target_hold_candles == 10
        assert settings.rl_max_drawdown_pct == pytest.approx(0.01)
        assert settings.rl_learning_rate == pytest.approx(3e-4)
        assert settings.rl_total_timesteps == 50_000
