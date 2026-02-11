"""
Account and per-strategy drawdown monitoring with circuit breaker.
"""

from datetime import datetime, timezone

from loguru import logger

from src.risk.schemas import DrawdownState, RiskLimits


class DrawdownMonitor:
    """
    Tracks equity drawdown at account and per-strategy level.
    Activates circuit breaker when limits are breached.
    """

    def __init__(self, initial_equity: float):
        """
        Initialize drawdown monitor.

        Args:
            initial_equity: Starting equity for tracking
        """
        now = datetime.now(timezone.utc)
        self._state = DrawdownState(
            peak_equity=initial_equity,
            current_equity=initial_equity,
            current_drawdown_pct=0.0,
            daily_pnl=0.0,
            daily_start_equity=initial_equity,
            circuit_breaker_active=False,
            last_reset=now,
        )

    @property
    def state(self) -> DrawdownState:
        """Get current drawdown state."""
        return self._state

    def update(self, current_equity: float) -> DrawdownState:
        """
        Update drawdown tracking with new equity value.

        Args:
            current_equity: Current account equity

        Returns:
            Updated drawdown state
        """
        self._state.current_equity = current_equity

        # Update peak equity (high-water mark)
        if current_equity > self._state.peak_equity:
            self._state.peak_equity = current_equity

        # Calculate current drawdown from peak
        if self._state.peak_equity > 0:
            self._state.current_drawdown_pct = (
                (self._state.peak_equity - current_equity) / self._state.peak_equity
            )
        else:
            self._state.current_drawdown_pct = 0.0

        # Calculate daily P&L
        self._state.daily_pnl = current_equity - self._state.daily_start_equity

        return self._state

    def check_limits(self, limits: RiskLimits) -> tuple[bool, str | None]:
        """
        Check if drawdown limits are breached.

        Args:
            limits: Risk limits to check against

        Returns:
            Tuple of (is_ok, reason). is_ok=True means within limits.
        """
        # Check total drawdown
        if self._state.current_drawdown_pct >= limits.max_total_drawdown:
            reason = (
                f"Total drawdown {self._state.current_drawdown_pct:.1%} "
                f">= limit {limits.max_total_drawdown:.1%}"
            )
            return False, reason

        # Check daily drawdown
        if self._state.daily_start_equity > 0:
            daily_dd = -self._state.daily_pnl / self._state.daily_start_equity
            if daily_dd >= limits.max_daily_drawdown:
                reason = (
                    f"Daily drawdown {daily_dd:.1%} >= limit {limits.max_daily_drawdown:.1%}"
                )
                return False, reason

        return True, None

    def reset_daily(self) -> None:
        """Reset daily P&L tracking. Call at start of trading day."""
        self._state.daily_start_equity = self._state.current_equity
        self._state.daily_pnl = 0.0
        self._state.last_reset = datetime.now(timezone.utc)
        logger.info(
            f"Daily drawdown reset. Start equity: {self._state.daily_start_equity:.2f}"
        )

    def is_circuit_breaker_active(self) -> bool:
        """Check if circuit breaker is currently active."""
        return self._state.circuit_breaker_active

    def activate_circuit_breaker(self, reason: str) -> None:
        """
        Activate circuit breaker to halt all trading.

        Args:
            reason: Reason for activation
        """
        if not self._state.circuit_breaker_active:
            self._state.circuit_breaker_active = True
            self._state.circuit_breaker_reason = reason
            logger.warning(f"CIRCUIT BREAKER ACTIVATED: {reason}")

    def deactivate_circuit_breaker(self) -> None:
        """Deactivate circuit breaker to resume trading."""
        if self._state.circuit_breaker_active:
            self._state.circuit_breaker_active = False
            self._state.circuit_breaker_reason = None
            logger.info("Circuit breaker deactivated, trading resumed")
