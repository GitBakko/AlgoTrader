# MANTIS-EVOLUTION: RL schema contracts
"""
Pydantic v2 models and enums defining the contracts for the MANTIS AI
Reinforcement Learning system.

These schemas are the single source of truth for all RL agent I/O — no
raw dicts allowed across RL module boundaries.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------


class RLAction(IntEnum):
    """5 discrete RL actions."""

    LONG_ENTRY = 0
    LONG_EXIT = 1
    SHORT_ENTRY = 2
    SHORT_EXIT = 3
    NEUTRAL = 4


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class RLConfig(BaseModel):
    """Configuration for the RL system."""

    algorithm: Literal["PPO", "SAC"] = "PPO"
    reward_function: Literal[
        "scalping", "sharpe", "risk_adjusted", "composite", "xgb_marginal"
    ] = "composite"
    reward_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "scalping": 0.4,
            "sharpe": 0.4,
            "risk_adjusted": 0.2,
        }
    )
    sliding_window_size: int = 500
    retrain_interval_minutes: int = 60
    max_trades_per_session: int = 20
    target_hold_candles: int = 10
    max_drawdown_pct: float = 0.01
    learning_rate: float = 3e-4
    total_timesteps: int = 50_000
    # Phase 5-bis: scale factor for the XGB-marginal reward.  Higher values
    # encourage the agent to deviate from the XGBoost director only when the
    # marginal pay-off is large.
    xgb_marginal_scale: float = 5.0


# ---------------------------------------------------------------------------
# Environment state
# ---------------------------------------------------------------------------


class EnvState(BaseModel):
    """Snapshot of RL environment state for reward calculation."""

    current_step: int = 0
    position: int = 0  # -1 short, 0 flat, 1 long
    entry_price: float = 0.0
    current_price: float = 0.0
    current_profit: float = 0.0  # unrealized P&L as fraction
    trade_duration: int = 0  # candles since entry
    total_trades: int = 0
    wins: int = 0
    losses: int = 0
    cumulative_pnl: float = 0.0
    max_drawdown: float = 0.0
    volatility_regime: int = 0  # 0=LOW, 1=MED, 2=HIGH, 3=EXTREME
    returns_history: list[float] = Field(default_factory=list)
    # Phase 5-bis: cumulative XGBoost-baseline P&L for marginal reward
    # shaping.  Populated by the environment caller (XGBOverlayEnv) per
    # step.  Default 0.0 keeps standalone training mode unaffected.
    xgb_cumulative_pnl: float = 0.0
    xgb_step_pnl: float = 0.0


# ---------------------------------------------------------------------------
# RL agent output signal
# ---------------------------------------------------------------------------


class RLSignal(BaseModel):
    """Output from the RL agent for the orchestrator."""

    action: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    model_version: str = ""
    algorithm: str = ""
    raw_action: int = 0  # raw RLAction value
