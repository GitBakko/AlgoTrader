# MANTIS-EVOLUTION: DRL Ensemble package
"""Deep Reinforcement Learning ensemble for MANTIS AI (Sprint 5)."""

from src.drl.agents import A2CAgent, PPOAgent, SACAgent, TD3Agent
from src.drl.backtest import MantisDRLBacktester
from src.drl.base_drl_agent import MantisDRLAgent
from src.drl.ensemble import MantisDRLEnsemble
from src.drl.performance_analyzer import MantisPerformanceAnalyzer
from src.drl.schemas import (
    BacktestConfig,
    BacktestResult,
    ComparisonReport,
    DRLConfig,
    DRLEnsembleSignal,
    PerformanceMetrics,
    PerformanceSnapshot,
    TrainingResult,
)
from src.drl.trainer import MantisDRLTrainer

# NOTE: MantisDRLEnsembleAgent is NOT imported here to avoid a circular import:
#   drl/__init__ -> drl_ensemble_agent -> agents.schemas -> agents/__init__
#   -> agents.orchestrator -> drl.drl_ensemble_agent (partially initialised)
# Import it directly: from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent


def __getattr__(name: str):
    """Lazy-load MantisDRLEnsembleAgent to break the circular import."""
    if name == "MantisDRLEnsembleAgent":
        from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent  # noqa: PLC0415

        return MantisDRLEnsembleAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DRLConfig",
    "TrainingResult",
    "PerformanceMetrics",
    "PerformanceSnapshot",
    "DRLEnsembleSignal",
    "ComparisonReport",
    "BacktestConfig",
    "BacktestResult",
    "MantisDRLAgent",
    "PPOAgent",
    "SACAgent",
    "A2CAgent",
    "TD3Agent",
    "MantisPerformanceAnalyzer",
    "MantisDRLEnsemble",
    "MantisDRLEnsembleAgent",
    "MantisDRLTrainer",
    "MantisDRLBacktester",
]
