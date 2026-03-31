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
from src.utils.config import get_settings


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
        self.correlation_guard = CorrelationGuard()

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
        audit: dict = {}

        # 0. Validate inputs
        if atr <= 0:
            logger.warning(f"Trade rejected: invalid ATR={atr}")
            return RiskCheckResult(
                approved=False,
                rejection_reason=f"Invalid ATR value: {atr}",
                audit=audit,
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
        audit["circuit_breakers"] = {
            "passed": cb_ok,
            "daily_pnl_pct": round(daily_pnl_pct, 4),
            "open_positions": len(open_positions),
            "reasons": cb_reasons if not cb_ok else [],
        }
        if not cb_ok:
            reason = "; ".join(cb_reasons)
            logger.warning(f"Trade rejected (circuit breaker): {reason}")
            return RiskCheckResult(
                approved=False,
                rejection_reason=reason,
                circuit_breaker_details={
                    "tripped": self.circuit_breakers.tripped_breakers,
                    "consecutive_losses": self.circuit_breakers._consecutive_losses,
                },
                audit=audit,
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

        # 1c. Check total exposure cap
        if self.limits.max_total_exposure < 1.0 and open_positions and equity > 0:
            total_notional = sum(
                abs(p.get("size", 0) * p.get("level", p.get("entry_price", 0)))
                for p in open_positions
            )
            exposure_ratio = total_notional / equity
            if exposure_ratio >= self.limits.max_total_exposure:
                reason = (
                    f"Total exposure {exposure_ratio:.1%} >= limit "
                    f"{self.limits.max_total_exposure:.0%}"
                )
                logger.warning(f"Trade rejected: {reason}")
                return RiskCheckResult(
                    approved=False,
                    rejection_reason=reason,
                )

        # 1d. Check legacy drawdown circuit breaker
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
        dd_pct = self.drawdown_monitor.state.current_drawdown_pct
        audit["drawdown"] = {
            "passed": dd_ok,
            "current_dd_pct": round(dd_pct, 4) if isinstance(dd_pct, (int, float)) else 0.0,
            "equity": equity,
            "reason": dd_reason if not dd_ok else None,
        }
        if not dd_ok:
            self.drawdown_monitor.activate_circuit_breaker(dd_reason)
            logger.warning(f"Trade rejected (drawdown): {dd_reason}")
            return RiskCheckResult(
                approved=False,
                rejection_reason=dd_reason,
                audit=audit,
            )

        # 3. Calculate stop-loss with dynamic multiplier (volatility-scaled)
        _risk_settings = get_settings()
        if _risk_settings.scalp_mode_enabled:
            base_sl = _risk_settings.scalp_sl_multiplier
            sl_min = _risk_settings.scalp_dynamic_sl_min
            sl_max = _risk_settings.scalp_dynamic_sl_max
        else:
            base_sl = 2.0
            sl_min, sl_max = 1.5, 4.0
        baseline_atr = self.circuit_breakers.get_baseline_atr(signal.epic)
        stop_mult = StopManager.dynamic_multiplier(
            base_multiplier=base_sl,
            current_atr=atr,
            baseline_atr=baseline_atr,
            min_multiplier=sl_min,
            max_multiplier=sl_max,
        )
        if abs(stop_mult - base_sl) > 0.01:
            adjustments.append(
                f"Dynamic SL multiplier: {stop_mult:.2f}x (base={base_sl}, vol ratio={atr/baseline_atr:.2f})"
            )
        stop_loss = StopManager.calculate_stop_loss(
            direction=signal.direction.value,
            entry_price=signal.entry_price,
            atr=atr,
            multiplier=stop_mult,
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

        # 4. Calculate take-profit (uses same dynamic multiplier for consistency)
        rr_ratio = _risk_settings.scalp_tp_risk_reward if _risk_settings.scalp_mode_enabled else 2.5
        take_profit = StopManager.calculate_take_profit(
            direction=signal.direction.value,
            entry_price=signal.entry_price,
            atr=atr,
            multiplier=stop_mult,
            risk_reward=rr_ratio,
        )

        if signal.suggested_tp is not None:
            take_profit = signal.suggested_tp
            adjustments.append("Using signal suggested take-profit")

        audit["stop_loss"] = {
            "dynamic_multiplier": round(stop_mult, 4),
            "base_multiplier": base_sl,
            "baseline_atr": (
                round(baseline_atr, 5) if isinstance(baseline_atr, (int, float)) else None
            ),
            "stop_loss": round(stop_loss, 5),
            "take_profit": round(take_profit, 5),
        }

        # 5. Check correlation exposure
        corr_multiplier, corr_warnings = CorrelationGuard.check_exposure(
            epic=signal.epic,
            direction=signal.direction.value,
            open_positions=open_positions,
        )
        adjustments.extend(corr_warnings)

        audit["correlation"] = {
            "multiplier": round(corr_multiplier, 4),
            "warnings": corr_warnings,
        }

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
            risk_per_trade = (
                _risk_settings.scalp_max_risk_per_trade
                if _risk_settings.scalp_mode_enabled
                else self.limits.max_risk_per_trade
            )
            position_size = PositionSizer.calculate_size(
                equity=equity,
                risk_per_trade=risk_per_trade,
                entry_price=signal.entry_price,
                stop_loss=stop_loss,
                confidence=signal.confidence,
                max_position_pct=self.limits.max_position_pct,
            )

        # Apply correlation multiplier
        if corr_multiplier < 1.0:
            position_size *= corr_multiplier

        # 6b. Confidence tiering
        conf_mult = self.confidence_size_multiplier(signal.confidence)
        audit["confidence_tier"] = {
            "confidence": round(signal.confidence, 4),
            "multiplier": conf_mult,
        }
        if conf_mult < 1.0:
            adjustments.append(f"Confidence tier: {conf_mult:.0%} (conf={signal.confidence:.2f})")
            position_size *= conf_mult

        # 7. Apply equity curve filter
        eq_multiplier = self.equity_curve_filter.get_size_multiplier()
        if eq_multiplier < 1.0:
            position_size *= eq_multiplier
            adjustments.append(f"Equity curve filter: size reduced {eq_multiplier:.0%}")

        audit["sizing"] = {
            "method": sizing_method,
            "raw_size": round(position_size, 6),
            "corr_multiplier": round(corr_multiplier, 4),
        }

        if position_size <= 0:
            return RiskCheckResult(
                approved=False,
                rejection_reason="Calculated position size is zero",
                audit=audit,
            )

        # 8. Calculate multi-target TP1/TP2
        risk_distance = abs(signal.entry_price - stop_loss)
        if signal.direction.value == "BUY":
            tp1 = signal.entry_price + risk_distance * 1.0  # 1:1 R:R
            tp2 = signal.entry_price + risk_distance * 2.0  # 2:1 R:R
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
            audit=audit,
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

    @staticmethod
    def confidence_size_multiplier(confidence: float) -> float:
        """Scale position size by confidence tier.

        < 0.15: 0.0 (rejected — too low even for reduced sizing)
        0.15-0.30: 0.25x (ML-disagree signals with confluence)
        0.30-0.45: 0.50x
        0.45-0.60: 0.75x
        >= 0.60: 1.0x
        """
        if confidence < 0.15:
            return 0.0
        elif confidence < 0.30:
            return 0.25
        elif confidence < 0.45:
            return 0.50
        elif confidence < 0.60:
            return 0.75
        return 1.0
