"""
Per-asset price rounding utilities.

Capital.com requires SL/TP and price levels to be rounded to a specific
decimal precision per asset class. Indices typically use 1 decimal,
forex 4-5 decimals, crypto varies, etc.
"""

# Decimal places per epic (Capital.com tick precision)
# Add new epics as needed
PRICE_DECIMALS: dict[str, int] = {
    # Indices: 1 decimal
    "US500": 1,
    "DE40": 1,
    "NAS100": 1,
    # Stocks: 2 decimals
    "NVDA": 2,
    "TSLA": 2,
    # Commodities (precious metals): 2 decimals
    "XAUUSD": 2,
    "XAGUSD": 3,
    "PLATINUM": 1,
    "COPPER": 4,
    "WTIUSD": 2,
    "NATGAS": 3,
    # Forex: 5 decimals (4 for JPY)
    "EURUSD": 5,
    "GBPUSD": 5,
    "USDJPY": 3,
    # Crypto: varies
    "BTCUSD": 1,
    "ETHUSD": 2,
    "SOLUSD": 3,
    "BNBUSD": 2,
    "DOGUSD": 5,
    "DASHUSD": 2,
    "ICPUSD": 3,
}

DEFAULT_DECIMALS = 4


def round_price(epic: str, price: float | None) -> float | None:
    """Round a price level to the broker's required precision for the given epic.

    Args:
        epic: Asset epic (e.g. "US500", "XAUUSD")
        price: Raw price value

    Returns:
        Price rounded to the asset's tick precision, or None if input is None
    """
    if price is None:
        return None
    decimals = PRICE_DECIMALS.get(epic, DEFAULT_DECIMALS)
    return round(price, decimals)
