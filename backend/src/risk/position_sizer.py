"""
ATR-based position sizing with confidence scaling.
Formula from docs/03-ML-STRATEGY.md.
"""

from loguru import logger


class PositionSizer:
    """Calculates position sizes based on risk parameters and model confidence."""

    @staticmethod
    def calculate_size(
        equity: float,
        risk_per_trade: float,
        entry_price: float,
        stop_loss: float,
        confidence: float,
        max_position_pct: float = 0.05,
    ) -> float:
        """
        Calculate position size using ATR-based risk and confidence scaling.

        Args:
            equity: Current account equity
            risk_per_trade: Max risk as fraction of equity (e.g. 0.02 = 2%)
            entry_price: Expected entry price
            stop_loss: Stop-loss price level
            confidence: Model confidence (0.0-1.0)
            max_position_pct: Max position as fraction of equity (default 5%)

        Returns:
            Position size (units of the asset)
        """
        if equity <= 0 or entry_price <= 0:
            return 0.0

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance < 1e-10:
            logger.warning("Stop distance is zero, cannot calculate position size")
            return 0.0

        # Base risk amount
        risk_amount = equity * risk_per_trade

        # Base position size from risk/stop distance
        # Note: confidence scaling is handled by RiskManager.confidence_size_multiplier()
        final_size = risk_amount / stop_distance

        # Cap at max_position_pct of equity
        max_size = (equity * max_position_pct) / entry_price
        if final_size > max_size:
            logger.debug(
                f"Position size capped: {final_size:.4f} -> {max_size:.4f} "
                f"(max {max_position_pct*100:.0f}% of equity)"
            )
            final_size = max_size

        return max(0.0, final_size)
