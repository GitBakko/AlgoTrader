"""
Risk management orchestrator.
Combines position sizing, stop management, drawdown monitoring,
and correlation checks into a unified risk check pipeline.
"""

from loguru import logger

from src.risk.correlation_guard import CorrelationGuard
from src.risk.drawdown_monitor import DrawdownMonitor
from src.risk.position_sizer import PositionSizer
from src.risk.schemas import DrawdownState, RiskCheckResult, RiskLimits
from src.risk.stop_manager import StopManager
from src.strategy.schemas import TradingSignal


class RiskManager:
    """
    Orchestrates all risk checks for a proposed trade.
    Pipeline: circuit breaker -> drawdown -> SL/TP -> correlation -> sizing.
    """

    def __init__(
        self,
        initial_equity: float = 10000.0,
        limits: RiskLimits | None = None,
    ):
        """
        Initialize risk manager.

        Args:
            initial_equity: Starting account equity
            limits: Risk limits (uses defaults if None)
        """
        self.limits = limits or RiskLimits()
        self.drawdown_monitor = DrawdownMonitor(initial_equity)

    def check_trade(
        self,
        signal: TradingSignal,
        equity: float,
        atr: float,
        open_positions: list[dict] | None = None,
    ) -> RiskCheckResult:
        """
        Run full risk check pipeline on a proposed trade.

        Args:
            signal: Trading signal to evaluate
            equity: Current account equity
            atr: Current ATR value for the asset
            open_positions: List of open positions (dicts with 'epic', 'direction')

        Returns:
            RiskCheckResult with approval status, size, SL, TP, and any adjustments
        """
        open_positions = open_positions or []
        adjustments: list[str] = []

        # 0. Validate inputs
        if atr <= 0:
            logger.warning(f"Trade rejected: invalid ATR={atr}")
            return RiskCheckResult(
                approved=False,
                rejection_reason=f"Invalid ATR value: {atr}",
            )

        # 1. Check circuit breaker
        if self.drawdown_monitor.is_circuit_breaker_active():
            reason = self.drawdown_monitor.state.circuit_breaker_reason or "Circuit breaker active"
            logger.warning(f"Trade rejected: {reason}")
            return RiskCheckResult(
                approved=False,
                rejection_reason=reason,
            )

        # 2. Update and check drawdown limits
        self.drawdown_monitor.update(equity)
        dd_ok, dd_reason = self.drawdown_monitor.check_limits(self.limits)
        if not dd_ok:
            self.drawdown_monitor.activate_circuit_breaker(dd_reason)
            logger.warning(f"Trade rejected (drawdown): {dd_reason}")
            return RiskCheckResult(
                approved=False,
                rejection_reason=dd_reason,
            )

        # 3. Calculate stop-loss
        stop_loss = StopManager.calculate_stop_loss(
            direction=signal.direction.value,
            entry_price=signal.entry_price,
            atr=atr,
            multiplier=2.0,
        )

        # Use signal's suggested stop if tighter
        if signal.suggested_stop is not None:
            if signal.direction.value == "BUY":
                stop_loss = max(stop_loss, signal.suggested_stop)
            else:
                stop_loss = min(stop_loss, signal.suggested_stop)
            adjustments.append("Using tighter suggested stop-loss")

        # 4. Calculate take-profit
        take_profit = StopManager.calculate_take_profit(
            direction=signal.direction.value,
            entry_price=signal.entry_price,
            atr=atr,
            multiplier=2.0,
            risk_reward=2.0,
        )

        if signal.suggested_tp is not None:
            take_profit = signal.suggested_tp
            adjustments.append("Using signal suggested take-profit")

        # 5. Check correlation exposure
        corr_multiplier, corr_warnings = CorrelationGuard.check_exposure(
            epic=signal.epic,
            direction=signal.direction.value,
            open_positions=open_positions,
        )
        adjustments.extend(corr_warnings)

        # 6. Calculate position size
        position_size = PositionSizer.calculate_size(
            equity=equity,
            risk_per_trade=self.limits.max_risk_per_trade,
            entry_price=signal.entry_price,
            stop_loss=stop_loss,
            confidence=signal.confidence,
            max_position_pct=self.limits.max_position_pct,
        )

        # Apply correlation multiplier
        if corr_multiplier < 1.0:
            position_size *= corr_multiplier

        if position_size <= 0:
            return RiskCheckResult(
                approved=False,
                rejection_reason="Calculated position size is zero",
            )

        logger.info(
            f"Risk check approved: {signal.epic} {signal.direction.value} "
            f"size={position_size:.4f} SL={stop_loss:.2f} TP={take_profit:.2f}"
        )

        return RiskCheckResult(
            approved=True,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            adjustments=adjustments,
        )

    def update_equity(self, equity: float) -> DrawdownState:
        """
        Update equity tracking.

        Args:
            equity: Current account equity

        Returns:
            Updated drawdown state
        """
        return self.drawdown_monitor.update(equity)

    def reset_daily(self) -> None:
        """Reset daily P&L tracking."""
        self.drawdown_monitor.reset_daily()
