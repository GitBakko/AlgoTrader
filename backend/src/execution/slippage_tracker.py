"""
Slippage tracking: records and analyzes expected vs actual execution prices.
"""

from dataclasses import dataclass, field


@dataclass
class SlippageRecord:
    """Single slippage measurement."""

    epic: str
    expected_price: float
    actual_price: float
    direction: str
    slippage: float  # absolute value


class SlippageTracker:
    """Tracks slippage across all executions."""

    MAX_RECORDS = 10000  # Prevent unbounded memory growth

    def __init__(self):
        self._records: list[SlippageRecord] = []

    def record_slippage(
        self,
        epic: str,
        expected_price: float,
        actual_price: float,
        direction: str,
    ) -> None:
        """
        Record a slippage measurement.

        Args:
            epic: Asset epic code
            expected_price: Expected fill price
            actual_price: Actual fill price
            direction: Trade direction ("BUY" or "SELL")
        """
        slippage = abs(actual_price - expected_price)
        self._records.append(
            SlippageRecord(
                epic=epic,
                expected_price=expected_price,
                actual_price=actual_price,
                direction=direction,
                slippage=slippage,
            )
        )
        # Trim oldest records if over limit
        if len(self._records) > self.MAX_RECORDS:
            self._records = self._records[-self.MAX_RECORDS:]

    def get_average_slippage(self, epic: str | None = None) -> float:
        """
        Get average slippage, optionally filtered by epic.

        Args:
            epic: Filter by asset (None = all assets)

        Returns:
            Average slippage (0.0 if no records)
        """
        records = self._records
        if epic is not None:
            records = [r for r in records if r.epic == epic]

        if not records:
            return 0.0
        return sum(r.slippage for r in records) / len(records)

    def get_stats(self) -> dict:
        """
        Get slippage statistics per epic.

        Returns:
            Dict with per-epic stats: avg, max, count
        """
        if not self._records:
            return {}

        stats: dict[str, dict] = {}
        for record in self._records:
            if record.epic not in stats:
                stats[record.epic] = {"total": 0.0, "max": 0.0, "count": 0}

            s = stats[record.epic]
            s["total"] += record.slippage
            s["max"] = max(s["max"], record.slippage)
            s["count"] += 1

        # Calculate averages
        result = {}
        for epic, s in stats.items():
            result[epic] = {
                "avg_slippage": s["total"] / s["count"],
                "max_slippage": s["max"],
                "count": s["count"],
            }

        return result

    def reset(self) -> None:
        """Clear all slippage records."""
        self._records.clear()
