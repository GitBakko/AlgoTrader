"""
Transaction cost simulator for backtesting.
Models spread, slippage, and overnight fees for Capital.com CFDs.
"""


# Typical spreads for Capital.com demo (in price units, not pips)
# These are approximate mid-market values
ASSET_SPREADS = {
    "XAUUSD": 0.30,   # ~0.3 USD spread on Gold
    "BTCUSD": 30.0,   # ~30 USD spread on Bitcoin
    "US500": 0.40,    # ~0.4 points spread on S&P 500
}

# Typical overnight swap rates (daily, as fraction of position value)
# Long/Short rates differ; these are approximations
OVERNIGHT_RATES = {
    "XAUUSD": {"long": -0.000015, "short": -0.000010},
    "BTCUSD": {"long": -0.000020, "short": -0.000015},
    "US500": {"long": -0.000012, "short": -0.000008},
}

# Slippage as fraction of spread (additional cost on top of spread)
DEFAULT_SLIPPAGE_FACTOR = 0.1  # 10% of spread as extra slippage


class CostSimulator:
    """
    Simulates trading costs for realistic backtesting.

    Costs modeled:
    1. Spread: bid-ask spread (paid on entry and exit)
    2. Slippage: additional execution cost beyond spread
    3. Overnight fees: swap charges for holding positions overnight
    """

    def __init__(self, slippage_factor: float = DEFAULT_SLIPPAGE_FACTOR):
        """
        Args:
            slippage_factor: Additional slippage as fraction of spread
        """
        self.slippage_factor = slippage_factor

    def calculate_spread_cost(self, epic: str, size: float) -> float:
        """
        Calculate spread cost for a trade.

        Cost is spread * size, applied at both entry and exit (round-trip).

        Args:
            epic: Asset epic
            size: Position size in units

        Returns:
            Total spread cost (round-trip)
        """
        spread = ASSET_SPREADS.get(epic, 0.5)
        return spread * abs(size) * 2  # Round-trip

    def calculate_slippage(self, epic: str, size: float) -> float:
        """
        Calculate estimated slippage.

        Args:
            epic: Asset epic
            size: Position size

        Returns:
            Estimated slippage cost
        """
        spread = ASSET_SPREADS.get(epic, 0.5)
        return spread * self.slippage_factor * abs(size) * 2  # Round-trip

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
            nights: Number of nights held

        Returns:
            Total overnight fee (positive = cost)
        """
        rates = OVERNIGHT_RATES.get(epic, {"long": -0.000015, "short": -0.000010})
        rate_key = "long" if direction.upper() == "LONG" else "short"
        daily_rate = rates[rate_key]

        return abs(position_value * daily_rate * nights)

    def calculate_total_cost(
        self,
        epic: str,
        size: float,
        entry_price: float,
        direction: str,
        bars_held: int,
        timeframe_minutes: int,
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

        Returns:
            Total cost
        """
        # Spread + slippage
        cost = self.calculate_spread_cost(epic, size)
        cost += self.calculate_slippage(epic, size)

        # Overnight fees
        total_minutes = bars_held * timeframe_minutes
        nights = total_minutes // (24 * 60)

        if nights > 0:
            position_value = abs(entry_price * size)
            cost += self.calculate_overnight_fee(epic, position_value, direction, nights)

        return cost
