"""
Cross-asset correlation exposure checker.
Reduces position size when correlated assets have open positions in the same direction.
"""

from loguru import logger

# Hardcoded correlation pairs for MVP
# Format: (asset_a, asset_b, size_reduction_factor)
# If both have positions in same direction, reduce new position by this factor
CORRELATION_PAIRS: list[tuple[str, str, float]] = [
    ("XAUUSD", "BTCUSD", 0.50),  # Gold <-> BTC: 50% size reduction
    ("BTCUSD", "US500", 0.30),  # BTC <-> SP500: 30% size reduction
    ("XAUUSD", "XAGUSD", 0.85),  # Gold <-> Silver: 85% reduction (very correlated)
    ("US500", "DE40", 0.70),  # S&P 500 <-> DAX: 70% reduction (equity indices)
    ("NVDA", "TSLA", 0.50),  # NVIDIA <-> Tesla: 50% (both tech megacaps)
    ("US500", "NVDA", 0.40),  # S&P 500 <-> NVIDIA: 40% (index contains stock)
    ("US500", "TSLA", 0.40),  # S&P 500 <-> Tesla: 40% (index contains stock)
    ("WTIUSD", "XAUUSD", 0.25),  # Crude Oil <-> Gold: 25% (commodities, weak)
    ("BTCUSD", "NVDA", 0.30),  # BTC <-> NVIDIA: 30% (risk-on assets)
]

# Map epic variants to canonical names for matching
EPIC_ALIASES: dict[str, str] = {
    "GOLD": "XAUUSD",
    "BITCOIN": "BTCUSD",
    "SP500": "US500",
    "SILVER": "XAGUSD",
    "OIL_CRUDE": "WTIUSD",
    "GERMANY40": "DE40",
}


def _normalize_epic(epic: str) -> str:
    """Normalize epic to canonical form."""
    return EPIC_ALIASES.get(epic.upper(), epic.upper())


class CorrelationGuard:
    """Checks cross-asset correlation exposure and adjusts position sizes."""

    @staticmethod
    def check_exposure(
        epic: str,
        direction: str,
        open_positions: list[dict],
    ) -> tuple[float, list[str]]:
        """
        Check if opening a new position would create excessive correlated exposure.

        Args:
            epic: Epic of the new position
            direction: Direction of the new position ("BUY" or "SELL")
            open_positions: List of open positions as dicts with 'epic' and 'direction' keys

        Returns:
            Tuple of (size_multiplier, warnings).
            size_multiplier: 1.0 = no reduction, 0.5 = halve size, etc.
            warnings: List of warning messages about correlated exposure.
        """
        normalized_epic = _normalize_epic(epic)
        size_multiplier = 1.0
        warnings: list[str] = []

        for asset_a, asset_b, reduction in CORRELATION_PAIRS:
            # Check if our epic is one of the correlated pair
            correlated_epic: str | None = None
            if normalized_epic == asset_a:
                correlated_epic = asset_b
            elif normalized_epic == asset_b:
                correlated_epic = asset_a
            else:
                continue

            # Check if any open position matches the correlated epic and same direction
            for pos in open_positions:
                pos_epic = _normalize_epic(pos.get("epic", ""))
                pos_direction = pos.get("direction", "")

                if pos_epic == correlated_epic and pos_direction == direction:
                    new_mult = 1.0 - reduction
                    if new_mult < size_multiplier:
                        size_multiplier = new_mult
                        warnings.append(
                            f"Correlated exposure: {epic} {direction} with "
                            f"{correlated_epic} {pos_direction} -> "
                            f"size reduced by {reduction:.0%}"
                        )

        if warnings:
            logger.info(
                f"Correlation guard for {epic} {direction}: "
                f"multiplier={size_multiplier:.2f}, warnings={len(warnings)}"
            )

        return size_multiplier, warnings
