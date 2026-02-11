"""
Pydantic models for feature engineering module.
Defines schemas for feature configuration, computed feature sets, and ML-ready matrices.
"""

from datetime import datetime, timezone
from enum import Enum

import polars as pl
from pydantic import BaseModel, ConfigDict, Field


class FeatureType(str, Enum):
    """Type of feature."""

    TECHNICAL = "technical"
    MACRO = "macro"
    SENTIMENT = "sentiment"
    CROSS_ASSET = "cross_asset"
    REGIME = "regime"


class MarketRegime(str, Enum):
    """Market regime classification."""

    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"


class FeatureConfig(BaseModel):
    """Configuration for a single feature or indicator."""

    model_config = ConfigDict(use_enum_values=True)

    name: str
    feature_type: FeatureType
    params: dict = Field(default_factory=dict)
    enabled: bool = True


class AssetFeatureConfig(BaseModel):
    """Feature configuration for a specific asset."""

    epic: str
    primary_timeframe: str = "1h"
    additional_timeframes: list[str] = Field(default_factory=list)
    technical_params: dict = Field(default_factory=dict)
    features: list[FeatureConfig] = Field(default_factory=list)


class FeatureSet(BaseModel):
    """Set of computed features with metadata."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    epic: str
    timeframe: str
    feature_names: list[str]
    num_rows: int
    num_features: int
    start_date: datetime | None = None
    end_date: datetime | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FeatureMatrix(BaseModel):
    """
    ML-ready feature matrix.
    Wraps a Polars DataFrame with feature columns and optional target column.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    epic: str
    timeframe: str
    feature_names: list[str]
    target_column: str | None = None
    num_rows: int
    num_features: int
    start_date: datetime | None = None
    end_date: datetime | None = None
    regime_column: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
