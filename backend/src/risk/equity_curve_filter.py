"""
Equity curve filter for position sizing adjustment.
Reduces position size when the equity curve is below its SMA,
indicating a losing streak or underperformance period.
"""

from collections import deque

from loguru import logger
from pydantic import BaseModel, Field


class EquityCurveConfig(BaseModel):
    """Configuration for equity curve filter."""

    sma_window: int = Field(default=20, ge=5, le=100)
    reduction_factor: float = Field(default=0.50, ge=0.1, le=0.9)
    min_trades_to_activate: int = Field(default=10, ge=3, le=50)


class EquityCurveFilter:
    """
    Tracks equity curve via trade-level snapshots and reduces position sizing
    when equity falls below its SMA.

    Usage:
        1. Call record_trade_close(equity) after each trade closes
        2. Call get_size_multiplier() before sizing a new position
    """

    def __init__(self, config: EquityCurveConfig | None = None):
        self.config = config or EquityCurveConfig()
        self._equity_points: deque[float] = deque(
            maxlen=self.config.sma_window * 3
        )

    def record_trade_close(self, equity_after_close: float) -> None:
        """
        Record equity snapshot after a trade closes.

        Args:
            equity_after_close: Account equity after the trade was closed.
        """
        self._equity_points.append(equity_after_close)

    def get_size_multiplier(self) -> float:
        """
        Get position size multiplier based on equity curve vs SMA.

        Returns:
            1.0 if equity above SMA or insufficient data,
            config.reduction_factor if equity below SMA.
        """
        if len(self._equity_points) < self.config.min_trades_to_activate:
            return 1.0

        sma = self.sma_value
        if sma is None:
            return 1.0

        current = self._equity_points[-1]
        if current < sma:
            logger.debug(
                f"Equity curve filter: equity {current:.2f} < SMA {sma:.2f}, "
                f"reducing size by {self.config.reduction_factor:.0%}"
            )
            return self.config.reduction_factor

        return 1.0

    @property
    def is_below_sma(self) -> bool:
        """Check if current equity is below its SMA."""
        if len(self._equity_points) < self.config.min_trades_to_activate:
            return False
        sma = self.sma_value
        if sma is None:
            return False
        return self._equity_points[-1] < sma

    @property
    def sma_value(self) -> float | None:
        """Current SMA of equity curve, or None if insufficient data."""
        window = self.config.sma_window
        if len(self._equity_points) < window:
            return None
        recent = list(self._equity_points)[-window:]
        return sum(recent) / len(recent)

    @property
    def trade_count(self) -> int:
        """Number of recorded trade closes."""
        return len(self._equity_points)

    def get_status(self) -> dict:
        """Get status for API/reporting."""
        return {
            "trade_count": self.trade_count,
            "sma_value": self.sma_value,
            "is_below_sma": self.is_below_sma,
            "size_multiplier": self.get_size_multiplier(),
            "last_equity": self._equity_points[-1] if self._equity_points else None,
        }
