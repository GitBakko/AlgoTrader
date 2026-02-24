"""
Pydantic models for ML module.
Defines schemas for predictions, training results, model metadata, and signal classes.
"""

from datetime import datetime, timezone
from enum import Enum, IntEnum

from pydantic import BaseModel, ConfigDict, Field


class SignalClass(IntEnum):
    """
    ATR-relative signal classification (3-class).
    Simplified from 5 classes to concentrate probability mass
    and produce meaningful confidence values (0.50-0.80 range).
    """

    SELL = 0
    HOLD = 1
    BUY = 2


SIGNAL_CLASS_NAMES = {
    SignalClass.SELL: "SELL",
    SignalClass.HOLD: "HOLD",
    SignalClass.BUY: "BUY",
}


class PredictionResult(BaseModel):
    """Result of a single model prediction."""

    signal_class: int = Field(ge=0, le=2)  # SignalClass value (0=SELL, 1=HOLD, 2=BUY)
    signal_name: str  # Human-readable name
    confidence: float  # Probability of predicted class
    probabilities: dict[str, float]  # Class name -> probability
    timestamp: datetime | None = None

    model_config = ConfigDict(use_enum_values=True)


class FoldResult(BaseModel):
    """Training/evaluation result for a single walk-forward fold."""

    fold_index: int
    train_size: int
    val_size: int
    test_size: int
    train_start: datetime | None = None
    train_end: datetime | None = None
    val_start: datetime | None = None
    val_end: datetime | None = None
    test_start: datetime | None = None
    test_end: datetime | None = None
    val_metrics: dict[str, float] = Field(default_factory=dict)
    test_metrics: dict[str, float] = Field(default_factory=dict)


class TrainingResult(BaseModel):
    """Complete training result across all walk-forward folds."""

    epic: str
    timeframe: str
    model_type: str
    num_folds: int
    fold_results: list[FoldResult] = Field(default_factory=list)
    avg_val_metrics: dict[str, float] = Field(default_factory=dict)
    avg_test_metrics: dict[str, float] = Field(default_factory=dict)
    best_fold_index: int | None = None
    feature_names: list[str] = Field(default_factory=list)
    num_features: int = 0
    total_train_samples: int = 0
    hyperparameters: dict = Field(default_factory=dict)
    training_duration_seconds: float = 0.0
    trained_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelMetadata(BaseModel):
    """Metadata about a saved model."""

    model_id: str
    model_type: str
    epic: str
    timeframe: str
    version: int = 1
    feature_names: list[str] = Field(default_factory=list)
    num_features: int = 0
    hyperparameters: dict = Field(default_factory=dict)
    training_result: TrainingResult | None = None
    train_date_start: datetime | None = None
    train_date_end: datetime | None = None
    horizon_bars: int = 6
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""
