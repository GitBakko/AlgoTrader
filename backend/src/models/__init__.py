"""
ML models module for AlgoTrader AI.
Handles model training, prediction, evaluation, and versioning.
"""

from src.models.base_model import BaseMLModel
from src.models.evaluator import ModelEvaluator
from src.models.schemas import (
    SIGNAL_CLASS_NAMES,
    FoldResult,
    ModelMetadata,
    PredictionResult,
    SignalClass,
    TrainingResult,
)
from src.models.target_builder import TargetBuilder
from src.models.trainer import ModelTrainer
from src.models.versioning import ModelVersioning
from src.models.walk_forward import WalkForwardSplit, WalkForwardSplitter
from src.models.xgboost_model import XGBoostClassifier

__all__ = [
    # Schemas
    "SignalClass",
    "SIGNAL_CLASS_NAMES",
    "PredictionResult",
    "FoldResult",
    "TrainingResult",
    "ModelMetadata",
    # Core
    "TargetBuilder",
    "WalkForwardSplitter",
    "WalkForwardSplit",
    "BaseMLModel",
    "XGBoostClassifier",
    "ModelEvaluator",
    "ModelVersioning",
    "ModelTrainer",
]
