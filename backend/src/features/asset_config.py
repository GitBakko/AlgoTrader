"""
Asset-specific feature configurations.
Defines which features, indicator periods, and timeframes to use per asset.
"""

from src.features.schemas import AssetFeatureConfig, FeatureConfig, FeatureType


# Default technical indicator parameters
DEFAULT_TECHNICAL_PARAMS = {
    "ema_periods": [8, 21, 50, 200],
    "rsi_period": 14,
    "bb_period": 20,
    "bb_std": 2.0,
    "atr_period": 14,
    "adx_period": 14,
    "hvol_period": 20,
    "macd_fast": 12,
    "macd_slow": 26,
    "macd_signal": 9,
    "return_periods": [1, 5, 20],
}


# ===== Gold (XAUUSD) =====
XAUUSD_CONFIG = AssetFeatureConfig(
    epic="XAUUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Gold is less volatile, use slightly longer periods
        "ema_periods": [8, 21, 50, 200],
        "rsi_period": 14,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        # Macro features (placeholder for Phase 2B)
        FeatureConfig(
            name="dxy_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with DXY index"},
        ),
        FeatureConfig(
            name="real_yield_proxy",
            feature_type=FeatureType.MACRO,
            enabled=False,
            params={"description": "US 10Y yield - CPI proxy"},
        ),
    ],
)


# ===== Bitcoin (BTCUSD) =====
BTCUSD_CONFIG = AssetFeatureConfig(
    epic="BTCUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # BTC is more volatile, slightly shorter periods can be useful
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        # Cross-asset features (placeholder for Phase 2B)
        FeatureConfig(
            name="gold_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Gold price"},
        ),
        FeatureConfig(
            name="sp500_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with S&P 500"},
        ),
    ],
)


# ===== S&P 500 (US500) =====
US500_CONFIG = AssetFeatureConfig(
    epic="US500",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        "ema_periods": [8, 21, 50, 200],
        "rsi_period": 14,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        # Volatility proxy (placeholder for Phase 2B)
        FeatureConfig(
            name="vix_proxy",
            feature_type=FeatureType.MACRO,
            enabled=False,
            params={"description": "VIX or implied volatility proxy"},
        ),
    ],
)


# ===== Crude Oil WTI (WTIUSD) =====
WTIUSD_CONFIG = AssetFeatureConfig(
    epic="WTIUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Oil: high volatility, news-driven, standard periods
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="gold_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Gold (commodities)"},
        ),
    ],
)


# ===== EUR/USD (EURUSD) =====
EURUSD_CONFIG = AssetFeatureConfig(
    epic="EURUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Forex: low volatility, high liquidity, standard periods
        "ema_periods": [8, 21, 50, 200],
        "rsi_period": 14,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="dxy_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Inverse correlation with DXY index"},
        ),
    ],
)


# ===== NVIDIA (NVDA) =====
NVDA_CONFIG = AssetFeatureConfig(
    epic="NVDA",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Tech stock: high volatility, earnings-driven
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="sp500_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with S&P 500"},
        ),
    ],
)


# ===== Tesla (TSLA) =====
TSLA_CONFIG = AssetFeatureConfig(
    epic="TSLA",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Tesla: very high volatility, sentiment-driven
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="sp500_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with S&P 500"},
        ),
    ],
)


# ===== Silver (XAGUSD) =====
XAGUSD_CONFIG = AssetFeatureConfig(
    epic="XAGUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Silver: correlates with gold, higher volatility
        "ema_periods": [8, 21, 50, 200],
        "rsi_period": 14,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="gold_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Gold price"},
        ),
    ],
)


# ===== DAX / Germany 40 (DE40) =====
DE40_CONFIG = AssetFeatureConfig(
    epic="DE40",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # European index, similar to US500
        "ema_periods": [8, 21, 50, 200],
        "rsi_period": 14,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="sp500_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with S&P 500"},
        ),
    ],
)


# Master config dict
ASSET_FEATURE_CONFIGS: dict[str, AssetFeatureConfig] = {
    "XAUUSD": XAUUSD_CONFIG,
    "BTCUSD": BTCUSD_CONFIG,
    "US500": US500_CONFIG,
    "WTIUSD": WTIUSD_CONFIG,
    "EURUSD": EURUSD_CONFIG,
    "NVDA": NVDA_CONFIG,
    "TSLA": TSLA_CONFIG,
    "XAGUSD": XAGUSD_CONFIG,
    "DE40": DE40_CONFIG,
}


def get_asset_config(epic: str) -> AssetFeatureConfig:
    """
    Get feature configuration for an asset.

    Args:
        epic: Asset epic code

    Returns:
        AssetFeatureConfig for the asset

    Raises:
        ValueError: If asset is not configured
    """
    if epic not in ASSET_FEATURE_CONFIGS:
        raise ValueError(
            f"No feature config for '{epic}'. "
            f"Available: {list(ASSET_FEATURE_CONFIGS.keys())}"
        )
    return ASSET_FEATURE_CONFIGS[epic]
