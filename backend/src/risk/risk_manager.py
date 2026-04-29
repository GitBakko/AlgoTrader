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
from src.utils.constants import FOREX_ASSETS


def _compute_risk_usd(
    epic: str, entry: float, stop_loss: float, size: float
) -> float:
    """Compute USD-denominated risk on a trade given size + stop distance.

    Non-forex (stocks/crypto/commodities/indices): price is in USD per
    unit, so ``size * |entry - SL|`` is already a USD figure.

    Forex with USD as **base** (USDJPY): ``size * stop_distance`` is in
    the quote currency (JPY); convert to USD by dividing by the entry
    price (USDJPY ≈ JPY-per-USD).

    Forex with USD as **quote** (EURUSD, GBPUSD): ``size * stop_distance``
    is already in USD because the quote leg is USD.

    Returns ``0.0`` defensively when the inputs cannot produce a number.
    """
    try:
        stop_distance = abs(float(entry) - float(stop_loss))
        size_f = float(size)
    except (TypeError, ValueError):
        return 0.0
    if stop_distance <= 0 or size_f <= 0:
        return 0.0
    if epic in FOREX_ASSETS and epic.startswith("USD") and float(entry) > 0:
        # USD-base, foreign quote → loss is in quote currency, convert to USD
        return (size_f * stop_distance) / float(entry)
    return size_f * stop_distance


