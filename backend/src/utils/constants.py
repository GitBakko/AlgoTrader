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
    # Phase 12 expansion candidates (2026-05-08 backtest screening)
    # All gated in _EXCLUDED_ASSETS until Phase 0 OOS validation passes.
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "AMD",
    "USDCHF",
    "USDCAD",
]

# Assets excluded from trading.
#
# Pre-Phase-0 (2026-04-09): NAS100 / XAGUSD / DASHUSD excluded for data
# shortage and historical live failures.
#
# Phase 0 OOS validation re-run on 2026-04-28 (timeframe 4h, no Monte Carlo,
# 18 currently-tradable assets, walk-forward folds with purge+embargo).
# See `docs/reports/2026-04-28_phase0_validation.md` for the full scorecard.
#
# Auto-excluded by the Phase 0 gate (`failed_criteria` non-empty AND
# decision == EXCLUDE — Sharpe < 0.3, win-rate < 40%, max-DD > 30%):
#     ICPUSD, NATGAS, EURUSD, DOGUSD, GBPUSD
#
# REVIEW (manual decision required, NOT auto-excluded):
#     NVDA   — Sharpe 0.22, marginal miss vs 0.30 floor, 47.9% WR
#     USDJPY — Sharpe -2.08 but tiny -0.7% return, micro-position symptom
#     COPPER — Sharpe -4.57, 0.0% WR over 32 trades — likely model rot
#
# Reactivation criterion: re-run `scripts/batch_oos_scorecard.py` on
# fresh data + retrained models; auto-promote when Sharpe > 0.3 and WR > 40%.
_EXCLUDED_ASSETS = {
    # Pre-Phase-0 exclusions (data / spread issues, unchanged)
    "NAS100",
    "XAGUSD",
    "DASHUSD",
    # Phase 0 (2026-04-28) auto-cuts
    "ICPUSD",
    "NATGAS",
    "EURUSD",
    "DOGUSD",
    "GBPUSD",
    # Phase 12 candidates — held out of TRADABLE_ASSETS until OOS scorecard
    # passes the standard gate (Sharpe > 0.3, WR > 40%, max-DD < 30%). They
    # remain in ALL_ASSETS so downloader / trainer / scorecard infrastructure
    # treats them like first-class assets.
    "AAPL",
    "MSFT",
    "GOOGL",
    "AMZN",
    "META",
    "AMD",
    "USDCHF",
    "USDCAD",
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
FOREX_ASSETS: set[str] = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD"}

# Index assets
INDEX_ASSETS: set[str] = {"US500", "DE40", "NAS100"}

# Stock assets
STOCK_ASSETS: set[str] = {
    "NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "AMD",
}

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
    "AAPL": ["NAS100", "US500"],
    "MSFT": ["NAS100", "US500"],
    "GOOGL": ["NAS100", "US500"],
    "AMZN": ["NAS100", "US500"],
    "META": ["NAS100", "US500"],
    "AMD": ["NAS100", "NVDA"],
    # Forex: USD index dynamics
    "USDCHF": ["EURUSD", "USDJPY"],
    "USDCAD": ["WTIUSD", "US500"],
}
