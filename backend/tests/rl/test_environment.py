# MANTIS-EVOLUTION: RL Environment Tests
"""
Tests for MantisRLEnvironment.

gymnasium and stable-baselines3 are NOT installed in the venv.
All tests use the standalone step/reset API that works without gymnasium.
"""
from __future__ import annotations

import numpy as np
import pytest

from src.rl.environment import MantisRLEnvironment
from src.rl.schemas import RLAction, RLConfig, EnvState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_env(n_candles: int = 100, n_features: int = 5, base_price: float = 100.0) -> MantisRLEnvironment:
    """Create a simple test environment with rising prices."""
    features = np.random.randn(n_candles, n_features).astype(np.float32)
    prices = np.linspace(base_price, base_price * 1.1, n_candles)
    return MantisRLEnvironment(features=features, prices=prices)


def make_env_flat(n_candles: int = 50, n_features: int = 5, price: float = 100.0) -> MantisRLEnvironment:
    """Environment with flat prices."""
    features = np.zeros((n_candles, n_features), dtype=np.float32)
    prices = np.full(n_candles, price)
    return MantisRLEnvironment(features=features, prices=prices)


# ---------------------------------------------------------------------------
# Test 1: Basic initialization
# ---------------------------------------------------------------------------


def test_init_basic():
    """Creates env with features + prices arrays, correct obs_size."""
    n_candles, n_features = 100, 5
    env = make_env(n_candles=n_candles, n_features=n_features)

    assert env.n_candles == n_candles
    assert env.n_features == n_features
    # obs_size = n_features + 4 extra state values
    assert env.obs_size == n_features + 4
    assert isinstance(env.state, EnvState)


# ---------------------------------------------------------------------------
# Test 2: Reset returns observation
# ---------------------------------------------------------------------------


def test_reset_returns_observation():
    """reset() returns (obs, info) with correct shapes."""
    env = make_env()
    obs, info = env.reset()

    assert isinstance(obs, np.ndarray)
    assert obs.shape == (env.obs_size,)
    assert obs.dtype == np.float32
    assert isinstance(info, dict)
    assert "step" in info
    assert info["step"] == 0


# ---------------------------------------------------------------------------
# Test 3: NEUTRAL action does not open a position
# ---------------------------------------------------------------------------


def test_step_neutral_no_trade():
    """NEUTRAL action doesn't open a position."""
    env = make_env()
    env.reset()

    obs, reward, terminated, truncated, info = env.step(RLAction.NEUTRAL)

    assert env.state.position == 0
    assert reward == 0.0
    assert info["total_trades"] == 0
    assert not terminated
    assert not truncated


# ---------------------------------------------------------------------------
# Test 4: LONG_ENTRY then LONG_EXIT at higher price → positive reward
# ---------------------------------------------------------------------------


def test_long_entry_exit_profit():
    """LONG_ENTRY then LONG_EXIT at higher price yields positive reward."""
    n_candles = 10
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.array([100.0, 110.0] + [110.0] * (n_candles - 2))
    env = MantisRLEnvironment(features=features, prices=prices)
    env.reset()

    # Step 0: enter long at price 100
    obs, r, term, trunc, info = env.step(RLAction.LONG_ENTRY)
    assert env.state.position == 1
    assert r == 0.0  # entry has no immediate reward

    # Step 1: exit long at price 110
    obs, r, term, trunc, info = env.step(RLAction.LONG_EXIT)
    assert env.state.position == 0
    assert r > 0.0, f"Expected positive reward, got {r}"
    expected_pnl = (110.0 - 100.0) / 100.0
    assert abs(r - expected_pnl) < 1e-6


# ---------------------------------------------------------------------------
# Test 5: LONG_ENTRY then LONG_EXIT at lower price → negative reward
# ---------------------------------------------------------------------------


def test_long_entry_exit_loss():
    """LONG_ENTRY then LONG_EXIT at lower price yields negative reward."""
    n_candles = 10
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.array([100.0, 90.0] + [90.0] * (n_candles - 2))
    # Use a large max_drawdown_pct so the drawdown penalty does NOT fire,
    # letting us assert the raw trade P&L reward precisely.
    config = RLConfig(max_drawdown_pct=1.0)
    env = MantisRLEnvironment(features=features, prices=prices, config=config)
    env.reset()

    env.step(RLAction.LONG_ENTRY)  # enter at 100
    obs, r, term, trunc, info = env.step(RLAction.LONG_EXIT)  # exit at 90

    assert r < 0.0, f"Expected negative reward, got {r}"
    expected_pnl = (90.0 - 100.0) / 100.0
    assert abs(r - expected_pnl) < 1e-6


# ---------------------------------------------------------------------------
# Test 6: SHORT_ENTRY then SHORT_EXIT at lower price → positive reward
# ---------------------------------------------------------------------------


