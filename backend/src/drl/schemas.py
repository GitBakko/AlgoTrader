# MANTIS-EVOLUTION: DRL Ensemble schema contracts
"""Pydantic models for the DRL Ensemble (Sprint 5)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

import numpy as np  # noqa: F401 — allowed for future array fields


class DRLConfig(BaseModel):
    """Configuration for a DRL agent."""

    algorithm: str = "PPO"
    policy: str = "MlpPolicy"
    learning_rate: float = 3e-4
    total_timesteps: int = 50000
    gamma: float = 0.99
    extra_params: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class TrainingResult(BaseModel):
    """Result of a training run."""

    algorithm: str
    total_timesteps: int
    training_time_seconds: float = 0.0
    final_reward: float = 0.0
    converged: bool = False
    model_path: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class PerformanceMetrics(BaseModel):
    """Performance metrics for a DRL agent."""

    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    total_return: float = 0.0
    num_trades: int = 0
    avg_trade_duration_hours: float = 0.0

    model_config = {"arbitrary_types_allowed": True}


class PerformanceSnapshot(BaseModel):
    """A point-in-time performance snapshot."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metrics: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    regime: str = "UNKNOWN"

    model_config = {"arbitrary_types_allowed": True}


class DRLEnsembleSignal(BaseModel):
    """Output from the DRL ensemble."""

    action: int = 0  # 0=HOLD, 1=BUY, 2=SELL
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    contributing_agents: list[str] = Field(default_factory=list)
    regime_match: bool = False
    voting_mode: str = "REGIME_ROUTING"
    agent_votes: dict[str, int] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class ComparisonReport(BaseModel):
    """Comparative report of all DRL agents."""

    agent_metrics: dict[str, PerformanceMetrics] = Field(default_factory=dict)
    best_by_regime: dict[str, str] = Field(default_factory=dict)  # regime -> best agent name
    overall_best: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"arbitrary_types_allowed": True}


class BacktestConfig(BaseModel):
    """Configuration for DRL backtesting."""

    initial_balance: float = 10000.0
    commission_pct: float = 0.001
    slippage_pct: float = 0.0005
    max_position_size: float = 1.0
    use_ensemble: bool = True

    model_config = {"arbitrary_types_allowed": True}


class BacktestResult(BaseModel):
    """Result of a DRL backtest."""

    config: BacktestConfig = Field(default_factory=BacktestConfig)
    metrics: PerformanceMetrics = Field(default_factory=PerformanceMetrics)
    equity_curve: list[float] = Field(default_factory=list)
    trades: list[dict[str, Any]] = Field(default_factory=list)
    benchmark_return: float = 0.0  # Buy & Hold return
    agent_returns: dict[str, float] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}
