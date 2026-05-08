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
    # Phase 14 forex expansion (2026-05-09)
    # Diversifies away from existing USD-quote majors. Initially gated
    # in _EXCLUDED_ASSETS until 730d Capital.com backfill + retrain
    # produces f1 > 0.55 baseline.
    "AUDUSD",
    "NZDUSD",
    "EURJPY",
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
    # AAPL/MSFT/GOOGL/AMZN/META/AMD PROMOTED on 2026-05-08 — Phase 14
    # Capital.com history backfill complete (commit e0d26cd unblocked
    # tz-mismatch in storage.append_candles). Each stock now has
    # ~12,750 bars at ~17.5 bars/cal-day density (yfinance + Capital
    # combined), well above Phase 0 stocks=10.5 spec. Walk-forward
    # windows compute cleanly (train=2646, val=662, test=220, step=220
    # → 42 folds available). Per-epic risk multiplier defaults to 1.0
    # until live PnL justifies adjustment (track via EPIC_RISK_MULTIPLIERS
    # in backend/.env). XGBoost models will be trained on first
    # /api/models/retrain-all run.
    #
    # USDCHF + USDCAD PROMOTED on 2026-05-08 — multi-timeframe retrain
    # produced f1 0.5945 / 0.6134 (above BTC baseline 0.57). Risk multi-
    # plier left at default 1.0 until live PnL evidence justifies a
    # boost à la USDJPY (1.5x). See backend/.env EPIC_RISK_MULTIPLIERS.
    #
    # AUDUSD + EURJPY PROMOTED on 2026-05-09 — Phase 14 forex retrain
    # produced f1 0.5307 / 0.5418 (between stock baseline AMD 0.5149
    # and META 0.5401). 19 folds × 199 features. Risk multiplier
    # default 1.0; revisit after live PnL evidence.
    #
    # NZDUSD KEPT EXCLUDED — f1 0.5060 below stock floor 0.51,
    # marginal vs random. Re-evaluate after AUDUSD shows live edge
    # (sister-pair correlation should lift NZDUSD signal quality).
    "NZDUSD",
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
FOREX_ASSETS: set[str] = {
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD",
    "AUDUSD", "NZDUSD", "EURJPY",
}

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
    # Forex Phase 14: commodity-linked + cross
    "AUDUSD": ["XAUUSD", "COPPER"],
    "NZDUSD": ["AUDUSD", "WTIUSD"],
    "EURJPY": ["EURUSD", "USDJPY"],
}