def test_short_entry_exit_profit():
    """SHORT_ENTRY then SHORT_EXIT at lower price yields positive reward."""
    n_candles = 10
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.array([100.0, 90.0] + [90.0] * (n_candles - 2))
    env = MantisRLEnvironment(features=features, prices=prices)
    env.reset()

    env.step(RLAction.SHORT_ENTRY)  # enter short at 100
    obs, r, term, trunc, info = env.step(RLAction.SHORT_EXIT)  # exit short at 90

    assert r > 0.0, f"Expected positive reward, got {r}"
    expected_pnl = (100.0 - 90.0) / 100.0
    assert abs(r - expected_pnl) < 1e-6


# ---------------------------------------------------------------------------
# Test 7: Double entry is ignored
# ---------------------------------------------------------------------------


def test_double_entry_ignored():
    """LONG_ENTRY when already long doesn't open a second position."""
    n_candles = 10
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.linspace(100.0, 110.0, n_candles)
    env = MantisRLEnvironment(features=features, prices=prices)
    env.reset()

    env.step(RLAction.LONG_ENTRY)
    entry_price_first = env.state.entry_price

    # Second LONG_ENTRY should be ignored
    env.step(RLAction.LONG_ENTRY)

    assert env.state.position == 1
    assert env.state.entry_price == entry_price_first  # unchanged


# ---------------------------------------------------------------------------
# Test 8: EXIT when flat is ignored
# ---------------------------------------------------------------------------


def test_exit_when_flat_ignored():
    """LONG_EXIT when flat position → no effect, no error, no trade counted."""
    env = make_env()
    env.reset()

    obs, r, term, trunc, info = env.step(RLAction.LONG_EXIT)

    assert env.state.position == 0
    assert r == 0.0
    assert info["total_trades"] == 0


# ---------------------------------------------------------------------------
# Test 9: Position tracking through entry/exit cycle
# ---------------------------------------------------------------------------


def test_position_tracking():
    """Position updates correctly through a full entry/exit cycle."""
    n_candles = 10
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.linspace(100.0, 110.0, n_candles)
    env = MantisRLEnvironment(features=features, prices=prices)
    env.reset()

    # Start flat
    assert env.state.position == 0

    # Enter long
    env.step(RLAction.LONG_ENTRY)
    assert env.state.position == 1

    # Exit long
    env.step(RLAction.LONG_EXIT)
    assert env.state.position == 0

    # Enter short
    env.step(RLAction.SHORT_ENTRY)
    assert env.state.position == -1

    # Exit short
    env.step(RLAction.SHORT_EXIT)
    assert env.state.position == 0


# ---------------------------------------------------------------------------
# Test 10: Trade count increments on each closed trade
# ---------------------------------------------------------------------------


def test_trade_count_increments():
    """total_trades increments on each completed (closed) trade."""
    n_candles = 20
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.linspace(100.0, 110.0, n_candles)
    env = MantisRLEnvironment(features=features, prices=prices)
    env.reset()

    # First trade
    env.step(RLAction.LONG_ENTRY)
    env.step(RLAction.LONG_EXIT)
    assert env.state.total_trades == 1

    # Second trade
    env.step(RLAction.SHORT_ENTRY)
    env.step(RLAction.SHORT_EXIT)
    assert env.state.total_trades == 2

    # Open position without close — should not count
    env.step(RLAction.LONG_ENTRY)
    assert env.state.total_trades == 2


# ---------------------------------------------------------------------------
# Test 11: Win/loss tracking
# ---------------------------------------------------------------------------


def test_win_loss_tracking():
    """wins and losses count correctly based on P&L of each closed trade."""
    n_candles = 20
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.array([100.0, 110.0, 90.0, 80.0] + [80.0] * (n_candles - 4))
    # Large max_drawdown_pct so drawdown penalty doesn't alter rewards or terminate early
    config = RLConfig(max_drawdown_pct=1.0)
    env = MantisRLEnvironment(features=features, prices=prices, config=config)
    env.reset()

    # Win: long 100 → exit 110
    env.step(RLAction.LONG_ENTRY)   # step 0 @ 100
    env.step(RLAction.LONG_EXIT)    # step 1 @ 110
    assert env.state.wins == 1
    assert env.state.losses == 0

    # Loss: long 90 → exit 80
    env.step(RLAction.LONG_ENTRY)   # step 2 @ 90
    env.step(RLAction.LONG_EXIT)    # step 3 @ 80
    assert env.state.wins == 1
    assert env.state.losses == 1


# ---------------------------------------------------------------------------
# Test 12: Max drawdown tracking
# ---------------------------------------------------------------------------


