"""
Transaction cost simulator for backtesting.
Models spread, slippage, and overnight fees for Capital.com CFDs.
"""

from datetime import datetime, timedelta


# Capital.com typical FULL bid-ask spreads (in price units)
# These represent the full spread (ask - bid), not the half-spread.
ASSET_SPREADS = {
    "XAUUSD": 0.40,   # ~0.40 USD full spread on Gold
    "BTCUSD": 50.0,   # ~50 USD full spread on Bitcoin
    "US500": 0.50,     # ~0.50 points full spread on S&P 500
}

# Typical overnight swap rates (daily, as fraction of position value)
# Long/Short rates differ; these are approximations for Capital.com demo
OVERNIGHT_RATES = {
    "XAUUSD": {"long": -0.000015, "short": -0.000010},
    "BTCUSD": {"long": -0.000020, "short": -0.000015},
    "US500": {"long": -0.000012, "short": -0.000008},
}

# Slippage as fraction of spread (additional cost on top of spread)
DEFAULT_SLIPPAGE_FACTOR = 0.1  # 10% of spread as extra slippage

# Extra slippage on stop-loss fills (market orders in volatile conditions)
SL_SLIPPAGE_FACTOR = 0.5  # 50% of spread as additional SL slippage


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

    def calculate_spread_cost(self, epic: str, size: float) -> float:
        """
        Calculate spread cost for a round-trip trade.

        The spread values are FULL bid-ask spreads. A round-trip crosses
        the spread once (buy at ask, sell at bid), so cost = spread * size.

        Args:
            epic: Asset epic
            size: Position size in units

        Returns:
            Total spread cost (round-trip)
        """
        spread = ASSET_SPREADS.get(epic, 0.5)
        return spread * abs(size)

    def calculate_slippage(self, epic: str, size: float) -> float:
        """
        Calculate estimated slippage for normal exits (signal-based).

        Args:
            epic: Asset epic
            size: Position size

        Returns:
            Estimated slippage cost
        """
        spread = ASSET_SPREADS.get(epic, 0.5)
        return spread * self.slippage_factor * abs(size)

    def calculate_sl_slippage(self, epic: str, size: float) -> float:
        """
        Calculate extra slippage for stop-loss fills.

        Stop losses trigger market orders in potentially volatile conditions,
        resulting in worse fills than normal exits.

        Args:
            epic: Asset epic
            size: Position size

        Returns:
            Additional SL slippage cost
        """
        spread = ASSET_SPREADS.get(epic, 0.5)
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
        cost = self.calculate_spread_cost(epic, size)

        # Normal slippage
        cost += self.calculate_slippage(epic, size)

        # Extra SL slippage for stop-loss exits
        if is_sl_exit:
            cost += self.calculate_sl_slippage(epic, size)

        # Overnight fees with weekend multiplier
        total_minutes = bars_held * timeframe_minutes
        total_nights = total_minutes // (24 * 60)

        if total_nights > 0:
            position_value = abs(entry_price * size)

            weekday_nights, weekend_nights = self._count_weekend_nights(
                entry_time, total_nights,
            )

            # Weekend nights charged at 3x (Capital.com triple swap)
            effective_nights = weekday_nights + weekend_nights * 3

            if effective_nights > 0:
                cost += self.calculate_overnight_fee(
                    epic, position_value, direction, effective_nights,
                )

        return cost
