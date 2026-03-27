"""
Feature engineering module for AlgoTrader AI.
Transforms raw OHLC data into ML-ready feature matrices.
"""

from src.features.alignment import TimeframeAligner
from src.features.asset_config import (
    ASSET_FEATURE_CONFIGS,
    DEFAULT_TECHNICAL_PARAMS,
    get_asset_config,
)
from src.features.builder import FeatureBuilder
from src.features.normalizer import FeatureNormalizer
from src.features.regime import RegimeDetector
from src.features.schemas import (
    AssetFeatureConfig,
    FeatureConfig,
    FeatureMatrix,
    FeatureSet,
    FeatureType,
    MarketRegime,
)
from src.features.technical import TechnicalIndicators

__all__ = [
    # Schemas
    "FeatureType",
    "MarketRegime",
    "FeatureConfig",
    "AssetFeatureConfig",
    "FeatureSet",
    "FeatureMatrix",
    # Core
    "TechnicalIndicators",
    "FeatureNormalizer",
    "TimeframeAligner",
    "RegimeDetector",
    # Config
    "ASSET_FEATURE_CONFIGS",
    "DEFAULT_TECHNICAL_PARAMS",
    "get_asset_config",
    # Builder
    "FeatureBuilder",
]
