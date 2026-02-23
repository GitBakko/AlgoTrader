"""
Adaptive Kelly Criterion position sizing.
Uses half-Kelly by default for safety, with fallback to fixed-fractional
when insufficient trade history is available.
"""

from dataclasses import dataclass

from loguru import logger


@dataclass
class KellyStats:
    """Statistics computed from trade history for Kelly sizing."""

    win_rate: float
    avg_win: float
    avg_loss: float
    kelly_fraction: float
    half_kelly: float
    num_trades: int


class AdaptiveKellySizer:
    """
    Computes position sizes using the Kelly Criterion adapted for trading.

    Formula: kelly = win_rate - (1 - win_rate) / payoff_ratio
    where payoff_ratio = avg_win / avg_loss

    Uses half-Kelly by default (kelly / 2) for reduced variance.
    Falls back to fixed-fractional sizing when trade history < min_trades.
    """

    def __init__(
        self,
        min_trades: int = 30,
        lookback_trades: int = 100,
        max_kelly: float = 0.25,
        use_half_kelly: bool = True,
    ):
        """
        Args:
            min_trades: Minimum trades before activating Kelly
            lookback_trades: Number of recent trades to use for stats
            max_kelly: Maximum Kelly fraction (cap for safety)
            use_half_kelly: If True, use kelly/2 for lower variance
        """
        self.min_trades = min_trades
        self.lookback_trades = lookback_trades
        self.max_kelly = max_kelly
        self.use_half_kelly = use_half_kelly

    def compute_stats(self, trade_history: list[dict]) -> KellyStats | None:
        """
        Compute Kelly statistics from trade history.

        Args:
            trade_history: List of dicts with 'pnl' key (positive=win, negative=loss)

        Returns:
            KellyStats or None if insufficient data
        """
        if len(trade_history) < self.min_trades:
            return None

        # Use only recent trades
        recent = trade_history[-self.lookback_trades:]
        pnls = [t.get("pnl", t.get("net_pnl", 0.0)) for t in recent]

        wins = [p for p in pnls if p > 0]
        losses = [abs(p) for p in pnls if p < 0]

        if not wins or not losses:
            return None

        # Exclude breakeven trades (pnl==0) from denominator
        decisive_trades = len(wins) + len(losses)
        win_rate = len(wins) / decisive_trades
        avg_win = sum(wins) / len(wins)
        avg_loss = sum(losses) / len(losses)

        if avg_loss <= 0:
            return None

        payoff_ratio = avg_win / avg_loss

        # CRITICAL FIX: Prevent division by zero in Kelly formula
        # If payoff_ratio is 0 or negative, Kelly sizing is invalid
        if payoff_ratio <= 0:
            logger.warning(
                f"Invalid payoff ratio: {payoff_ratio:.4f} "
                f"(avg_win={avg_win:.2f}, avg_loss={avg_loss:.2f})"
            )
            return None

        kelly = win_rate - (1 - win_rate) / payoff_ratio

        # Cap Kelly fraction
        kelly = max(0.0, min(kelly, self.max_kelly))
        half = kelly / 2 if self.use_half_kelly else kelly

        return KellyStats(
            win_rate=win_rate,
            avg_win=avg_win,
            avg_loss=avg_loss,
            kelly_fraction=kelly,
            half_kelly=half,
            num_trades=len(pnls),
        )

    def calculate_size(
        self,
        equity: float,
        entry_price: float,
        stop_loss: float,
        confidence: float,
        trade_history: list[dict],
        max_position_pct: float = 0.05,
    ) -> tuple[float, str]:
        """
        Calculate position size using Kelly or fixed-fractional fallback.

        Args:
            equity: Current account equity
            entry_price: Expected entry price
            stop_loss: Stop-loss price level
            confidence: Model confidence (0.0-1.0)
            trade_history: List of past trades with 'pnl' key
            max_position_pct: Max position as fraction of equity

        Returns:
            Tuple of (position_size, sizing_method)
        """
        if equity <= 0 or entry_price <= 0:
            return 0.0, "invalid"

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance < 1e-10:
            return 0.0, "invalid"

        stats = self.compute_stats(trade_history)

        if stats is None:
            # Fallback: fixed-fractional (same as PositionSizer)
            return self._fixed_fractional(
                equity, stop_distance, entry_price, confidence, max_position_pct
            ), "fixed_fractional"

        # Kelly-based sizing
        kelly_frac = stats.half_kelly if self.use_half_kelly else stats.kelly_fraction

        if kelly_frac <= 0:
            # Negative Kelly = no statistical edge. Fall back to fixed-fractional
            # at 50% size so the system keeps trading conservatively and can
            # recover its stats instead of deadlocking.
            fallback = self._fixed_fractional(
                equity, stop_distance, entry_price, confidence, max_position_pct
            ) * 0.5
            logger.info(
                f"Kelly negative ({stats.kelly_fraction:.4f}), "
                f"fallback to 50% fixed-fractional: size={fallback:.4f} "
                f"(WR={stats.win_rate:.2%}, trades={stats.num_trades})"
            )
            return fallback, "kelly_negative_fallback"

        # Risk amount = kelly fraction * equity * confidence scaling
        confidence_mult = max(0.5, min(1.5, (confidence - 0.5) * 3.33))
        risk_amount = equity * kelly_frac * confidence_mult

        # Position size from risk / stop distance
        size = risk_amount / stop_distance

        # Cap at max position percentage
        max_size = (equity * max_position_pct) / entry_price
        if size > max_size:
            size = max_size

        logger.debug(
            f"Kelly sizing: fraction={kelly_frac:.4f}, "
            f"conf_mult={confidence_mult:.2f}, size={size:.4f} "
            f"(WR={stats.win_rate:.2%}, payoff={stats.avg_win/stats.avg_loss:.2f})"
        )

        return max(0.0, size), "kelly"

    @staticmethod
    def _fixed_fractional(
        equity: float,
        stop_distance: float,
        entry_price: float,
        confidence: float,
        max_position_pct: float,
        risk_per_trade: float = 0.02,
    ) -> float:
        """Fallback fixed-fractional sizing (mirrors PositionSizer)."""
        risk_amount = equity * risk_per_trade
        base_size = risk_amount / stop_distance
        confidence_mult = max(0.5, min(1.5, (confidence - 0.5) * 3.33))
        size = base_size * confidence_mult
        max_size = (equity * max_position_pct) / entry_price
        return max(0.0, min(size, max_size))
