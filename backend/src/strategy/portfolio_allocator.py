"""
Portfolio capital allocation across assets with regime adjustments.
Based on allocation strategy from docs/03-ML-STRATEGY.md.
"""

from src.strategy.schemas import AllocationConfig

# Default allocation config
_DEFAULT_CONFIG = AllocationConfig()


class PortfolioAllocator:
    """Allocates capital across assets based on base weights and regime adjustments."""

    @staticmethod
    def get_allocation(
        regime: str | None = None,
        config: AllocationConfig | None = None,
    ) -> dict[str, float]:
        """
        Get portfolio allocation weights for each asset.

        Args:
            regime: Market regime for adjustment (None = use base weights)
                    Recognized regimes: "bull", "bear", "high_vol"
            config: Allocation configuration (uses defaults if None)

        Returns:
            Dict of epic -> weight (weights sum to ~1.0)
        """
        cfg = config or _DEFAULT_CONFIG

        if regime is not None and regime in cfg.regime_adjustments:
            return dict(cfg.regime_adjustments[regime])

        return dict(cfg.base_weights)

    @staticmethod
    def get_max_capital_for_asset(
        epic: str,
        total_equity: float,
        regime: str | None = None,
        config: AllocationConfig | None = None,
    ) -> float:
        """
        Get maximum capital allocatable to a specific asset.

        Args:
            epic: Asset epic code
            total_equity: Total account equity
            regime: Market regime for adjustment
            config: Allocation configuration

        Returns:
            Maximum capital in account currency for this asset
        """
        allocation = PortfolioAllocator.get_allocation(regime, config)
        weight = allocation.get(epic, 0.0)
        return total_equity * weight
