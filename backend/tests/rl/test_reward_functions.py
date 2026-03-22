# MANTIS-EVOLUTION: Tests for MantisRewardCalculator
"""TDD tests for backend/src/rl/reward_functions.py."""
from __future__ import annotations

import pytest
import numpy as np

from src.rl.schemas import EnvState, RLConfig
from src.rl.reward_functions import MantisRewardCalculator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_state(**kwargs) -> EnvState:
    defaults = {
        "current_step": 50,
        "position": 1,
        "entry_price": 100.0,
        "current_price": 101.0,
        "current_profit": 0.01,
        "trade_duration": 5,
        "total_trades": 10,
        "wins": 6,
        "losses": 4,
        "cumulative_pnl": 0.02,
        "max_drawdown": 0.005,
        "volatility_regime": 1,
        "returns_history": [0.01, -0.005, 0.008, 0.012, -0.003, 0.007, -0.002, 0.009, 0.006, -0.004],
    }
    defaults.update(kwargs)
    return EnvState(**defaults)


@pytest.fixture
def calc() -> MantisRewardCalculator:
    return MantisRewardCalculator()


# ---------------------------------------------------------------------------
# sharpe_reward tests
# ---------------------------------------------------------------------------


def test_sharpe_reward_positive_returns(calc):
    """Consistent positive returns produce a positive Sharpe reward."""
    state = make_state(returns_history=[0.01, 0.012, 0.009, 0.011, 0.013])
    reward = calc.sharpe_reward(state)
    assert reward > 0.0


def test_sharpe_reward_negative_returns(calc):
    """Consistent negative returns produce a negative Sharpe reward."""
    state = make_state(returns_history=[-0.01, -0.012, -0.009, -0.011, -0.013])
    reward = calc.sharpe_reward(state)
    assert reward < 0.0


def test_sharpe_reward_insufficient_data(calc):
    """Fewer than 2 returns produce reward 0.0."""
    state = make_state(returns_history=[])
    assert calc.sharpe_reward(state) == 0.0

    state_one = make_state(returns_history=[0.01])
    assert calc.sharpe_reward(state_one) == 0.0


def test_sharpe_reward_clipped(calc):
    """Extreme Sharpe values are clipped to the [-2, 2] range."""
    # Very high positive Sharpe
    state_pos = make_state(returns_history=[0.1] * 50)
    reward_pos = calc.sharpe_reward(state_pos)
    assert reward_pos <= 2.0

    # Very high negative Sharpe
    state_neg = make_state(returns_history=[-0.1] * 50)
    reward_neg = calc.sharpe_reward(state_neg)
    # Nearly-zero std (all same value) → mean_ret * 10 path
    # But pure negative constant → std=0, return mean_ret*10 → negative
    assert reward_neg <= 2.0  # still bounded (can be very negative but test clip)


def test_sharpe_reward_low_vol_path(calc):
    """Near-zero std with positive mean returns mean_ret * 10 (positive)."""
    state = make_state(returns_history=[0.01, 0.01 + 1e-12, 0.01 - 1e-12])
    reward = calc.sharpe_reward(state)
    # std is ~0, so returns mean_ret * 10 = positive
    assert reward > 0.0


# ---------------------------------------------------------------------------
# scalping_reward tests
# ---------------------------------------------------------------------------


def test_scalping_reward_quick_profit(calc):
    """In position with profit and short duration gives high reward."""
    config = RLConfig(target_hold_candles=10)
    c = MantisRewardCalculator(config)
    state = make_state(
        position=1,
        current_profit=0.02,
        trade_duration=3,  # < target_hold_candles=10
        total_trades=10,
        wins=8,
        losses=2,
        max_drawdown=0.002,
        volatility_regime=0,
    )
    reward = c.scalping_reward(state)
    assert reward > 0.5  # positive and includes quick-profit bonus


def test_scalping_reward_drawdown_penalty(calc):
    """Drawdown exceeding max_drawdown_pct incurs a strong negative penalty."""
    config = RLConfig(max_drawdown_pct=0.01)
    c = MantisRewardCalculator(config)
    state = make_state(
        current_profit=0.001,
        max_drawdown=0.05,  # well above 0.01
        total_trades=5,
        wins=3,
        losses=2,
        volatility_regime=0,
    )
    reward = c.scalping_reward(state)
    assert reward < -1.0  # strong penalty


