"""
Rolling per-asset performance tracker.

Tracks P&L per trade for each asset over a configurable lookback window.
Assets with a Sharpe ratio below the threshold are excluded from trading.
"""

from collections import deque
from datetime import UTC, datetime, timedelta

import numpy as np
from loguru import logger


class AssetPerformanceTracker:
    """
    Tracks per-asset trade outcomes and computes rolling Sharpe ratios.

    Assets with Sharpe < threshold over the lookback period are excluded
    from signal generation to avoid consistently losing instruments.
    """

    def __init__(
        self,
        lookback_days: int = 14,
        min_trades: int = 5,
        sharpe_threshold: float = -0.5,
    ):
        self.lookback_days = lookback_days
        self.min_trades = min_trades
        self.sharpe_threshold = sharpe_threshold
        # Per-asset deque of (timestamp, pnl) tuples
        self._trades: dict[str, deque[tuple[datetime, float]]] = {}

    def record_trade(self, epic: str, pnl: float, timestamp: datetime | None = None) -> None:
        """Record a closed trade's P&L for the given asset."""
        ts = timestamp or datetime.now(UTC)
        if epic not in self._trades:
            self._trades[epic] = deque(maxlen=500)
        self._trades[epic].append((ts, pnl))

    def is_excluded(self, epic: str) -> tuple[bool, float]:
        """
        Check if an asset should be excluded from trading.

        Returns:
            (is_excluded, sharpe_ratio) — excluded if Sharpe < threshold
            and at least min_trades trades in the lookback window.
        """
        if epic not in self._trades:
            return False, 0.0

        cutoff = datetime.now(UTC) - timedelta(days=self.lookback_days)
        pnls = [pnl for ts, pnl in self._trades[epic] if ts >= cutoff]

        if len(pnls) < self.min_trades:
            return False, 0.0

        arr = np.array(pnls, dtype=np.float64)
        std = arr.std()
        if std == 0:
            # All same P&L — not enough variance to compute Sharpe
            return False, 0.0

        sharpe = float(arr.mean() / std * np.sqrt(252))
        excluded = sharpe < self.sharpe_threshold

        if excluded:
            logger.info(
                f"[{epic}] Asset excluded: {self.lookback_days}-day Sharpe = "
                f"{sharpe:.2f} < {self.sharpe_threshold} ({len(pnls)} trades)"
            )

        return excluded, sharpe

    def get_all_sharpes(self) -> dict[str, float]:
        """Get rolling Sharpe ratios for all tracked assets."""
        result = {}
        cutoff = datetime.now(UTC) - timedelta(days=self.lookback_days)
        for epic, trades in self._trades.items():
            pnls = [pnl for ts, pnl in trades if ts >= cutoff]
            if len(pnls) < self.min_trades:
                continue
            arr = np.array(pnls, dtype=np.float64)
            std = arr.std()
            if std == 0:
                continue
            result[epic] = float(arr.mean() / std * np.sqrt(252))
        return result

    def reset(self) -> None:
        """Clear all tracked trade history."""
        self._trades.clear()
        logger.info("Asset performance tracker reset")
