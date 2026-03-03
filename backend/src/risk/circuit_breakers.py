"""
Advanced circuit breakers for trading risk management.
6 types: daily loss, consecutive losses, max positions,
slippage anomaly, heartbeat timeout, volatility spike.
"""

import threading
import time as _time
from enum import Enum

from loguru import logger
from pydantic import BaseModel, Field


class CircuitBreakerType(str, Enum):
    """Types of circuit breakers."""

    DAILY_LOSS = "daily_loss"
    CONSECUTIVE_LOSSES = "consecutive_losses"
    MAX_POSITIONS = "max_positions"
    SLIPPAGE_ANOMALY = "slippage_anomaly"
    HEARTBEAT_TIMEOUT = "heartbeat_timeout"
    VOLATILITY_SPIKE = "volatility_spike"
    MAX_TRADES_PER_DAY = "max_trades_per_day"


class CircuitBreakerConfig(BaseModel):
    """Configuration for circuit breaker thresholds."""

    daily_loss_limit: float = Field(default=0.03, ge=0.005, le=0.20)
    max_consecutive_losses: int = Field(default=8, ge=2, le=20)
    max_open_positions: int = Field(default=20, ge=1, le=50)
    slippage_threshold_pct: float = Field(default=0.005, ge=0.001, le=0.05)
    slippage_window: int = Field(default=5, ge=2, le=50)
    heartbeat_timeout_seconds: float = Field(default=30.0, ge=5.0, le=300.0)
    volatility_spike_multiplier: float = Field(default=5.0, ge=2.0, le=20.0)
    auto_reset_after_minutes: int = Field(default=60, ge=5, le=1440)
    max_trades_per_day: int = Field(default=30, ge=1, le=200)
    max_trades_throttle_pct: float = Field(default=0.8, ge=0.5, le=1.0)


