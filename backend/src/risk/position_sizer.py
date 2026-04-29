"""
ATR-based position sizing with confidence scaling.
Formula from docs/03-ML-STRATEGY.md.
"""

from loguru import logger

from src.utils.constants import FOREX_ASSETS


def _is_usd_base_forex(epic: str | None) -> bool:
    """USD-base forex (USDJPY, USDCHF, USDCAD) — pip in foreign quote ccy.

    Capital.com sizes these in USD (base) units, so 1 unit of size carries
    a foreign-ccy P&L per pip that must be converted to USD via the live
    rate. Standard ``size * stop_distance`` gives a JPY/CHF/CAD figure
    which silently inflates risk in USD math.
    """
    return bool(epic) and epic in FOREX_ASSETS and epic.startswith("USD")


def _stop_distance_usd(epic: str | None, entry_price: float, stop_loss: float) -> float:
    """Stop distance expressed in USD per unit of size.

    For USD-base forex: stop_distance_quote / entry_price (USD per unit).
    For everything else (USD-quoted asset): stop_distance is already in
    USD per unit because the quote leg is USD.
    """
    raw = abs(entry_price - stop_loss)
    if _is_usd_base_forex(epic) and entry_price > 0:
        return raw / entry_price
    return raw


def _max_position_pct_for_epic(epic: str | None, base_pct: float, multiplier: float) -> float:
    """Apply the USD-base-forex multiplier to the per-trade exposure cap."""
    if not _is_usd_base_forex(epic):
        return base_pct
    try:
        m = float(multiplier)
    except (TypeError, ValueError):
        m = 1.0
    return base_pct * max(1.0, m)


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
        min_notional_usd: float | None = None,
        epic: str | None = None,
        forex_usd_base_size_multiplier: float = 1.0,
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
            min_notional_usd: Optional notional floor — when supplied, the
                final size is lifted so `size * entry_price >= floor`,
                still bounded by `max_position_pct`. Without it, FOREX
                micro-trades get sized to a few units (~$500 notional)
                where slippage + spread eat the entire edge.
            epic: Asset epic. When supplied for a USD-base forex pair
                (USDJPY/USDCHF/USDCAD), the sizer uses pip-aware risk
                (stop distance converted to USD) and applies
                ``forex_usd_base_size_multiplier`` to the exposure cap.
                Without the epic, the sizer falls back to the legacy
                same-ccy math which silently under-sizes USD-base forex.
            forex_usd_base_size_multiplier: Multiplier on the exposure cap
                for USD-base forex pairs (Capital.com forex leverage).
                No-op for non-forex epics.

        Returns:
            Position size (units of the asset)
        """
        if equity <= 0 or entry_price <= 0:
            return 0.0

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance < 1e-10:
            logger.warning("Stop distance is zero, cannot calculate position size")
            return 0.0

        # Base risk amount (USD)
        risk_amount = equity * risk_per_trade

        # Base position size from risk/stop distance — convert stop distance
        # to USD per unit so risk_amount/stop_distance is in size units.
        stop_distance_usd = _stop_distance_usd(epic, entry_price, stop_loss)
        if stop_distance_usd < 1e-12:
            logger.warning("USD stop distance is zero, cannot calculate position size")
            return 0.0
        # Note: confidence scaling is handled by RiskManager.confidence_size_multiplier()
        final_size = risk_amount / stop_distance_usd

        # Cap at max_position_pct of equity (leverage-aware for USD-base forex)
        effective_pct = _max_position_pct_for_epic(
            epic, max_position_pct, forex_usd_base_size_multiplier
        )
        max_size = (equity * effective_pct) / entry_price
        if final_size > max_size:
            logger.debug(
                f"Position size capped: {final_size:.4f} -> {max_size:.4f} "
                f"(max {effective_pct*100:.1f}% of equity, "
                f"epic={epic or 'n/a'})"
            )
            final_size = max_size

        # Notional floor: lift the size so the trade is worth taking in
        # the first place. Bounded by max_size so the floor cannot push
        # past the per-trade exposure cap. Defensive float cast guards
        # against mocked settings leaking a MagicMock through.
        try:
            min_notional = float(min_notional_usd) if min_notional_usd else 0.0
        except (TypeError, ValueError):
            min_notional = 0.0
        if min_notional > 0:
            min_size = min_notional / entry_price
            if final_size < min_size:
                bumped = min(min_size, max_size)
                if bumped > final_size:
                    logger.info(
                        f"Position size raised to notional floor: "
                        f"{final_size:.4f} → {bumped:.4f} "
                        f"(min ${min_notional:.0f}, capped at "
                        f"{max_position_pct * 100:.0f}% of equity)"
                    )
                    final_size = bumped

        return max(0.0, final_size)
