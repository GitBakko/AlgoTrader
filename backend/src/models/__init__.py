"""
ML models module for AlgoTrader AI.
Handles model training, prediction, evaluation, and versioning.
"""

from src.models.schemas import (
    FoldResult,
    ModelMetadata,
    PredictionResult,
    SignalClass,
    SIGNAL_CLASS_NAMES,
    TrainingResult,
)
from src.models.target_builder import TargetBuilder
from src.models.walk_forward import WalkForwardSplitter, WalkForwardSplit
from src.models.base_model import BaseMLModel
from src.models.xgboost_model import XGBoostClassifier
from src.models.evaluator import ModelEvaluator
from src.models.versioning import ModelVersioning
from src.models.trainer import ModelTrainer

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