def _position_notional_account_ccy(
    position: dict, account_currency: str = "USD"
) -> float:
    """Estimate per-position notional in the account currency.

    The naive ``size * entry_price`` formula is correct only when the
    position's quote currency matches the account currency (true for
    every USD-quoted CFD: NVDA, BTCUSD, EURUSD, XAUUSD …). It silently
    breaks for FX pairs where the account currency is the *base* and
    the quote is foreign — most notably ``USDJPY`` / ``USDCHF``: with
    Capital.com sizes denominated in the base (USD) units,
    ``100 * 159.286`` yielded a phantom 15.9 k USD notional and tripped
    the 80% total-exposure guard with a single 100-USD position.

    Heuristic (no async FX call, fits the synchronous risk_manager
    contract):

    1. ``position.currency == account_currency`` → quote already in
       account ccy → ``size * level``.
    2. Epic of the form ``ACCOUNT_CCY + XXX`` (e.g. ``USDJPY`` for a
       USD account) → notional in account ccy = ``size``.
    3. Fallback → ``size * level`` (preserves legacy behaviour for
       exotic/cross-currency cases until a proper FxConverter pre-pass
       lands).
    """
    size = abs(float(position.get("size", 0) or 0))
    level = float(position.get("level", position.get("entry_price", 0)) or 0)
    if size == 0 or level == 0:
        return 0.0

    epic = (position.get("epic") or "").upper()
    pos_currency = (position.get("currency") or "").upper()
    account_ccy = (account_currency or "USD").upper()
    # Normalise broker quirks like "USDd" → "USD".
    if pos_currency.endswith("D") and len(pos_currency) == 4:
        pos_currency = pos_currency[:-1]

    if pos_currency and pos_currency == account_ccy:
        return size * level

    if len(epic) == 6 and epic.startswith(account_ccy):
        # FX pair AAA/BBB where AAA == account currency. Capital.com
        # sizes the contract in base units, so notional in the account
        # currency is exactly the size — independent of `level`.
        return size

    return size * level


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
                _position_notional_account_ccy(p, account_currency="USD")
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

        # 4. Calculate take-profit (default ATR-based, used when strategy
        #    didn't pair suggested_stop with suggested_tp).
        rr_ratio = _risk_settings.scalp_tp_risk_reward if _risk_settings.scalp_mode_enabled else 2.5
        take_profit = StopManager.calculate_take_profit(
            direction=signal.direction.value,
            entry_price=signal.entry_price,
            atr=atr,
            multiplier=stop_mult,
            risk_reward=rr_ratio,
        )

        # 4-bis. Reconcile strategy-suggested SL/TP with risk-manager defaults.
        #
        # BUG FIX 2026-04-28: previous logic used `min()` for BUY-SL and
        # `max()` for SELL-SL with a comment claiming this picked the
        # *tighter* stop.  Both inversions were wrong:
        #   - BUY-SL is below entry → tighter SL has the LARGER price
        #     (closer to entry going up from below) → use `max()`.
        #   - SELL-SL is above entry → tighter SL has the SMALLER price → `min()`.
        # Combined with an unconditional TP override from `suggested_tp`,
        # this produced the inverted R:R seen in production (SL ~3-4×ATR
        # from risk_mgr, TP ~0.75×ATR from MR strategy → R:R 0.13-0.30).
        #
        # New rule: when the strategy paired suggested_stop AND
        # suggested_tp, trust the pair as-is — strategy authors calibrate
        # them together for an intentional R:R.  When only one side is
        # suggested, take the genuinely-tighter of the pair.
        if signal.suggested_stop is not None and signal.suggested_tp is not None:
            stop_loss = signal.suggested_stop
            take_profit = signal.suggested_tp
            adjustments.append("Using strategy-calibrated SL/TP pair")
        elif signal.suggested_stop is not None:
            if signal.direction.value == "BUY":
                # BUY-SL below entry → tighter = larger value
                stop_loss = max(stop_loss, signal.suggested_stop)
            else:
                # SELL-SL above entry → tighter = smaller value
                stop_loss = min(stop_loss, signal.suggested_stop)
            adjustments.append("Using tighter suggested stop-loss")
        elif signal.suggested_tp is not None:
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

        # 5. Check correlation exposure (dynamic matrix if available, else static)
        corr_multiplier, corr_warnings = self.correlation_guard.check_exposure_dynamic(
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
                min_notional_usd=_risk_settings.min_notional_usd,
                epic=signal.epic,
                forex_usd_base_size_multiplier=(
                    _risk_settings.forex_usd_base_size_multiplier
                ),
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
                min_notional_usd=_risk_settings.min_notional_usd,
                epic=signal.epic,
                forex_usd_base_size_multiplier=(
                    _risk_settings.forex_usd_base_size_multiplier
                ),
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

        # 7-bis. Minimum *risk* amount floor (USD).
        # MIN_NOTIONAL_USD already lifts the notional, but for forex pairs
        # with a non-USD quote (USDJPY) the realised USD risk of the
        # trade can still be a fraction of a dollar. We compute the true
        # USD risk via `_compute_risk_usd` (which respects the quote leg),
        # then lift size proportionally to clear the floor. The lift is
        # capped by ``max_position_pct``: if the floor cannot be met under
        # the cap (typical for USDJPY where pip-risk on a 0.06 lot is
        # ~$0.02 and clearing $5 would need 250x size), we **fall back to
        # the cap-bounded size** rather than rejecting the signal — a
        # small-but-real position is closer to user intent than a blocked
        # one. The shortfall is surfaced in audit so monitoring catches
        # systematic floor mismatches.
        min_risk_floor = float(_risk_settings.min_risk_amount_usd or 0)
        if min_risk_floor > 0:
            risk_amount_usd = _compute_risk_usd(
                epic=signal.epic,
                entry=signal.entry_price,
                stop_loss=stop_loss,
                size=position_size,
            )
            if risk_amount_usd > 0 and risk_amount_usd < min_risk_floor:
                risk_per_unit = risk_amount_usd / position_size
                lifted_size = min_risk_floor / risk_per_unit
                # Mirror the leverage-aware cap used by PositionSizer / KellySizer
                # so the floor lift respects the same per-trade budget that
                # produced ``position_size``. Without this, USD-base forex
                # signals would be capped at the stock-equivalent cap here
                # even though the sizer was allowed up to leverage_multiplier ×.
                effective_pct = self.limits.max_position_pct
                if (
                    signal.epic in FOREX_ASSETS
                    and signal.epic.startswith("USD")
                ):
                    try:
                        _fx_mult = float(_risk_settings.forex_usd_base_size_multiplier)
                    except (TypeError, ValueError):
                        _fx_mult = 1.0
                    if _fx_mult > 1.0:
                        effective_pct = self.limits.max_position_pct * _fx_mult
                max_size_by_exposure = (
                    equity * effective_pct
                ) / signal.entry_price if signal.entry_price else 0.0
                # Final size = the lift if the cap allows it, else the cap.
                # PositionSizer already enforces ``size <= max_size_by_exposure``
                # so ``position_size <= max_size_by_exposure`` is invariant on
                # the entry to this branch — final_size is therefore always
                # >= position_size and we never *shrink* the position here.
                final_size = (
                    min(lifted_size, max_size_by_exposure)
                    if max_size_by_exposure > 0
                    else 0.0
                )
                if final_size <= 0:
                    # Cap is zero (zero or negative equity) — reject
                    # defensively. Should not happen in normal operation.
                    audit["min_risk_floor"] = {
                        "computed_risk_usd": round(risk_amount_usd, 4),
                        "floor_usd": min_risk_floor,
                        "lifted_size": round(lifted_size, 6),
                        "max_size_by_exposure": round(max_size_by_exposure, 6),
                        "approved": False,
                    }
                    return RiskCheckResult(
                        approved=False,
                        rejection_reason=(
                            f"error.min_notional risk_amount=${risk_amount_usd:.2f} "
                            f"< floor=${min_risk_floor:.2f} and exposure cap "
                            f"is non-positive"
                        ),
                        audit=audit,
                    )
                final_risk = _compute_risk_usd(
                    epic=signal.epic,
                    entry=signal.entry_price,
                    stop_loss=stop_loss,
                    size=final_size,
                )
                lift_bounded_by_cap = final_size < lifted_size
                if lift_bounded_by_cap:
                    adjustments.append(
                        f"MIN_RISK_AMOUNT_USD floor capped by exposure cap "
                        f"({position_size:.4f} → {final_size:.4f}, "
                        f"risk ${risk_amount_usd:.2f} → ${final_risk:.2f}, "
                        f"floor=${min_risk_floor:.2f} not reached)"
                    )
                else:
                    adjustments.append(
                        f"Lifted size for MIN_RISK_AMOUNT_USD floor "
                        f"({position_size:.4f} → {final_size:.4f}, "
                        f"risk ${risk_amount_usd:.2f} → ${final_risk:.2f})"
                    )
                position_size = final_size
                risk_amount_usd = final_risk
                audit["min_risk_floor"] = {
                    "computed_risk_usd": round(risk_amount_usd, 4),
                    "floor_usd": min_risk_floor,
                    "intended_lifted_size": round(lifted_size, 6),
                    "actual_size": round(position_size, 6),
                    "max_size_by_exposure": round(max_size_by_exposure, 6),
                    "approved": True,
                    "lift_bounded_by_cap": lift_bounded_by_cap,
                }
            else:
                audit["min_risk_floor"] = {
                    "computed_risk_usd": round(risk_amount_usd, 4),
                    "floor_usd": min_risk_floor,
                    "approved": True,
                    "lift_bounded_by_cap": False,
                }

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
