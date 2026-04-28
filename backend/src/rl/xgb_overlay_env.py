# MANTIS-EVOLUTION: Phase 5-bis · XGBoost-overlay RL Environment
"""Wrapper around `MantisRLEnvironment` that injects XGBoost baseline P&L.

Use case: train a PPO agent whose reward is the *marginal* P&L over the
XGBoost director's per-step P&L stream, not its standalone P&L.  This
addresses the Phase 5 PoC failure mode where strict concordance ensemble
killed too many XGBoost winners — the agent had no incentive to mostly
agree with XGBoost and only deviate when its own signal was strong.

The wrapper:
  1. Pre-computes the XGBoost baseline cumulative-P&L stream at init.
  2. Forwards every `reset` / `step` to the inner env.
  3. After each step, populates `state.xgb_step_pnl` and
     `state.xgb_cumulative_pnl` so the `xgb_marginal_reward` can
     compute the marginal delta.
  4. Re-computes the reward via `MantisRewardCalculator.xgb_marginal_reward`
     and returns it in place of the inner env's raw reward.

See `docs/reports/2026-04-28_phase5_rl_ensemble_eval.md` §Phase 5-bis
for the rationale.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from loguru import logger

from src.rl.environment import MantisRLEnvironment
from src.rl.reward_functions import MantisRewardCalculator
from src.rl.schemas import RLConfig


class XGBOverlayEnv:
    """Wrap `MantisRLEnvironment` with XGB-baseline reward shaping.

    Parameters
    ----------
    inner: MantisRLEnvironment
        The base environment instance (already constructed with features
        and prices).  Its action space and observation space are
        re-exposed verbatim so stable-baselines3 can introspect them.
    xgb_signals: 1-D int array of length n_candles
        The XGBoost director's per-bar signal: 0=SELL, 1=HOLD, 2=BUY
        (matching `src.models.schemas.SignalClass`).  Used to construct
        the baseline P&L stream.
    config: RLConfig | None
        If given, overrides the inner env's config for the marginal
        reward scaling.  When None, the inner env's config is reused.

    Notes
    -----
    The baseline P&L is computed assuming the XGBoost director enters a
    full-size position on each non-HOLD bar and exits on direction
    flip / HOLD.  This matches the Phase 3 backtest convention.
    """

    def __init__(
        self,
        inner: MantisRLEnvironment,
        xgb_signals: np.ndarray,
        config: RLConfig | None = None,
    ) -> None:
        self._inner = inner
        self._config = config or inner.config
        self._reward_calc = MantisRewardCalculator(self._config)

        if len(xgb_signals) != inner.n_candles:
            raise ValueError(
                f"xgb_signals length {len(xgb_signals)} != n_candles {inner.n_candles}"
            )
        self._xgb_signals = np.asarray(xgb_signals, dtype=np.int32)

        # Pre-compute per-bar baseline step / cumulative P&L (fraction).
        self._xgb_step_pnl, self._xgb_cum_pnl = self._compute_baseline_pnl(
            self._xgb_signals, inner.prices,
        )

        # Re-expose gym attributes for SB3.
        if hasattr(inner, "action_space"):
            self.action_space = inner.action_space
        if hasattr(inner, "observation_space"):
            self.observation_space = inner.observation_space
        self.metadata = getattr(inner, "metadata", {"render_modes": []})

    # ------------------------------------------------------------------
    # Baseline P&L pre-computation
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_baseline_pnl(
        xgb_signals: np.ndarray, prices: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Replay the XGBoost director and return (step_pnl, cumulative_pnl)."""
        n = len(prices)
        step_pnl = np.zeros(n, dtype=np.float64)
        cum_pnl = np.zeros(n, dtype=np.float64)

        position = 0  # -1 short, 0 flat, 1 long
        entry_price = 0.0
        cumulative = 0.0

        for i in range(n - 1):
            sig = int(xgb_signals[i])
            price = float(prices[i])
            next_price = float(prices[i + 1])

            # Open / flip on signal
            desired = 0
            if sig == 2:  # BUY -> long
                desired = 1
            elif sig == 0:  # SELL -> short
                desired = -1
            else:  # HOLD -> close any open trade
                desired = 0

            if desired != position:
                # Close existing trade (if any) realising P&L
                if position != 0 and entry_price > 0:
                    realised = (
                        (price - entry_price) / entry_price
                        if position == 1
                        else (entry_price - price) / entry_price
                    )
                    cumulative += realised
                    step_pnl[i] = realised
                position = desired
                entry_price = price if desired != 0 else 0.0
            else:
                # Holding: mark-to-market unrealised step P&L
                if position != 0 and entry_price > 0:
                    bar_return = (
                        (next_price - price) / entry_price
                        if position == 1
                        else (price - next_price) / entry_price
                    )
                    step_pnl[i] = bar_return
                    cumulative += bar_return
            cum_pnl[i] = cumulative

        # Last bar — close open trade at last price
        if position != 0 and entry_price > 0:
            last_price = float(prices[-1])
            realised = (
                (last_price - entry_price) / entry_price
                if position == 1
                else (entry_price - last_price) / entry_price
            )
            cumulative += realised
            step_pnl[-1] = realised
        cum_pnl[-1] = cumulative

        return step_pnl, cum_pnl

    # ------------------------------------------------------------------
    # Gym interface forwarding
    # ------------------------------------------------------------------

    def reset(self, seed: int | None = None, options: dict | None = None):
        return self._inner.reset(seed=seed, options=options)

    def step(self, action: int):
        obs, _raw_reward, terminated, truncated, info = self._inner.step(action)

        # Sync baseline values into env state.
        step_idx = min(self._inner._current_step - 1, len(self._xgb_step_pnl) - 1)
        if step_idx < 0:
            step_idx = 0
        self._inner._state.xgb_step_pnl = float(self._xgb_step_pnl[step_idx])
        self._inner._state.xgb_cumulative_pnl = float(self._xgb_cum_pnl[step_idx])

        # Compute marginal reward.
        reward = self._reward_calc.xgb_marginal_reward(self._inner._state)

        info["xgb_step_pnl"] = self._inner._state.xgb_step_pnl
        info["xgb_cumulative_pnl"] = self._inner._state.xgb_cumulative_pnl
        info["raw_reward"] = float(_raw_reward)
        return obs, reward, terminated, truncated, info

    def render(self):
        return self._inner.render()

    def close(self):
        return self._inner.close()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self):
        return self._inner.state

    @property
    def n_candles(self) -> int:
        return self._inner.n_candles

    @property
    def features(self) -> np.ndarray:
        return self._inner.features

    @property
    def prices(self) -> np.ndarray:
        return self._inner.prices

    @property
    def baseline_pnl(self) -> tuple[np.ndarray, np.ndarray]:
        """Return the pre-computed (step_pnl, cumulative_pnl) arrays."""
        return self._xgb_step_pnl, self._xgb_cum_pnl


def __getattr__(name: str) -> Any:
    if name == "logger":
        return logger
    raise AttributeError(name)