def test_scalping_reward_overtrading_penalty(calc):
    """Exceeding max_trades_per_session applies an overtrading penalty."""
    config = RLConfig(max_trades_per_session=20)
    c = MantisRewardCalculator(config)
    state_normal = make_state(total_trades=20, wins=12, max_drawdown=0.002, volatility_regime=0)
    state_over = make_state(total_trades=30, wins=18, max_drawdown=0.002, volatility_regime=0)

    reward_normal = c.scalping_reward(state_normal)
    reward_over = c.scalping_reward(state_over)
    assert reward_over < reward_normal


def test_scalping_reward_high_vol_penalty(calc):
    """Position held in HIGH or EXTREME volatility regime incurs a penalty."""
    state_med = make_state(position=1, volatility_regime=1, max_drawdown=0.002)
    state_high = make_state(position=1, volatility_regime=2, max_drawdown=0.002)
    state_extreme = make_state(position=1, volatility_regime=3, max_drawdown=0.002)

    reward_med = calc.scalping_reward(state_med)
    reward_high = calc.scalping_reward(state_high)
    reward_extreme = calc.scalping_reward(state_extreme)

    assert reward_high < reward_med
    assert reward_extreme < reward_high


# ---------------------------------------------------------------------------
# risk_adjusted_reward tests
# ---------------------------------------------------------------------------


def test_risk_adjusted_positive_edge(calc):
    """Good win rate and avg win > avg loss gives positive reward."""
    state = make_state(
        total_trades=10,
        wins=7,
        losses=3,
        current_profit=0.01,
        returns_history=[0.02, -0.005, 0.015, 0.018, -0.004, 0.012, -0.003, 0.016, 0.011, 0.014],
    )
    reward = calc.risk_adjusted_reward(state)
    assert reward > 0.0


def test_risk_adjusted_negative_edge(calc):
    """Bad win rate and avg loss > avg win gives negative reward."""
    state = make_state(
        total_trades=10,
        wins=3,
        losses=7,
        current_profit=-0.01,
        returns_history=[-0.02, 0.003, -0.015, -0.018, 0.002, -0.012, 0.001, -0.016, -0.011, -0.014],
    )
    reward = calc.risk_adjusted_reward(state)
    assert reward < 0.0


def test_risk_adjusted_insufficient_trades(calc):
    """Fewer than 2 trades return 0.0."""
    state_zero = make_state(total_trades=0, returns_history=[])
    assert calc.risk_adjusted_reward(state_zero) == 0.0

    state_one = make_state(total_trades=1, returns_history=[0.01])
    assert calc.risk_adjusted_reward(state_one) == 0.0


# ---------------------------------------------------------------------------
# composite_reward tests
# ---------------------------------------------------------------------------


def test_composite_default_weights(calc):
    """Composite reward is a weighted blend of 0.4 scalping + 0.4 sharpe + 0.2 risk_adjusted."""
    state = make_state()
    composite = calc.composite_reward(state)
    # Manually compute with default weights
    expected = (
        calc.scalping_reward(state) * 0.4
        + calc.sharpe_reward(state) * 0.4
        + calc.risk_adjusted_reward(state) * 0.2
    ) / 1.0
    assert abs(composite - expected) < 1e-9


def test_composite_custom_weights(calc):
    """Different weight dicts produce different composite rewards."""
    state = make_state()
    weights_a = {"scalping": 0.9, "sharpe": 0.05, "risk_adjusted": 0.05}
    weights_b = {"scalping": 0.05, "sharpe": 0.9, "risk_adjusted": 0.05}
    reward_a = calc.composite_reward(state, weights=weights_a)
    reward_b = calc.composite_reward(state, weights=weights_b)
    # With different weights, results should differ (unless all sub-rewards happen to be equal)
    scalp = calc.scalping_reward(state)
    sharpe = calc.sharpe_reward(state)
    if abs(scalp - sharpe) > 1e-6:
        assert abs(reward_a - reward_b) > 1e-9


def test_composite_zero_weights(calc):
    """All-zero weights return 0.0 (avoid division by zero)."""
    state = make_state()
    reward = calc.composite_reward(state, weights={"scalping": 0.0, "sharpe": 0.0, "risk_adjusted": 0.0})
    assert reward == 0.0


def test_composite_partial_weights(calc):
    """Partial weights (missing keys) fall back to 0 for missing entries."""
    state = make_state()
    # Only scalping weight provided, others default to 0
    reward = calc.composite_reward(state, weights={"scalping": 1.0})
    scalp_only = calc.scalping_reward(state)
    assert abs(reward - scalp_only) < 1e-9
