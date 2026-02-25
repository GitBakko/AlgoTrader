"""
Regime-adaptive strategy parameter adjustment.
Modifies strategy config based on detected market regime.
"""

from src.strategy.schemas import StrategyConfig


# Regime-specific parameter overrides (calibrated for 3-class system)
_REGIME_PARAMS: dict[str, dict[str, float]] = {
    "trending_up": {
        "min_confidence": 0.50,     # was 0.48; aligned with tiering floor
        "stop_multiplier": 2.5,     # was 3.5
        "counter_trend_penalty": 0.5,  # was 0.4 (less harsh)
    },
    "trending_down": {
        "min_confidence": 0.50,     # was 0.45
        "stop_multiplier": 2.0,     # was 2.5
        "counter_trend_penalty": 0.4,  # was 0.3 (less harsh)
    },
    "ranging": {
        "min_confidence": 0.50,     # was 0.52 (aligned with trending)
        "stop_multiplier": 2.0,     # was 2.5
        "counter_trend_penalty": 0.7,  # unchanged
    },
}


class RegimeAdapter:
    """Adapts strategy parameters based on market regime."""

    @staticmethod
    def adapt_params(regime: str | None, base_config: StrategyConfig) -> StrategyConfig:
        """
        Adjust strategy config parameters for the current market regime.

        Args:
            regime: Current market regime ("trending_up", "trending_down", "ranging")
                    or None for no adaptation
            base_config: Base strategy configuration

        Returns:
            New StrategyConfig with regime-adjusted parameters
        """
        if regime is None or regime not in _REGIME_PARAMS:
            return base_config

        overrides = _REGIME_PARAMS[regime]
        return base_config.model_copy(update=overrides)

    @staticmethod
    def get_stop_multiplier(regime: str | None) -> float:
        """
        Get ATR stop multiplier for the given regime.

        Args:
            regime: Market regime or None

        Returns:
            ATR multiplier for stop-loss calculation
        """
        if regime is None or regime not in _REGIME_PARAMS:
            return 2.0
        return _REGIME_PARAMS[regime]["stop_multiplier"]

    @staticmethod
    def is_counter_trend(direction: str, regime: str | None) -> bool:
        """
        Check if a trade direction is counter-trend for the given regime.

        Args:
            direction: Trade direction ("BUY" or "SELL")
            regime: Market regime

        Returns:
            True if the trade is counter-trend
        """
        if regime == "trending_up" and direction == "SELL":
            return True
        if regime == "trending_down" and direction == "BUY":
            return True
        return False