class CircuitBreakerManager:
    """
    Manages multiple circuit breaker checks for the trading system.

    Each check can independently trip the breaker. Auto-reset is available
    after a configurable cooldown period.
    """

    def __init__(self, config: CircuitBreakerConfig | None = None):
        self.config = config or CircuitBreakerConfig()

        # CRITICAL FIX (CRIT-4): Thread-safety lock for shared state
        # Using threading.Lock() (not asyncio.Lock) for compatibility with sync and async code
        self._lock = threading.Lock()

        # State tracking
        self._tripped: dict[CircuitBreakerType, str] = {}
        self._tripped_at: dict[CircuitBreakerType, float] = {}
        self._consecutive_losses: int = 0
        self._slippage_history: list[float] = []
        self._last_heartbeat: float = _time.monotonic()
        self._baseline_atr: dict[str, float] = {}
        self._daily_trade_count: int = 0
        self._daily_trade_date: str = ""

    @property
    def is_tripped(self) -> bool:
        """Check if any circuit breaker is currently tripped (thread-safe)."""
        with self._lock:
            return len(self._tripped) > 0

    @property
    def tripped_breakers(self) -> dict[str, str]:
        """Get dict of tripped breaker type -> reason (thread-safe)."""
        with self._lock:
            return {k.value: v for k, v in self._tripped.items()}

    def check_all(
        self,
        daily_pnl_pct: float,
        open_position_count: int,
        current_atr: float | None = None,
        baseline_atr: float | None = None,
        epic: str | None = None,
    ) -> tuple[bool, list[str]]:
        """
        Run all circuit breaker checks.

        Args:
            daily_pnl_pct: Current daily P&L as percentage (negative = loss)
            open_position_count: Number of open positions
            current_atr: Current ATR value (for volatility spike)
            baseline_atr: Baseline ATR for comparison
            epic: Asset epic (for baseline ATR tracking)

        Returns:
            Tuple of (is_ok, list of trip reasons). is_ok=True means all clear.
        """
        reasons: list[str] = []

        # Try auto-reset before checking
        self._try_auto_reset()

        # 1. Daily loss check
        if daily_pnl_pct < -self.config.daily_loss_limit:
            reason = (
                f"Daily loss {daily_pnl_pct:.2%} exceeds limit "
                f"-{self.config.daily_loss_limit:.2%}"
            )
            self._trip(CircuitBreakerType.DAILY_LOSS, reason)
            reasons.append(reason)

        # 2. Consecutive losses
        if self._consecutive_losses >= self.config.max_consecutive_losses:
            reason = (
                f"Consecutive losses ({self._consecutive_losses}) >= "
                f"limit ({self.config.max_consecutive_losses})"
            )
            self._trip(CircuitBreakerType.CONSECUTIVE_LOSSES, reason)
            reasons.append(reason)

        # 3. Max positions
        if open_position_count >= self.config.max_open_positions:
            reason = (
                f"Open positions ({open_position_count}) >= "
                f"limit ({self.config.max_open_positions})"
            )
            self._trip(CircuitBreakerType.MAX_POSITIONS, reason)
            reasons.append(reason)

        # 4. Heartbeat timeout
        elapsed = _time.monotonic() - self._last_heartbeat
        if elapsed > self.config.heartbeat_timeout_seconds:
            reason = (
                f"Heartbeat timeout: {elapsed:.1f}s > "
                f"{self.config.heartbeat_timeout_seconds:.1f}s"
            )
            self._trip(CircuitBreakerType.HEARTBEAT_TIMEOUT, reason)
            reasons.append(reason)

        # 5. Volatility spike
        if current_atr is not None and baseline_atr is not None and baseline_atr > 0:
            ratio = current_atr / baseline_atr
            if ratio >= self.config.volatility_spike_multiplier:
                reason = (
                    f"Volatility spike: ATR ratio {ratio:.1f}x >= "
                    f"{self.config.volatility_spike_multiplier:.1f}x"
                )
                self._trip(CircuitBreakerType.VOLATILITY_SPIKE, reason)
                reasons.append(reason)

        # 6. Max trades per day
        if self._daily_trade_count >= self.config.max_trades_per_day:
            reason = (
                f"Max trades/day ({self._daily_trade_count}) >= "
                f"limit ({self.config.max_trades_per_day})"
            )
            self._trip(CircuitBreakerType.MAX_TRADES_PER_DAY, reason)
            reasons.append(reason)

        # 7. Slippage anomaly (checked internally via recorded slippage)
        if len(self._slippage_history) >= self.config.slippage_window:
            recent = self._slippage_history[-self.config.slippage_window:]
            avg_slippage = sum(recent) / len(recent)
            if avg_slippage > self.config.slippage_threshold_pct:
                reason = (
                    f"Slippage anomaly: avg {avg_slippage:.4%} > "
                    f"{self.config.slippage_threshold_pct:.4%} "
                    f"(last {self.config.slippage_window} trades)"
                )
                self._trip(CircuitBreakerType.SLIPPAGE_ANOMALY, reason)
                reasons.append(reason)

        # Also include already-tripped breakers
        for cb_type, cb_reason in self._tripped.items():
            if cb_reason not in reasons:
                reasons.append(cb_reason)

        is_ok = len(reasons) == 0
        return is_ok, reasons

    def record_trade_opened(self, current_date: str | None = None) -> None:
        """
        Record a trade was opened for daily trade count tracking (thread-safe).

        Args:
            current_date: Date string (YYYY-MM-DD). Auto-detected if None.
        """
        from datetime import datetime, timezone
        if current_date is None:
            current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with self._lock:
            if self._daily_trade_date != current_date:
                self._daily_trade_count = 0
                self._daily_trade_date = current_date
                # Clear the max trades breaker on new day
                self._tripped.pop(CircuitBreakerType.MAX_TRADES_PER_DAY, None)
                self._tripped_at.pop(CircuitBreakerType.MAX_TRADES_PER_DAY, None)
            self._daily_trade_count += 1

    def is_trade_throttled(self) -> bool:
        """
        Check if trades should be throttled (80% of max trades/day).
        When throttled, caller should halve position size.
        """
        with self._lock:
            threshold = int(self.config.max_trades_per_day * self.config.max_trades_throttle_pct)
            return self._daily_trade_count >= threshold

    def record_trade_result(self, is_win: bool) -> None:
        """
        Record trade outcome for consecutive loss tracking (thread-safe).

        Args:
            is_win: True if trade was profitable
        """
        with self._lock:
            if is_win:
                self._consecutive_losses = 0
                # Auto-clear consecutive losses breaker on a win
                # Note: _clear() has its own lock, but we're already inside one
                # so we need to clear manually here to avoid deadlock
                self._tripped.pop(CircuitBreakerType.CONSECUTIVE_LOSSES, None)
                self._tripped_at.pop(CircuitBreakerType.CONSECUTIVE_LOSSES, None)
            else:
                self._consecutive_losses += 1

    def record_slippage(self, slippage_pct: float) -> None:
        """
        Record slippage for anomaly detection (thread-safe).

        Args:
            slippage_pct: Absolute slippage as percentage (e.g., 0.002 = 0.2%)
        """
        with self._lock:
            self._slippage_history.append(abs(slippage_pct))
            # Keep only recent history
            max_history = self.config.slippage_window * 3
            if len(self._slippage_history) > max_history:
                self._slippage_history = self._slippage_history[-max_history:]

    def heartbeat(self) -> None:
        """Update heartbeat timestamp. Call at start of each iteration (thread-safe)."""
        with self._lock:
            self._last_heartbeat = _time.monotonic()
            # Clear manually to avoid deadlock (we already have the lock)
            self._tripped.pop(CircuitBreakerType.HEARTBEAT_TIMEOUT, None)
            self._tripped_at.pop(CircuitBreakerType.HEARTBEAT_TIMEOUT, None)

    def update_baseline_atr(self, epic: str, atr: float) -> None:
        """Update baseline ATR for volatility spike detection (thread-safe)."""
        with self._lock:
            self._baseline_atr[epic] = atr

    def get_baseline_atr(self, epic: str) -> float | None:
        """Get baseline ATR for an epic (thread-safe)."""
        with self._lock:
            return self._baseline_atr.get(epic)

    def reset_all(self) -> list[str]:
        """
        Manually reset all circuit breakers (thread-safe).

        Returns:
            List of breaker types that were reset.
        """
        with self._lock:
            reset_types = [cb.value for cb in self._tripped]
            self._tripped.clear()
            self._tripped_at.clear()
            self._consecutive_losses = 0
            self._slippage_history.clear()
            self._last_heartbeat = _time.monotonic()
            self._daily_trade_count = 0
            self._daily_trade_date = ""
            if reset_types:
                logger.info(f"Circuit breakers manually reset: {reset_types}")
            return reset_types

    def reset_daily(self) -> None:
        """Reset daily-specific breakers (daily loss). Call at start of trading day (thread-safe)."""
        with self._lock:
            # Clear manually to avoid deadlock
            self._tripped.pop(CircuitBreakerType.DAILY_LOSS, None)
            self._tripped_at.pop(CircuitBreakerType.DAILY_LOSS, None)
            self._slippage_history.clear()

    def get_status(self) -> dict:
        """Get current circuit breaker status for API/status reporting (thread-safe)."""
        with self._lock:
            return {
                "is_tripped": len(self._tripped) > 0,
                "tripped_breakers": {k.value: v for k, v in self._tripped.items()},
                "consecutive_losses": self._consecutive_losses,
                "recent_slippages": len(self._slippage_history),
                "seconds_since_heartbeat": _time.monotonic() - self._last_heartbeat,
                "daily_trade_count": self._daily_trade_count,
                "daily_trade_date": self._daily_trade_date,
            }

    def _trip(self, cb_type: CircuitBreakerType, reason: str, epic: str = "global") -> None:
        """Trip a circuit breaker (thread-safe)."""
        with self._lock:
            if cb_type not in self._tripped:
                self._tripped[cb_type] = reason
                self._tripped_at[cb_type] = _time.monotonic()
                logger.warning(f"CIRCUIT BREAKER [{cb_type.value}]: {reason}")
                try:
                    from src.monitoring.metrics import MetricsCollector
                    MetricsCollector.record_circuit_breaker(epic=epic, reason=cb_type.value)
                except Exception:
                    pass

    def _clear(self, cb_type: CircuitBreakerType) -> None:
        """Clear a specific circuit breaker (thread-safe)."""
        with self._lock:
            self._tripped.pop(cb_type, None)
            self._tripped_at.pop(cb_type, None)

    def _try_auto_reset(self) -> list[str]:
        """
        Auto-reset breakers that have been tripped longer than the cooldown (thread-safe).

        Returns:
            List of breaker types that were auto-reset.
        """
        with self._lock:
            reset_types: list[str] = []
            now = _time.monotonic()
            cooldown = self.config.auto_reset_after_minutes * 60

            # Iterate over copy to avoid modification during iteration
            for cb_type in list(self._tripped_at.keys()):
                elapsed = now - self._tripped_at[cb_type]
                if elapsed >= cooldown:
                    # Clear manually to avoid deadlock (we already have the lock)
                    self._tripped.pop(cb_type, None)
                    self._tripped_at.pop(cb_type, None)
                    reset_types.append(cb_type.value)
                    logger.info(
                        f"Circuit breaker [{cb_type.value}] auto-reset "
                        f"after {elapsed / 60:.0f} minutes"
                    )

            return reset_types
