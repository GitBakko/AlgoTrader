"""
Centralized asset definitions for MANTIS AI.

Single source of truth for all 21 supported assets.
Import from here instead of hardcoding asset lists.
"""

# All 21 supported assets
ALL_ASSETS: list[str] = [
    # Original 9
    "XAUUSD",
    "BTCUSD",
    "US500",
    "WTIUSD",
    "EURUSD",
    "NVDA",
    "TSLA",
    "XAGUSD",
    "DE40",
    # Phase 11 expansion (12 new)
    "SOLUSD",
    "ETHUSD",
    "BNBUSD",
    "DOGUSD",
    "DASHUSD",
    "ICPUSD",
    "NATGAS",
    "COPPER",
    "PLATINUM",
    "GBPUSD",
    "USDJPY",
    "NAS100",
]

# Assets excluded from trading.
# Phase 0 OOS validation (2026-03-31) excluded 11 assets based on models with
# 83 features (F1 ~0.23). After retrain on 2026-04-09 with 199 features (multi-TF),
# all except NAS100 now have F1 > 0.53. Reactivated 8 with high confidence.
#
# Still excluded:
# NAS100: insufficient historical data (3706 bars vs 8071 needed), F1=0.30
# XAGUSD: F1=0.548 post-retrain but FAILED in live (23.5% WR, -$71 in 48h) — needs
#          paper confirmation before reactivation
# DASHUSD: F1=0.537 but known spread issues (MAX_SPREAD_PCT filter blocks most signals)
_EXCLUDED_ASSETS = {
    "NAS100",
    "XAGUSD",
    "DASHUSD",
}
TRADABLE_ASSETS: list[str] = [a for a in ALL_ASSETS if a not in _EXCLUDED_ASSETS]

# Crypto assets (24/7 markets, different session handling)
CRYPTO_ASSETS: set[str] = {
    "BTCUSD",
    "SOLUSD",
    "ETHUSD",
    "BNBUSD",
    "DOGUSD",
    "DASHUSD",
    "ICPUSD",
}

# Commodity assets
COMMODITY_ASSETS: set[str] = {
    "XAUUSD",
    "XAGUSD",
    "WTIUSD",
    "NATGAS",
    "COPPER",
    "PLATINUM",
}

# Forex assets
FOREX_ASSETS: set[str] = {"EURUSD", "GBPUSD", "USDJPY"}

# Index assets
INDEX_ASSETS: set[str] = {"US500", "DE40", "NAS100"}

# Stock assets
STOCK_ASSETS: set[str] = {"NVDA", "TSLA"}

# Cross-asset correlation clusters
# Each asset maps to its cluster leader(s) — assets whose returns
# are used as features for this asset's ML model.
ASSET_CLUSTERS: dict[str, list[str]] = {
    # Crypto: BTC leads the pack
    "BTCUSD": ["US500", "XAUUSD"],
    "ETHUSD": ["BTCUSD", "US500"],
    "SOLUSD": ["BTCUSD", "ETHUSD"],
    "BNBUSD": ["BTCUSD", "ETHUSD"],
    "DOGUSD": ["BTCUSD", "ETHUSD"],
    "DASHUSD": ["BTCUSD", "ETHUSD"],
    "ICPUSD": ["BTCUSD", "ETHUSD"],
    # Commodities: Gold leads, oil separate
    "XAUUSD": ["USDJPY", "US500"],
    "XAGUSD": ["XAUUSD", "COPPER"],
    "WTIUSD": ["US500", "COPPER"],
    "NATGAS": ["WTIUSD", "COPPER"],
    "COPPER": ["US500", "WTIUSD"],
    "PLATINUM": ["XAUUSD", "COPPER"],
    # Forex: USD index dynamics
    "EURUSD": ["GBPUSD", "USDJPY"],
    "GBPUSD": ["EURUSD", "US500"],
    "USDJPY": ["XAUUSD", "US500"],
    # Indices: co-move strongly
    "US500": ["NAS100", "DE40"],
    "DE40": ["US500", "EURUSD"],
    "NAS100": ["US500", "NVDA"],
    # Stocks: sector + index
    "NVDA": ["NAS100", "US500"],
    "TSLA": ["NAS100", "US500"],
}
