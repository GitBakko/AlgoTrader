"""
Epic analyzer for evaluating candidate assets for day/scalp/intraday trading.

This module provides tools to analyze potential EPIC symbols based on:
- Volatility (intraday price movement %)
- Liquidity (average daily volume)
- Spread (bid-ask spread, lower is better)
- Correlation with existing portfolio (diversification)

Use Case:
    Evaluate new assets before adding them to MANTIS AI trading system.

Example:
    >>> analyzer = EpicAnalyzer()
    >>> analysis = analyzer.analyze("NATGAS")
    >>> if analysis.recommended:
    ...     print(f"✅ {analysis.epic}: {analysis.notes}")

TODO:
    - Implement volatility calculation (historical data from Capital.com)
    - Implement correlation matrix (compare with existing 9 assets)
    - Add volume tracking and liquidity scoring
    - Integrate with Capital.com search API for spread data
"""

from dataclasses import dataclass


@dataclass
class EpicAnalysis:
    """Analysis result for a candidate EPIC symbol."""

    epic: str
    volatility_daily: float  # Average daily price movement in %
    spread_avg: float  # Average bid-ask spread in pips/points
    volume_daily: int  # Average daily volume
    correlation_portfolio: dict[str, float]  # {asset: correlation coefficient}
    recommended: bool  # True if meets criteria for addition
    notes: str  # Human-readable summary


class EpicAnalyzer:
    """
    Analyzer for evaluating candidate EPIC symbols.

    Selection Criteria (default thresholds):
    - Volatility: >1.5% intraday movement (for scalping opportunities)
    - Liquidity: >500k daily volume (for execution quality)
    - Spread: <0.05% (minimize trading costs)
    - Correlation: <0.7 with existing assets (for diversification)

    Current Portfolio (9 assets):
        XAUUSD, BTCUSD, US500, WTIUSD, EURUSD, NVDA, TSLA, XAGUSD, DE40
    """

    def __init__(self):
        """Initialize Epic Analyzer with default criteria."""
        self.min_volatility = 1.5  # %
        self.min_volume = 500_000
        self.max_spread = 0.05  # %
        self.max_correlation = 0.7

        # Current MANTIS AI portfolio
        self.portfolio = [
            "XAUUSD",  # Gold
            "BTCUSD",  # Bitcoin
            "US500",  # S&P 500
            "WTIUSD",  # Crude Oil
            "EURUSD",  # Euro / US Dollar
            "NVDA",  # NVIDIA
            "TSLA",  # Tesla
            "XAGUSD",  # Silver
            "DE40",  # Germany 40 / DAX
        ]

    def analyze(self, epic: str) -> EpicAnalysis:
        """
        Analyze a candidate EPIC symbol.

        Args:
            epic: Asset symbol to analyze (e.g., "NATGAS", "GBPUSD")

        Returns:
            EpicAnalysis with recommendations

        TODO:
            - Fetch historical data from Capital.com
            - Calculate volatility from OHLC data
            - Query spread from broker API
            - Calculate correlation matrix with portfolio
            - Apply selection criteria
        """
        # Placeholder implementation
        return EpicAnalysis(
            epic=epic,
            volatility_daily=0.0,  # TODO: Calculate from historical data
            spread_avg=0.0,  # TODO: Fetch from broker
            volume_daily=0,  # TODO: Fetch from broker
            correlation_portfolio={},  # TODO: Calculate correlation matrix
            recommended=False,  # TODO: Apply criteria
            notes="Analysis not yet implemented. See module docstring for TODOs.",
        )


# Research Findings (February 2026)
# ---------------------------------
# Based on external research (not yet automated):
#
# Top 5 Recommended EPIC Candidates:
#
# 1. NATGAS - Natural Gas Futures
#    - Volatility: 3-5% intraday (excellent for scalping)
#    - Seasonality: strong winter/summer patterns
#    - Correlation with portfolio: Low (~0.3 with WTI)
#    - Notes: High volatility, requires tighter risk management
#
# 2. GBPUSD - British Pound / US Dollar (Cable)
#    - Volatility: 1.8% intraday (European session)
#    - Liquidity: Very high (major forex pair)
#    - Correlation: Medium (~0.6 with EURUSD)
#    - Notes: Strong European session activity, complements EURUSD
#
# 3. MSFT - Microsoft Corporation
#    - Volatility: 1.6% intraday (stable tech)
#    - Liquidity: Excellent (mega-cap stock)
#    - Correlation: High (~0.8 with NVDA, but lower volatility)
#    - Notes: Lower volatility vs NVDA/TSLA, trend-following friendly
#
# 4. NDX - Nasdaq 100 Index
#    - Volatility: 2.2% intraday (tech-heavy)
#    - Correlation: Medium (~0.75 with US500)
#    - Notes: Complements S&P 500, higher tech exposure
#
# 5. COPPER - Copper Futures
#    - Volatility: 1.9% intraday
#    - Economic indicator: Leading indicator for industrial activity
#    - Correlation: Low (~0.4 with Gold, inverse to Dollar)
#    - Notes: Strong diversification, pairs trading potential with Gold
#
# Selection Criteria Used:
# - Volatility >1.5% intraday
# - Liquidity >500k daily volume
# - Spread <0.05% (major markets)
# - Correlation <0.7 with existing portfolio (or strategic overlap like NDX/US500)
#
# Implementation Priority:
# 1. NATGAS (highest volatility, strong seasonality)
# 2. GBPUSD (excellent liquidity, European session coverage)
# 3. MSFT (stable tech alternative to NVDA/TSLA)
# 4. NDX (tech index, complements US500)
# 5. COPPER (diversification, economic indicator)
