"""
Cross-asset correlation exposure checker.
Reduces position size when correlated assets have open positions in the same direction.
Supports both hardcoded static pairs and a dynamic NxN correlation matrix.
"""

from __future__ import annotations

import numpy as np
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
    """Checks cross-asset correlation exposure and adjusts position sizes.

    Supports two modes:
    - Static: hardcoded CORRELATION_PAIRS (via class method ``check_exposure``)
    - Dynamic: live NxN correlation matrix (via instance method ``check_exposure_dynamic``)
    """

    def __init__(self) -> None:
        self._matrix: np.ndarray | None = None
        self._epic_index: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Dynamic matrix management
    # ------------------------------------------------------------------

    def update_matrix(self, epics: list[str], matrix: np.ndarray) -> None:
        """Store an NxN correlation matrix for the given epics.

        Args:
            epics: Ordered list of epic names (canonical form preferred).
            matrix: NxN numpy array of pairwise correlations.
        """
        self._epic_index = {_normalize_epic(e): i for i, e in enumerate(epics)}
        self._matrix = np.array(matrix, dtype=float)
        logger.info(f"Correlation matrix updated: {len(epics)} epics, shape={self._matrix.shape}")

    def get_dynamic_correlation(self, epic_a: str, epic_b: str) -> float | None:
        """Return the dynamic correlation between two epics, or None if unavailable."""
        if self._matrix is None:
            return None
        idx_a = self._epic_index.get(_normalize_epic(epic_a))
        idx_b = self._epic_index.get(_normalize_epic(epic_b))
        if idx_a is None or idx_b is None:
            return None
        return float(self._matrix[idx_a, idx_b])

    # ------------------------------------------------------------------
    # Dynamic exposure check
    # ------------------------------------------------------------------

    def check_exposure_dynamic(
        self,
        epic: str,
        direction: str,
        open_positions: list[dict],
    ) -> tuple[float, list[str]]:
        """Check correlated exposure using the dynamic matrix first, static fallback.

        For assets present in the dynamic matrix the absolute correlation value
        is used as the reduction factor.  Assets NOT in the matrix fall back to
        the hardcoded ``CORRELATION_PAIRS``.

        Only same-direction positions are penalised.

        Returns:
            Tuple of (size_multiplier, warnings).
        """
        normalized_epic = _normalize_epic(epic)
        size_multiplier = 1.0
        warnings: list[str] = []
        # Track which position epics were handled dynamically so we can
        # fall back to static for the rest.
        handled_epics: set[str] = set()

        for pos in open_positions:
            pos_epic = _normalize_epic(pos.get("epic", ""))
            pos_direction = pos.get("direction", "")

            # Only penalise same-direction positions
            if pos_direction != direction:
                continue

            # Skip self
            if pos_epic == normalized_epic:
                continue

            corr = self.get_dynamic_correlation(normalized_epic, pos_epic)
            if corr is not None:
                handled_epics.add(pos_epic)
                abs_corr = abs(corr)
                # M14 fix: clamp to [0, 1]. numpy float drift can yield
                # |corr| > 1.0 (1.0000000001 after matrix ops on highly
                # correlated pairs); without the clamp, new_mult goes
                # negative and propagates to a negative position size
                # that downstream rejects with a misleading "size zero"
                # message instead of surfacing the matrix anomaly.
                new_mult = max(0.0, 1.0 - abs_corr)
                if new_mult < size_multiplier:
                    size_multiplier = new_mult
                    warnings.append(
                        f"Dynamic correlated exposure: {epic} {direction} with "
                        f"{pos_epic} {pos_direction} -> "
                        f"corr={corr:.2f}, size reduced by {abs_corr:.0%}"
                    )

        # Static fallback for positions not covered by the dynamic matrix
        for asset_a, asset_b, reduction in CORRELATION_PAIRS:
            correlated_epic: str | None = None
            if normalized_epic == asset_a:
                correlated_epic = asset_b
            elif normalized_epic == asset_b:
                correlated_epic = asset_a
            else:
                continue

            if correlated_epic in handled_epics:
                continue

            for pos in open_positions:
                pos_epic = _normalize_epic(pos.get("epic", ""))
                pos_direction = pos.get("direction", "")
                if pos_epic == correlated_epic and pos_direction == direction:
                    new_mult = 1.0 - reduction
                    if new_mult < size_multiplier:
                        size_multiplier = new_mult
                        warnings.append(
                            f"Static correlated exposure: {epic} {direction} with "
                            f"{correlated_epic} {pos_direction} -> "
                            f"size reduced by {reduction:.0%}"
                        )

        if warnings:
            logger.info(
                f"Correlation guard (dynamic) for {epic} {direction}: "
                f"multiplier={size_multiplier:.2f}, warnings={len(warnings)}"
            )

        return size_multiplier, warnings

    # ------------------------------------------------------------------
    # Static exposure check (backward-compatible class method)
    # ------------------------------------------------------------------

    @staticmethod
    def check_exposure(
        epic: str,
        direction: str,
        open_positions: list[dict],
    ) -> tuple[float, list[str]]:
        """
        Check if opening a new position would create excessive correlated exposure.

        Uses only the hardcoded ``CORRELATION_PAIRS``.  For dynamic matrix support
        use an instance and call ``check_exposure_dynamic`` instead.

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
