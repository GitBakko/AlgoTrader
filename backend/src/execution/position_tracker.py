"""
Position tracking: syncs positions with broker and manages paper trading state.
"""

import threading
from datetime import datetime, timezone
from uuid import uuid4

from loguru import logger

from src.broker.client import CapitalComClient
from src.broker.models import Position as BrokerPosition
from src.execution.schemas import ExecutionMode, ExecutionOrder


class PositionTracker:
    """
    Tracks open positions.
    In PAPER mode, maintains in-memory state.
    In LIVE mode, syncs with broker.
    """

    def __init__(
        self,
        broker: CapitalComClient | None = None,
        mode: ExecutionMode = ExecutionMode.PAPER,
    ):
        self._broker = broker
        self._mode = mode

        # CRITICAL FIX (CRIT-7): Thread-safety lock for shared state
        self._lock = threading.Lock()

        # Paper trading internal state: deal_id -> position dict
        self._paper_positions: dict[str, dict] = {}

    def get_paper_positions_sync(self) -> list[dict]:
        """Get paper positions synchronously (for status queries in paper mode) - thread-safe."""
        with self._lock:
            return list(self._paper_positions.values())

    async def sync_positions(self) -> list[dict]:
        """
        Get all open positions (thread-safe).

        PAPER: Uses local in-memory tracking (no broker).
        DEMO/LIVE: Queries broker for authoritative state (Capital.com is source of truth).

        Returns:
            List of position dicts with keys: deal_id, epic, direction, size, level
        """
        # CRITICAL FIX: Only PAPER mode uses local tracking
        # DEMO and LIVE must call broker to detect manual closes!
        if self._mode == ExecutionMode.PAPER:
            with self._lock:
                return list(self._paper_positions.values())

        # DEMO and LIVE: broker is the source of truth
        if self._broker is None:
            logger.warning(f"Broker not available in {self._mode.value} mode, using local positions")
            with self._lock:
                return list(self._paper_positions.values())

        positions = await self._broker.list_positions()
        return [
            {
                "deal_id": p.deal_id,
                "epic": p.epic,
                "direction": p.direction.value,
                "size": p.size,
                "level": p.level,
                "stop_level": p.stop_level,
                "profit_level": p.profit_level,
            }
            for p in positions
        ]

    async def get_open_positions(self, epic: str | None = None) -> list[dict]:
        """
        Get open positions, optionally filtered by epic.

        Args:
            epic: Filter by asset (None = all)

        Returns:
            List of position dicts
        """
        positions = await self.sync_positions()
        if epic is not None:
            positions = [p for p in positions if p.get("epic") == epic]
        return positions

    async def get_position(self, deal_id: str) -> dict | None:
        """
        Get a specific position by deal ID (thread-safe).

        Args:
            deal_id: Deal ID

        Returns:
            Position dict or None
        """
        if self._mode in (ExecutionMode.PAPER, ExecutionMode.DEMO):
            with self._lock:
                return self._paper_positions.get(deal_id)

        positions = await self.sync_positions()
        for p in positions:
            if p.get("deal_id") == deal_id:
                return p
        return None

    def open_paper_position(
        self, order: ExecutionOrder, fill_price: float, deal_id: str
    ) -> dict:
        """
        Record a paper trading position opening (thread-safe).

        Args:
            order: The executed order
            fill_price: Actual fill price
            deal_id: Generated deal ID

        Returns:
            Position dict
        """
        with self._lock:
            # CRITICAL: Check for duplicates to prevent race condition
            if deal_id in self._paper_positions:
                raise ValueError(f"Position {deal_id} already exists!")

            position = {
                "deal_id": deal_id,
                "epic": order.epic,
                "direction": order.direction,
                "size": order.size,
                "level": fill_price,
                "stop_level": order.stop_loss,
                "profit_level": order.take_profit,
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }
            self._paper_positions[deal_id] = position
            logger.debug(f"Paper position opened: {deal_id} {order.epic} {order.direction}")
            return position

    def close_paper_position(self, deal_id: str) -> dict | None:
        """
        Remove a paper trading position (thread-safe).

        Args:
            deal_id: Deal ID to close

        Returns:
            Closed position dict or None if not found
        """
        with self._lock:
            position = self._paper_positions.pop(deal_id, None)
            if position:
                logger.debug(f"Paper position closed: {deal_id}")
            return position

    def reduce_paper_position(self, deal_id: str, reduce_pct: float) -> dict | None:
        """
        Reduce a paper position's size (for partial closes) - thread-safe.

        Args:
            deal_id: Deal ID to reduce
            reduce_pct: Percentage to close (0.0 to 1.0)

        Returns:
            Updated position dict or None if not found
        """
        with self._lock:
            position = self._paper_positions.get(deal_id)
            if position is None:
                return None

            if reduce_pct >= 1.0:
                # Full close - remove from dict
                position = self._paper_positions.pop(deal_id, None)
                if position:
                    logger.debug(f"Paper position closed (100% reduction): {deal_id}")
                return position

            old_size = position["size"]
            position["size"] = old_size * (1.0 - reduce_pct)
            logger.debug(
                f"Paper position reduced: {deal_id} "
                f"{old_size:.4f} -> {position['size']:.4f} (-{reduce_pct:.0%})"
            )
            return position

    def inject_paper_position(
        self,
        deal_id: str,
        epic: str,
        direction: str,
        size: float,
        entry_price: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> dict:
        """
        Inject a position into paper trading state (for state recovery) - thread-safe.

        Args:
            deal_id: Position deal identifier
            epic: Asset symbol
            direction: BUY or SELL
            size: Position size
            entry_price: Entry price
            stop_loss: Stop loss level
            take_profit: Take profit level

        Returns:
            Injected position dict
        """
        with self._lock:
            position = {
                "deal_id": deal_id,
                "epic": epic,
                "direction": direction,
                "size": size,
                "level": entry_price,
                "stop_level": stop_loss,
                "profit_level": take_profit,
                "opened_at": datetime.now(timezone.utc).isoformat(),
            }
            self._paper_positions[deal_id] = position
            logger.debug(f"Position injected for recovery: {deal_id} {epic} {direction}")
            return position

    @property
    def paper_position_count(self) -> int:
        """Number of open paper positions (thread-safe)."""
        with self._lock:
            return len(self._paper_positions)
