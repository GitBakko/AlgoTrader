"""
Transaction cost simulator for backtesting.
Models spread, slippage, and overnight fees for Capital.com CFDs.
"""

from datetime import datetime, timedelta

from loguru import logger

# Capital.com typical FULL bid-ask spreads (in price units).
# These represent the full spread (ask - bid), not the half-spread.
# Recalibrated 2026-05-23 from 74h passive snapshot collector (n=14,349 tradeable
# obs across 21 epics). Values = measured_p95 × 1.1 buffer (Phase 3-bis methodology).
# See `backend/docs/reports/2026-05-23_phase3-bis_spread_recalibration_PROPOSAL.md`
# + `data/diagnostics/spread_audit/2026-05.parquet`.
ASSET_SPREADS = {
    # Crypto (Capital.com demo)
    "XAUUSD": 0.825,  # p95 0.75 × 1.1 (was 0.60)
    "BTCUSD": 55.0,  # p95 50.0 × 1.1 (was 60.0)
    "ETHUSD": 1.925,  # p95 1.75 × 1.1 (was 2.10)
    "SOLUSD": 0.481,  # p95 0.4373 × 1.1 (was 0.50)
    "BNBUSD": 3.63,  # p95 3.30 × 1.1 (was 3.75)
    # Indices
    "US500": 0.66,  # p95 0.60 × 1.1 (was 0.50)
    "DE40": 8.80,  # p95 8.00 × 1.1 (was 1.00 — +780% understated, Asia session spike)
    # Commodities
    "WTIUSD": 0.044,  # p95 0.04 × 1.1 (was 0.04)
    "PLATINUM": 7.70,  # p95 7.00 × 1.1 (was 1.00 — +670% understated)
    "COPPER": 0.0030,  # p95 0.0027 × 1.1 (was missing)
    # US Stocks (high session-dependent variance, p95 dominated by Asia/pre-market)
    "TSLA": 0.495,  # p95 0.45 × 1.1 (was 0.10 — +395% understated)
    "NVDA": 0.308,  # p95 0.28 × 1.1 (was 0.10 — +208% understated)
    "AAPL": 0.517,  # p95 0.47 × 1.1 (was missing)
    "MSFT": 0.66,  # p95 0.60 × 1.1 (was missing)
    "GOOGL": 0.583,  # p95 0.53 × 1.1 (was missing)
    "AMZN": 0.55,  # p95 0.50 × 1.1 (was missing)
    "META": 1.144,  # p95 1.04 × 1.1 (was missing)
    "AMD": 1.078,  # p95 0.98 × 1.1 (was missing)
    # Forex (USD-base / quote pairs)
    "USDJPY": 0.0154,  # p95 0.014 × 1.1 (was missing, fallback 0.5 was 32× too wide)
    "USDCAD": 0.00022,  # p95 0.0002 × 1.1 (was missing, fallback was 2272× too wide)
    "USDCHF": 0.00033,  # p95 0.0003 × 1.1 (was missing, fallback was 1515× too wide)
}

# Typical overnight swap rates (daily, as fraction of position value).
# Long/Short rates differ; weekend Fri/Sat charged 3x (handled in engine).
# Sources: Capital.com demo public swap tables (2026-04-28 sample).
OVERNIGHT_RATES = {
    "XAUUSD": {"long": -0.000015, "short": -0.000010},
    "BTCUSD": {"long": -0.000020, "short": -0.000015},
    "ETHUSD": {"long": -0.000018, "short": -0.000013},
    "SOLUSD": {"long": -0.000022, "short": -0.000017},
    "BNBUSD": {"long": -0.000020, "short": -0.000015},
    "US500": {"long": -0.000012, "short": -0.000008},
    "WTIUSD": {"long": -0.000015, "short": -0.000012},
    "DE40": {"long": -0.000010, "short": -0.000007},
    "PLATINUM": {"long": -0.000015, "short": -0.000011},
    "TSLA": {"long": -0.000018, "short": -0.000014},
    "NVDA": {"long": -0.000018, "short": -0.000014},
}

# Slippage as fraction of spread (additional cost on top of spread)
DEFAULT_SLIPPAGE_FACTOR = 0.1  # 10% of spread as extra slippage

# Extra slippage on stop-loss fills (market orders in volatile conditions)
SL_SLIPPAGE_FACTOR = 0.5  # 50% of spread as additional SL slippage

# Fallback spread for epics missing from ASSET_SPREADS.
# The legacy flat 0.5 (absolute price units) was catastrophic for low-priced /
# forex epics — e.g. DOGUSD ~$0.10 received a $0.50 "spread" = 500%, NATGAS ~$2.8
# got 18%, GBPUSD ~1.27 got 39%. That silently corrupted any reactivation-screening
# backtest on excluded assets. Use a proportional fraction of price instead, and
# warn so the gap gets a measured value from a spread audit. NOTE: every CURRENTLY
# tradable epic is already listed above, so this path only affects excluded-asset
# screening — current backtests are unchanged.
SPREAD_FALLBACK_PCT = 0.0008  # ~8 bps of price (mid of listed ~1.3–60 bps range)
_FLAT_SPREAD_FALLBACK = 0.5  # last resort only when no reference price is available
_warned_missing_spread: set[str] = set()


