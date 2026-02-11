"""
Strategy manager orchestrator.
Coordinates regime adaptation, signal generation, and portfolio allocation.
"""

from loguru import logger

from src.models.schemas import PredictionResult
from src.strategy.portfolio_allocator import PortfolioAllocator
from src.strategy.regime_adapter import RegimeAdapter
from src.strategy.schemas import StrategyConfig, TradingSignal
from src.strategy.signal_generator import SignalGenerator


class StrategyManager:
    """
    Orchestrates the strategy pipeline:
    prediction -> regime adaptation -> signal generation.
    """

    def __init__(self, configs: dict[str, StrategyConfig] | None = None):
        """
        Initialize strategy manager.

        Args:
            configs: Per-asset strategy configs. Uses defaults if None.
        """
        self._configs = configs or {}

    def _get_config(self, epic: str) -> StrategyConfig:
        """Get or create config for an asset."""
        if epic not in self._configs:
            self._configs[epic] = StrategyConfig(epic=epic)
        return self._configs[epic]

    def process_prediction(
        self,
        prediction: PredictionResult,
        epic: str,
        market_data: dict,
    ) -> TradingSignal:
        """
        Process an ML prediction into a trading signal.

        Args:
            prediction: ML model prediction
            epic: Asset epic code
            market_data: Dict with keys:
                - current_price (float, required)
                - atr (float, required)
                - rsi (float, optional)
                - regime (str, optional)

        Returns:
            TradingSignal with direction and suggested levels
        """
        current_price = market_data["current_price"]
        atr = market_data["atr"]
        rsi = market_data.get("rsi")
        regime = market_data.get("regime")

        # Get base config and adapt for regime
        base_config = self._get_config(epic)
        adapted_config = RegimeAdapter.adapt_params(regime, base_config)

        # Generate signal
        signal = SignalGenerator.generate_signal(
            prediction=prediction,
            epic=epic,
            current_price=current_price,
            atr=atr,
            rsi=rsi,
            regime=regime,
            config=adapted_config,
        )

        logger.info(
            f"Strategy [{epic}]: {signal.direction.value} "
            f"conf={signal.confidence:.2f} regime={regime}"
        )

        return signal

    def get_allocation(self, regime: str | None = None) -> dict[str, float]:
        """
        Get portfolio allocation weights.

        Args:
            regime: Market regime for adjustment

        Returns:
            Dict of epic -> allocation weight
        """
        return PortfolioAllocator.get_allocation(regime)
