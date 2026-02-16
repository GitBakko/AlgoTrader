"""
Risk management orchestrator.
Combines position sizing, stop management, drawdown monitoring,
circuit breakers, equity curve filtering, and correlation checks
into a unified risk check pipeline.
"""

from loguru import logger

from src.risk.circuit_breakers import CircuitBreakerConfig, CircuitBreakerManager
from src.risk.correlation_guard import CorrelationGuard
from src.risk.drawdown_monitor import DrawdownMonitor
from src.risk.equity_curve_filter import EquityCurveConfig, EquityCurveFilter
from src.risk.kelly_sizer import AdaptiveKellySizer
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
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        equity_curve_config: EquityCurveConfig | None = None,
        kelly_sizer: AdaptiveKellySizer | None = None,
    ):
        """
        Initialize risk manager.

        Args:
            initial_equity: Starting account equity
            limits: Risk limits (uses defaults if None)
            circuit_breaker_config: Config for advanced circuit breakers (None = defaults)
            equity_curve_config: Config for equity curve filter (None = defaults)
            kelly_sizer: Adaptive Kelly sizer instance (None = disabled, uses fixed-fractional)
        """
        self.limits = limits or RiskLimits()
        self.initial_equity = initial_equity
        self.drawdown_monitor = DrawdownMonitor(initial_equity)
        self.circuit_breakers = CircuitBreakerManager(circuit_breaker_config)
        self.equity_curve_filter = EquityCurveFilter(equity_curve_config)
        self.kelly_sizer = kelly_sizer

    def check_trade(
        self,
        signal: TradingSignal,
        equity: float,
        atr: float,
        open_positions: list[dict] | None = None,
        trade_history: list[dict] | None = None,
    ) -> RiskCheckResult:
        """
        Run full risk check pipeline on a proposed trade.

        Args:
            signal: Trading signal to evaluate
            equity: Current account equity
            atr: Current ATR value for the asset
            open_positions: List of open positions (dicts with 'epic', 'direction')
            trade_history: Past trades for Kelly sizing (dicts with 'pnl')

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

        # 1. Check advanced circuit breakers
        daily_pnl_pct = 0.0
        daily_start = self.drawdown_monitor.state.daily_start_equity
        if daily_start > 0:
            daily_pnl_pct = (equity - daily_start) / daily_start

        cb_ok, cb_reasons = self.circuit_breakers.check_all(
            daily_pnl_pct=daily_pnl_pct,
            open_position_count=len(open_positions),
            current_atr=atr,
            baseline_atr=self.circuit_breakers.get_baseline_atr(signal.epic),
        )
        if not cb_ok:
            reason = "; ".join(cb_reasons)
            logger.warning(f"Trade rejected (circuit breaker): {reason}")
            return RiskCheckResult(
                approved=False,
                rejection_reason=reason,
                circuit_breaker_details={
                    "tripped": self.circuit_breakers.tripped_breakers,
                },
            )

        # 1b. Check max total open positions
        total_open = len(open_positions)
        if total_open >= self.limits.max_total_open_positions:
            reason = (
                f"Max total positions reached: {total_open}/{self.limits.max_total_open_positions}"
            )
            logger.warning(f"Trade rejected: {reason}")
            return RiskCheckResult(
                approved=False,
                rejection_reason=reason,
            )

        # 1c. Check legacy drawdown circuit breaker
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
        # CRITICAL FIX: Inverted logic was causing SL above entry for longs!
        # For BUY: SL must be BELOW entry, so we want the MIN (closer to entry)
        # For SELL: SL must be ABOVE entry, so we want the MAX (closer to entry)
        if signal.suggested_stop is not None:
            if signal.direction.value == "BUY":
                stop_loss = min(stop_loss, signal.suggested_stop)
            else:
                stop_loss = max(stop_loss, signal.suggested_stop)
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

        # 6. Calculate position size (Kelly or fixed-fractional)
        sizing_method = "fixed_fractional"
        if self.kelly_sizer is not None and trade_history:
            position_size, sizing_method = self.kelly_sizer.calculate_size(
                equity=equity,
                entry_price=signal.entry_price,
                stop_loss=stop_loss,
                confidence=signal.confidence,
                trade_history=trade_history,
                max_position_pct=self.limits.max_position_pct,
            )
            if sizing_method != "fixed_fractional":
                adjustments.append(f"Sizing: {sizing_method}")
        else:
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

        # 7. Apply equity curve filter
        eq_multiplier = self.equity_curve_filter.get_size_multiplier()
        if eq_multiplier < 1.0:
            position_size *= eq_multiplier
            adjustments.append(
                f"Equity curve filter: size reduced {eq_multiplier:.0%}"
            )

        if position_size <= 0:
            return RiskCheckResult(
                approved=False,
                rejection_reason="Calculated position size is zero",
            )

        # 8. Calculate multi-target TP1/TP2
        risk_distance = abs(signal.entry_price - stop_loss)
        if signal.direction.value == "BUY":
            tp1 = signal.entry_price + risk_distance * 1.0   # 1:1 R:R
            tp2 = signal.entry_price + risk_distance * 2.0   # 2:1 R:R
        else:
            tp1 = signal.entry_price - risk_distance * 1.0
            tp2 = signal.entry_price - risk_distance * 2.0

        logger.info(
            f"Risk check approved: {signal.epic} {signal.direction.value} "
            f"size={position_size:.4f} SL={stop_loss:.2f} TP={take_profit:.2f} "
            f"TP1={tp1:.2f} TP2={tp2:.2f} sizing={sizing_method}"
        )

        return RiskCheckResult(
            approved=True,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            take_profit_1=tp1,
            take_profit_2=tp2,
            adjustments=adjustments,
            sizing_method=sizing_method,
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