def resolve_spread(epic: str, price: float | None = None) -> float:
    """Return the spread (price units) for an epic.

    Uses the measured ASSET_SPREADS value when present. For unlisted epics,
    falls back to a fraction of the reference price (never the nonsensical flat
    absolute default) and warns once per epic.
    """
    spread = ASSET_SPREADS.get(epic)
    if spread is not None:
        return spread
    if epic not in _warned_missing_spread:
        _warned_missing_spread.add(epic)
        mode = (
            f"proportional {SPREAD_FALLBACK_PCT}×price"
            if price and price > 0
            else f"flat {_FLAT_SPREAD_FALLBACK}"
        )
        logger.warning(
            f"No ASSET_SPREADS entry for {epic!r} — using {mode} fallback. "
            f"Add a measured spread in src/backtest/costs.py before trusting "
            f"backtests on this epic."
        )
    if price and price > 0:
        return price * SPREAD_FALLBACK_PCT
    return _FLAT_SPREAD_FALLBACK


class CostSimulator:
    """
    Simulates trading costs for realistic backtesting.

    Costs modeled:
    1. Spread: full bid-ask spread (paid once per round-trip)
    2. Slippage: additional execution cost beyond spread
    3. SL slippage: extra slippage on stop-loss fills (volatile market orders)
    4. Overnight fees: swap charges with weekend 3x multiplier
    """

    def __init__(self, slippage_factor: float = DEFAULT_SLIPPAGE_FACTOR):
        self.slippage_factor = slippage_factor

    def calculate_spread_cost(self, epic: str, size: float, price: float | None = None) -> float:
        """
        Calculate spread cost for a round-trip trade.

        The spread values are FULL bid-ask spreads. A round-trip crosses
        the spread once (buy at ask, sell at bid), so cost = spread * size.

        Args:
            epic: Asset epic
            size: Position size in units
            price: Reference price, used only for the proportional fallback
                when the epic is missing from ASSET_SPREADS

        Returns:
            Total spread cost (round-trip)
        """
        spread = resolve_spread(epic, price)
        return spread * abs(size)

    def calculate_slippage(self, epic: str, size: float, price: float | None = None) -> float:
        """
        Calculate estimated slippage for normal exits (signal-based).

        Args:
            epic: Asset epic
            size: Position size
            price: Reference price for the proportional fallback (unlisted epics)

        Returns:
            Estimated slippage cost
        """
        spread = resolve_spread(epic, price)
        return spread * self.slippage_factor * abs(size)

    def calculate_sl_slippage(self, epic: str, size: float, price: float | None = None) -> float:
        """
        Calculate extra slippage for stop-loss fills.

        Stop losses trigger market orders in potentially volatile conditions,
        resulting in worse fills than normal exits.

        Args:
            epic: Asset epic
            size: Position size
            price: Reference price for the proportional fallback (unlisted epics)

        Returns:
            Additional SL slippage cost
        """
        spread = resolve_spread(epic, price)
        return spread * SL_SLIPPAGE_FACTOR * abs(size)

    def calculate_overnight_fee(
        self,
        epic: str,
        position_value: float,
        direction: str,
        nights: int,
    ) -> float:
        """
        Calculate overnight holding fees.

        Args:
            epic: Asset epic
            position_value: Notional value of position
            direction: "LONG" or "SHORT"
            nights: Effective number of nights (weekend nights pre-multiplied)

        Returns:
            Total overnight fee (positive = cost)
        """
        rates = OVERNIGHT_RATES.get(epic, {"long": -0.000015, "short": -0.000010})
        rate_key = "long" if direction.upper() == "LONG" else "short"
        daily_rate = rates[rate_key]

        return abs(position_value * daily_rate * nights)

    def _count_weekend_nights(
        self,
        entry_time: datetime | None,
        total_nights: int,
    ) -> tuple[int, int]:
        """
        Count weekday and weekend nights for overnight fee calculation.

        Weekend nights (Friday->Saturday and Saturday->Sunday) are charged
        at 3x the normal rate on Capital.com (triple swap).

        Returns:
            (weekday_nights, weekend_nights)
        """
        if entry_time is None or total_nights <= 0:
            return (total_nights, 0)

        weekday_nights = 0
        weekend_nights = 0
        current = entry_time

        for _ in range(total_nights):
            day_of_week = current.weekday()
            if day_of_week in (4, 5):  # Friday night or Saturday night
                weekend_nights += 1
            else:
                weekday_nights += 1
            current += timedelta(days=1)

        return (weekday_nights, weekend_nights)

    def calculate_total_cost(
        self,
        epic: str,
        size: float,
        entry_price: float,
        direction: str,
        bars_held: int,
        timeframe_minutes: int,
        is_sl_exit: bool = False,
        entry_time: datetime | None = None,
    ) -> float:
        """
        Calculate total transaction cost for a trade.

        Args:
            epic: Asset epic
            size: Position size
            entry_price: Entry price
            direction: Trade direction
            bars_held: Number of bars the position was held
            timeframe_minutes: Minutes per bar (for overnight calculation)
            is_sl_exit: True if trade was closed by stop loss (extra slippage)
            entry_time: Entry timestamp (for weekend fee calculation)

        Returns:
            Total cost
        """
        # Spread (full bid-ask, round-trip)
        cost = self.calculate_spread_cost(epic, size, entry_price)

        # Normal slippage
        cost += self.calculate_slippage(epic, size, entry_price)

        # Extra SL slippage for stop-loss exits
        if is_sl_exit:
            cost += self.calculate_sl_slippage(epic, size, entry_price)

        # Overnight fees with weekend multiplier
        total_minutes = bars_held * timeframe_minutes
        total_nights = total_minutes // (24 * 60)

        if total_nights > 0:
            position_value = abs(entry_price * size)

            weekday_nights, weekend_nights = self._count_weekend_nights(
                entry_time,
                total_nights,
            )

            # Weekend nights charged at 3x (Capital.com triple swap)
            effective_nights = weekday_nights + weekend_nights * 3

            if effective_nights > 0:
                cost += self.calculate_overnight_fee(
                    epic,
                    position_value,
                    direction,
                    effective_nights,
                )

        return cost