def test_max_drawdown_tracking():
    """max_drawdown is tracked across trades.

    The implementation computes drawdown as max(cumulative_pnl, 0) - cumulative_pnl
    at each step (not a running high-water mark across trades).

    Sequence:
      - Trade 1 (long  100→110): pnl=+0.10, cumulative=+0.10
        After close: peak = max(0.10, 0)=0.10, dd = 0.10-0.10 = 0.0
      - Trade 2 (long  110→88):  pnl=-0.20, cumulative=-0.10
        After close: peak = max(-0.10, 0)=0.0,  dd = 0.0-(-0.10) = 0.10

    So max_drawdown == 0.10.
    """
    n_candles = 20
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.array([100.0, 110.0, 110.0, 88.0] + [88.0] * (n_candles - 4))
    # Large max_drawdown_pct so we don't hit the termination penalty
    config = RLConfig(max_drawdown_pct=1.0)
    env = MantisRLEnvironment(features=features, prices=prices, config=config)
    env.reset()

    # Win: cumulative_pnl +0.10
    env.step(RLAction.LONG_ENTRY)   # step 0
    env.step(RLAction.LONG_EXIT)    # step 1

    # Loss: cumulative_pnl drops to -0.10
    env.step(RLAction.LONG_ENTRY)   # step 2
    env.step(RLAction.LONG_EXIT)    # step 3

    assert env.state.max_drawdown > 0.0
    # peak=max(-0.10,0)=0, dd=0-(-0.10)=0.10 → max_drawdown=0.10
    expected_dd = 0.10
    assert abs(env.state.max_drawdown - expected_dd) < 1e-5


# ---------------------------------------------------------------------------
# Test 13: Episode ends at data end
# ---------------------------------------------------------------------------


def test_episode_ends_at_data_end():
    """truncated=True when we run out of candles."""
    n_candles = 5
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.linspace(100.0, 105.0, n_candles)
    env = MantisRLEnvironment(features=features, prices=prices)
    env.reset()

    # Step through all candles
    terminated = False
    truncated = False
    for _ in range(n_candles - 1):
        obs, r, terminated, truncated, info = env.step(RLAction.NEUTRAL)

    # Last step should trigger truncation
    assert truncated or terminated, "Episode should have ended"


# ---------------------------------------------------------------------------
# Test 14: Max trades terminates episode
# ---------------------------------------------------------------------------


def test_max_trades_terminates():
    """truncated=True when max_trades_per_session is reached."""
    n_candles = 100
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.linspace(100.0, 110.0, n_candles)
    config = RLConfig(max_trades_per_session=2)
    env = MantisRLEnvironment(features=features, prices=prices, config=config)
    env.reset()

    # Complete 2 trades rapidly
    env.step(RLAction.LONG_ENTRY)
    env.step(RLAction.LONG_EXIT)
    env.step(RLAction.SHORT_ENTRY)
    obs, r, terminated, truncated, info = env.step(RLAction.SHORT_EXIT)

    # After 2 closed trades, episode should be done
    assert truncated or terminated, "Expected episode to end after max_trades reached"


# ---------------------------------------------------------------------------
# Test 15: Observation shape
# ---------------------------------------------------------------------------


def test_observation_shape():
    """obs shape matches obs_size = n_features + 4 at every step."""
    n_features = 7
    env = make_env(n_candles=20, n_features=n_features)
    expected_shape = (n_features + 4,)

    obs, _ = env.reset()
    assert obs.shape == expected_shape, f"reset obs shape: {obs.shape} != {expected_shape}"

    for _ in range(5):
        obs, r, terminated, truncated, info = env.step(RLAction.NEUTRAL)
        if not (terminated or truncated):
            assert obs.shape == expected_shape, f"step obs shape: {obs.shape} != {expected_shape}"


# ---------------------------------------------------------------------------
# Test 16: Step after done raises RuntimeError
# ---------------------------------------------------------------------------


def test_step_after_done_raises():
    """Calling step() after episode is done raises RuntimeError."""
    n_candles = 3
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.linspace(100.0, 103.0, n_candles)
    env = MantisRLEnvironment(features=features, prices=prices)
    env.reset()

    for _ in range(n_candles - 1):
        env.step(RLAction.NEUTRAL)

    with pytest.raises(RuntimeError, match="Episode is done"):
        env.step(RLAction.NEUTRAL)


# ---------------------------------------------------------------------------
# Test 17: Reset clears state
# ---------------------------------------------------------------------------


def test_reset_clears_state():
    """reset() clears all episode state to defaults."""
    n_candles = 10
    features = np.zeros((n_candles, 3), dtype=np.float32)
    prices = np.linspace(100.0, 110.0, n_candles)
    env = MantisRLEnvironment(features=features, prices=prices)
    env.reset()

    # Do some trades to dirty the state
    env.step(RLAction.LONG_ENTRY)
    env.step(RLAction.LONG_EXIT)

    assert env.state.total_trades == 1

    # Reset and verify clean state
    obs, info = env.reset()
    assert env.state.position == 0
    assert env.state.total_trades == 0
    assert env.state.wins == 0
    assert env.state.losses == 0
    assert env.state.cumulative_pnl == 0.0
    assert env.state.max_drawdown == 0.0
    assert env.state.current_profit == 0.0
    assert env.state.trade_duration == 0
    assert env._current_step == 0
