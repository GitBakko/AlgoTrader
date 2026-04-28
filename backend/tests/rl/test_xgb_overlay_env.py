"""Tests for the Phase 5-bis XGBOverlayEnv wrapper."""

from __future__ import annotations

import numpy as np
import pytest

from src.rl.environment import MantisRLEnvironment
from src.rl.schemas import RLAction, RLConfig
from src.rl.xgb_overlay_env import XGBOverlayEnv


@pytest.fixture()
def small_env() -> tuple[MantisRLEnvironment, np.ndarray, np.ndarray]:
    """Build a tiny env with deterministic prices."""
    n = 60
    rng = np.random.default_rng(42)
    features = rng.standard_normal((n, 4)).astype(np.float32)
    # Up-trending prices so XGB BUY signals capture positive baseline.
    prices = 100.0 + np.linspace(0, 5, n) + rng.normal(0, 0.05, n)
    config = RLConfig(total_timesteps=1000)
    env = MantisRLEnvironment(features, prices, config)
    return env, features, prices


def test_overlay_baseline_positive_on_uptrend(small_env):
    inner, _, _ = small_env
    n = inner.n_candles
    # Constant BUY signal: baseline should accumulate positive P&L.
    xgb_signals = np.full(n, 2, dtype=np.int32)  # 2=BUY per SignalClass
    overlay = XGBOverlayEnv(inner, xgb_signals)

    step_pnl, cum_pnl = overlay.baseline_pnl
    assert step_pnl.shape == (n,)
    assert cum_pnl.shape == (n,)
    assert cum_pnl[-1] > 0, "Constant BUY on uptrend must yield positive cumulative"


def test_overlay_baseline_negative_on_uptrend_short(small_env):
    inner, _, _ = small_env
    n = inner.n_candles
    xgb_signals = np.full(n, 0, dtype=np.int32)  # 0=SELL
    overlay = XGBOverlayEnv(inner, xgb_signals)
    _, cum_pnl = overlay.baseline_pnl
    assert cum_pnl[-1] < 0, "Constant SHORT on uptrend must yield negative cumulative"


def test_overlay_step_returns_marginal_reward(small_env):
    inner, _, _ = small_env
    n = inner.n_candles
    xgb_signals = np.full(n, 2, dtype=np.int32)
    overlay = XGBOverlayEnv(inner, xgb_signals)

    overlay.reset()
    obs, reward, terminated, truncated, info = overlay.step(int(RLAction.LONG_ENTRY))
    # Reward field present and finite
    assert np.isfinite(reward)
    assert "raw_reward" in info
    assert "xgb_step_pnl" in info
    assert "xgb_cumulative_pnl" in info


def test_overlay_state_synced_after_step(small_env):
    inner, _, _ = small_env
    n = inner.n_candles
    xgb_signals = np.full(n, 2, dtype=np.int32)
    overlay = XGBOverlayEnv(inner, xgb_signals)
    overlay.reset()
    # Step a few times to give the baseline cumulative a chance to move
    # past bar 0 (where XGB just flipped flat -> long, pnl still 0).
    for _ in range(5):
        overlay.step(int(RLAction.NEUTRAL))
    state = overlay.state
    assert state.xgb_cumulative_pnl != 0.0


def test_overlay_signal_length_mismatch_raises(small_env):
    inner, _, _ = small_env
    bad_signals = np.full(inner.n_candles - 5, 2, dtype=np.int32)
    with pytest.raises(ValueError, match="xgb_signals length"):
        XGBOverlayEnv(inner, bad_signals)


def test_overlay_action_observation_spaces_forwarded(small_env):
    inner, _, _ = small_env
    n = inner.n_candles
    xgb_signals = np.full(n, 1, dtype=np.int32)  # HOLD baseline
    overlay = XGBOverlayEnv(inner, xgb_signals)
    # gymnasium attributes only present when gymnasium is importable
    if hasattr(inner, "action_space"):
        assert overlay.action_space is inner.action_space
    if hasattr(inner, "observation_space"):
        assert overlay.observation_space is inner.observation_space
