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


# ===== Solana (SOLUSD) =====
SOLUSD_CONFIG = AssetFeatureConfig(
    epic="SOLUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Crypto: high volatility, 24/7 trading
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="btc_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Bitcoin"},
        ),
    ],
)


# ===== Ethereum (ETHUSD) =====
ETHUSD_CONFIG = AssetFeatureConfig(
    epic="ETHUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Ethereum: DeFi backbone, high volatility
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="btc_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Bitcoin"},
        ),
    ],
)


# ===== Binance Coin (BNBUSD) =====
BNBUSD_CONFIG = AssetFeatureConfig(
    epic="BNBUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # BNB: exchange token, moderate-high volatility
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="btc_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Bitcoin"},
        ),
    ],
)


# ===== Dogecoin (DOGUSD) =====
DOGUSD_CONFIG = AssetFeatureConfig(
    epic="DOGUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # DOGE: meme coin, very high volatility, retail momentum
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="btc_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Bitcoin"},
        ),
    ],
)


# ===== Dash (DASHUSD) =====
DASHUSD_CONFIG = AssetFeatureConfig(
    epic="DASHUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # DASH: privacy coin, moderate volatility
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="btc_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Bitcoin"},
        ),
    ],
)


# ===== Internet Computer (ICPUSD) =====
ICPUSD_CONFIG = AssetFeatureConfig(
    epic="ICPUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # ICP: deflationary protocol, moderate volatility
        "ema_periods": [8, 21, 50, 200],
        "hvol_period": 20,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="btc_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Bitcoin"},
        ),
    ],
)


# ===== Natural Gas (NATGAS) =====
NATGAS_CONFIG = AssetFeatureConfig(
    epic="NATGAS",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Natural Gas: extreme volatility (78.4% spike Jan 2026), weather-driven
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


# ===== Copper (COPPER) =====
COPPER_CONFIG = AssetFeatureConfig(
    epic="COPPER",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Copper: industrial metal, supply deficit, moderate volatility
        "ema_periods": [8, 21, 50, 200],
        "rsi_period": 14,
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


# ===== Platinum (PLATINUM) =====
PLATINUM_CONFIG = AssetFeatureConfig(
    epic="PLATINUM",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Platinum: precious metal, automotive/industrial demand
        "ema_periods": [8, 21, 50, 200],
        "rsi_period": 14,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="gold_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Rolling correlation with Gold (precious metals)"},
        ),
    ],
)


# ===== GBP/USD Cable (GBPUSD) =====
GBPUSD_CONFIG = AssetFeatureConfig(
    epic="GBPUSD",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # GBP/USD: high liquidity, tight spreads (0.8-1.2 pips), low volatility
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


# ===== USD/JPY (USDJPY) =====
USDJPY_CONFIG = AssetFeatureConfig(
    epic="USDJPY",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # USD/JPY: negative correlation with EURUSD (-0.40), safe haven flows
        "ema_periods": [8, 21, 50, 200],
        "rsi_period": 14,
    },
    features=[
        FeatureConfig(name="technical_all", feature_type=FeatureType.TECHNICAL),
        FeatureConfig(
            name="dxy_correlation",
            feature_type=FeatureType.CROSS_ASSET,
            enabled=False,
            params={"description": "Positive correlation with DXY index"},
        ),
    ],
)


# ===== Nasdaq 100 (NAS100) =====
NAS100_CONFIG = AssetFeatureConfig(
    epic="NAS100",
    primary_timeframe="1h",
    additional_timeframes=["4h", "1d"],
    technical_params={
        **DEFAULT_TECHNICAL_PARAMS,
        # Nasdaq 100: 55.4% tech composition, higher volatility than S&P500
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


# Master config dict
ASSET_FEATURE_CONFIGS: dict[str, AssetFeatureConfig] = {
    # Existing 9 assets
    "XAUUSD": XAUUSD_CONFIG,
    "BTCUSD": BTCUSD_CONFIG,
    "US500": US500_CONFIG,
    "WTIUSD": WTIUSD_CONFIG,
    "EURUSD": EURUSD_CONFIG,
    "NVDA": NVDA_CONFIG,
    "TSLA": TSLA_CONFIG,
    "XAGUSD": XAGUSD_CONFIG,
    "DE40": DE40_CONFIG,
    # New 12 assets - Phase 12: Portfolio Expansion
    "SOLUSD": SOLUSD_CONFIG,
    "ETHUSD": ETHUSD_CONFIG,
    "BNBUSD": BNBUSD_CONFIG,
    "DOGUSD": DOGUSD_CONFIG,
    "DASHUSD": DASHUSD_CONFIG,
    "ICPUSD": ICPUSD_CONFIG,
    "NATGAS": NATGAS_CONFIG,
    "COPPER": COPPER_CONFIG,
    "PLATINUM": PLATINUM_CONFIG,
    "GBPUSD": GBPUSD_CONFIG,
    "USDJPY": USDJPY_CONFIG,
    "NAS100": NAS100_CONFIG,
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
