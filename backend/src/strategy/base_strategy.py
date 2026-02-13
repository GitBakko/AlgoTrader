"""
Abstract base class for all trading strategies.
Defines the interface that strategies must implement.
"""

from abc import ABC, abstractmethod

import polars as pl

from src.strategy.schemas import StrategyConfig, TradingSignal


class BaseStrategy(ABC):
    """
    Abstract base class for trading strategies.

    All strategies must implement:
    - generate_signal() for real-time trading
    - generate_backtest_signals() for batch backtesting
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy name identifier."""
        ...

    @property
    @abstractmethod
    def applicable_regimes(self) -> list[str]:
        """Market regimes where this strategy is applicable."""
        ...

    @abstractmethod
    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        """
        Generate a trading signal from current market data.

        Args:
            epic: Asset epic code
            current_bar: Dict with OHLCV + indicator values for current bar
            recent_bars: Recent bars DataFrame for lookback analysis
            config: Strategy configuration

        Returns:
            TradingSignal
        """
        ...

    @abstractmethod
    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """
        Generate signals for an entire DataFrame (batch backtesting).

        Args:
            ohlc_df: DataFrame with OHLCV + indicators
            epic: Asset epic code
            timeframe: Timeframe string

        Returns:
            DataFrame with added signal columns
        """
        ...
