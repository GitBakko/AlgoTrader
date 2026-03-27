# MANTIS-EVOLUTION: RL Trading Environment
"""Custom gymnasium environment for MANTIS RL trading."""

from __future__ import annotations

import numpy as np
from loguru import logger

from src.rl.schemas import EnvState, RLAction, RLConfig

try:
    import gymnasium as gym
    from gymnasium import spaces

    HAS_GYMNASIUM = True
except ImportError:
    HAS_GYMNASIUM = False
    # Provide stubs for type checking
    gym = None  # type: ignore
    spaces = None  # type: ignore


# ---------------------------------------------------------------------------
# Base class selection — Gym Env when available, plain object otherwise
# ---------------------------------------------------------------------------

if HAS_GYMNASIUM:
    _BaseEnv = gym.Env  # type: ignore
else:

    class _BaseEnv:  # type: ignore
        """Minimal stub so MantisRLEnvironment can inherit from something."""

        pass


class MantisRLEnvironment(_BaseEnv):
    """
    RL Environment for MANTIS trading.

    Actions: 5 discrete (LONG_ENTRY, LONG_EXIT, SHORT_ENTRY, SHORT_EXIT, NEUTRAL)

    Observation: [feature_vector, current_profit, position, trade_duration, volatility_regime]

    If gymnasium is installed, this is a proper gym.Env subclass with action_space and
    observation_space attributes.  If not, it still works as a standalone environment
    with the same step/reset interface.
    """

    metadata = {"render_modes": []}

    def __init__(
        self,
        features: np.ndarray,
        prices: np.ndarray,
        config: RLConfig | None = None,
    ) -> None:
        """
        Args:
            features: 2-D array of shape (n_candles, n_features) — normalised features.
            prices:   1-D array of close prices, same length as features.
            config:   RL configuration.  Defaults to RLConfig() when None.
        """
        if HAS_GYMNASIUM:
            super().__init__()

        self.config: RLConfig = config or RLConfig()

        # Data
        self.features: np.ndarray = np.asarray(features, dtype=np.float32)
        self.prices: np.ndarray = np.asarray(prices, dtype=np.float64)
        self.n_candles: int = len(prices)
        self.n_features: int = self.features.shape[1] if self.features.ndim == 2 else 1

        # Observation = features + [current_profit, position, trade_duration, vol_regime]
        self.obs_size: int = self.n_features + 4

        # Gym spaces (only when gymnasium is available)
        if HAS_GYMNASIUM:
            self.action_space = spaces.Discrete(5)
            self.observation_space = spaces.Box(
                low=-np.inf,
                high=np.inf,
                shape=(self.obs_size,),
                dtype=np.float32,
            )

        # Episode state
        self._state: EnvState = EnvState()
        self._current_step: int = 0
        self._done: bool = False

    # ------------------------------------------------------------------
    # Public gym interface
    # ------------------------------------------------------------------

    def reset(self, seed: int | None = None, options: dict | None = None):  # type: ignore[override]
        """Reset environment to the start of a new episode.

        Returns:
            (observation, info) — gymnasium-style tuple.
        """
        if HAS_GYMNASIUM and seed is not None:
            super().reset(seed=seed)

        self._current_step = 0
        self._done = False
        self._state = EnvState()

        obs = self._get_observation()
        info: dict = {"step": 0}
        return obs, info

    def step(self, action: int):  # type: ignore[override]
        """Execute one environment step.

        Args:
            action: integer in [0, 4] corresponding to RLAction values.

        Returns:
            (observation, reward, terminated, truncated, info)
        """
        if self._done:
            raise RuntimeError("Episode is done. Call reset().")

        action = int(action)
        price = float(self.prices[self._current_step])

        # Apply trading action and collect immediate reward
        reward = self._apply_action(action, price)

        # Advance time step
        self._current_step += 1

        # Determine episode termination
        terminated = False
        truncated = False

        if self._current_step >= self.n_candles - 1:
            # Ran out of data
            truncated = True
            self._done = True

        if self._state.max_drawdown > self.config.max_drawdown_pct:
            # Drawdown limit breached
            terminated = True
            self._done = True
            reward -= 1.0  # penalty

        if self._state.total_trades >= self.config.max_trades_per_session:
            # Trade budget exhausted
            truncated = True
            self._done = True

        obs = (
            self._get_observation() if not self._done else np.zeros(self.obs_size, dtype=np.float32)
        )

        info: dict = {
            "step": self._current_step,
            "position": self._state.position,
            "total_trades": self._state.total_trades,
            "cumulative_pnl": self._state.cumulative_pnl,
        }

        return obs, reward, terminated, truncated, info

    def render(self):  # noqa: D102
        pass

    def close(self):  # noqa: D102
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _apply_action(self, action: int, price: float) -> float:
        """Apply a trading action and return an immediate scalar reward."""
        reward = 0.0

        if action == RLAction.LONG_ENTRY and self._state.position == 0:
            # ── Open long ─────────────────────────────────────────────
            self._state.position = 1
            self._state.entry_price = price
            self._state.trade_duration = 0
            logger.debug("RL LONG_ENTRY @ {:.4f}", price)

        elif action == RLAction.LONG_EXIT and self._state.position == 1:
            # ── Close long ────────────────────────────────────────────
            pnl = (price - self._state.entry_price) / self._state.entry_price
            reward = pnl
            self._close_position(pnl)
            logger.debug("RL LONG_EXIT @ {:.4f}  pnl={:.4f}", price, pnl)

        elif action == RLAction.SHORT_ENTRY and self._state.position == 0:
            # ── Open short ────────────────────────────────────────────
            self._state.position = -1
            self._state.entry_price = price
            self._state.trade_duration = 0
            logger.debug("RL SHORT_ENTRY @ {:.4f}", price)

        elif action == RLAction.SHORT_EXIT and self._state.position == -1:
            # ── Close short ───────────────────────────────────────────
            pnl = (self._state.entry_price - price) / self._state.entry_price
            reward = pnl
            self._close_position(pnl)
            logger.debug("RL SHORT_EXIT @ {:.4f}  pnl={:.4f}", price, pnl)

        # ── Update unrealised P&L and trade duration ──────────────────
        if self._state.position != 0:
            self._state.trade_duration += 1
            if self._state.position == 1:
                self._state.current_profit = (
                    price - self._state.entry_price
                ) / self._state.entry_price
            else:  # short
                self._state.current_profit = (
                    self._state.entry_price - price
                ) / self._state.entry_price
        else:
            self._state.current_profit = 0.0

        # ── Update running max-drawdown ────────────────────────────────
        peak = max(self._state.cumulative_pnl, 0.0)
        drawdown = peak - self._state.cumulative_pnl
        if drawdown > self._state.max_drawdown:
            self._state.max_drawdown = drawdown

        return reward

    def _close_position(self, pnl: float) -> None:
        """Shared bookkeeping when a position is closed."""
        self._state.cumulative_pnl += pnl
        self._state.total_trades += 1
        if pnl > 0:
            self._state.wins += 1
        else:
            self._state.losses += 1
        self._state.returns_history.append(pnl)
        self._state.position = 0
        self._state.entry_price = 0.0
        self._state.trade_duration = 0

    def _get_observation(self) -> np.ndarray:
        """Build observation vector: [features, current_profit, position, trade_duration, vol_regime]."""
        if self._current_step >= self.n_candles:
            return np.zeros(self.obs_size, dtype=np.float32)

        feature_row = self.features[self._current_step].astype(np.float32)
        extra = np.array(
            [
                self._state.current_profit,
                float(self._state.position),
                float(self._state.trade_duration),
                float(self._state.volatility_regime),
            ],
            dtype=np.float32,
        )
        return np.concatenate([feature_row, extra])

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def state(self) -> EnvState:
        """Current episode state snapshot."""
        return self._state
