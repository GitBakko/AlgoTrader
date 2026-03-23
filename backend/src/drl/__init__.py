# MANTIS-EVOLUTION: DRL Ensemble package
"""Deep Reinforcement Learning ensemble for MANTIS AI (Sprint 5)."""
from src.drl.schemas import (
    DRLConfig,
    TrainingResult,
    PerformanceMetrics,
    PerformanceSnapshot,
    DRLEnsembleSignal,
    ComparisonReport,
    BacktestConfig,
    BacktestResult,
)
from src.drl.base_drl_agent import MantisDRLAgent
from src.drl.agents import PPOAgent, SACAgent, A2CAgent, TD3Agent
from src.drl.performance_analyzer import MantisPerformanceAnalyzer
from src.drl.ensemble import MantisDRLEnsemble
from src.drl.drl_ensemble_agent import MantisDRLEnsembleAgent
from src.drl.trainer import MantisDRLTrainer
from src.drl.backtest import MantisDRLBacktester

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
