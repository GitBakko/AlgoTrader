"""
Strategy Router: selects and executes strategies based on market regime.

Routes signals to the most appropriate strategy for the current regime,
with fallthrough logic (if first strategy returns HOLD, try next).
"""

import polars as pl
from loguru import logger

from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal


class StrategyRouter:
    """
    Routes trading decisions to regime-appropriate strategies.

    Each regime has an ordered list of strategies. The router tries
    strategies in order until one produces a non-HOLD signal.
    """

    # Default regime-to-strategy priority map
    DEFAULT_REGIME_MAP: dict[str, list[str]] = {
        "trending_up": ["ml_ensemble"],
        "trending_down": ["ml_ensemble"],
        "ranging": ["squeeze_breakout", "vwap_reversion", "ml_ensemble"],
    }

    def __init__(
        self,
        regime_map: dict[str, list[str]] | None = None,
    ):
        """
        Args:
            regime_map: Custom regime-to-strategy mapping (None = defaults)
        """
        self._strategies: dict[str, BaseStrategy] = {}
        self._regime_map = regime_map or self.DEFAULT_REGIME_MAP

    def register_strategy(self, strategy: BaseStrategy) -> None:
        """Register a strategy for routing."""
        self._strategies[strategy.name] = strategy
        logger.debug(
            f"Strategy registered: {strategy.name} "
            f"(regimes: {strategy.applicable_regimes})"
        )

    def get_strategy(self, name: str) -> BaseStrategy | None:
        """Get a registered strategy by name."""
        return self._strategies.get(name)

    @property
    def registered_strategies(self) -> list[str]:
        """Names of all registered strategies."""
        return list(self._strategies.keys())

    def select_strategy(
        self,
        regime: str | None,
        epic: str,
    ) -> list[BaseStrategy]:
        """
        Get ordered list of strategies for the given regime.

        Args:
            regime: Current market regime (None = use all registered)
            epic: Asset epic (for future per-asset routing)

        Returns:
            Ordered list of BaseStrategy instances
        """
        if regime is None:
            regime = "ranging"

        strategy_names = self._regime_map.get(regime, ["ml_ensemble"])
        strategies = []
        for name in strategy_names:
            strat = self._strategies.get(name)
            if strat is not None:
                strategies.append(strat)

        if not strategies:
            # Fallback: return all registered strategies
            strategies = list(self._strategies.values())

        return strategies

    def generate_signal(
        self,
        epic: str,
        regime: str | None,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        """
        Route signal generation through strategies with fallthrough.

        Tries strategies in priority order for the regime.
        First non-HOLD signal wins. If all return HOLD, returns HOLD.

        Args:
            epic: Asset epic
            regime: Current market regime
            current_bar: Current bar data dict
            recent_bars: Recent bars DataFrame
            config: Strategy configuration

        Returns:
            TradingSignal from the winning strategy
        """
        strategies = self.select_strategy(regime, epic)

        for strategy in strategies:
            try:
                signal = strategy.generate_signal(
                    epic=epic,
                    current_bar=current_bar,
                    recent_bars=recent_bars,
                    config=config,
                )

                if signal.direction != SignalDirection.HOLD:
                    signal.strategy_name = strategy.name
                    logger.info(
                        f"{epic}: Strategy '{strategy.name}' produced "
                        f"{signal.direction.value} (regime={regime})"
                    )
                    return signal

                logger.debug(
                    f"{epic}: Strategy '{strategy.name}' returned HOLD, "
                    f"trying next..."
                )

            except Exception as e:
                logger.error(
                    f"{epic}: Strategy '{strategy.name}' failed: {e}"
                )
                continue

        # All strategies returned HOLD
        from src.models.schemas import SignalClass

        return TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=SignalClass.HOLD,
            entry_price=float(current_bar.get("close", 0)),
            technical_confirmation=False,
            strategy_name=None,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
        regime: str | None = None,
    ) -> pl.DataFrame:
        """
        Generate signals for backtesting using the primary strategy
        for the given regime.

        Args:
            ohlc_df: DataFrame with OHLCV + indicators
            epic: Asset epic
            timeframe: Timeframe
            regime: Market regime (uses first strategy in priority list)

        Returns:
            DataFrame with signal columns added
        """
        strategies = self.select_strategy(regime, epic)
        if not strategies:
            return ohlc_df.with_columns([
                pl.lit(0).alias("signal_direction"),
                pl.lit(0.0).alias("signal_confidence"),
            ])

        # Use first (highest priority) strategy for batch backtest
        return strategies[0].generate_backtest_signals(ohlc_df, epic, timeframe)
