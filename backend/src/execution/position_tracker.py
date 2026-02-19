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
            positions = []
            for p in self._paper_positions.values():
                pos = dict(p)
                pos.setdefault("risk_managed_locally", True)
                self._apply_emergency_levels(pos)
                positions.append(pos)
            return positions

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
                positions = []
                for p in self._paper_positions.values():
                    pos = dict(p)
                    # Paper mode: all risk is managed locally
                    pos.setdefault("risk_managed_locally", True)
                    self._apply_emergency_levels(pos)
                    positions.append(pos)
                return positions

        # DEMO and LIVE: broker is the source of truth
        if self._broker is None:
            logger.warning(f"Broker not available in {self._mode.value} mode, using local positions")
            with self._lock:
                return list(self._paper_positions.values())

        positions = await self._broker.list_positions()
        result = []
        for p in positions:
            pos_dict = {
                "deal_id": p.deal_id,
                "epic": p.epic,
                "direction": p.direction.value,
                "size": p.size,
                "level": p.level,
                "stop_level": p.stop_level,
                "profit_level": p.profit_level,
                "opened_at": p.created_date.isoformat() if p.created_date else None,
            }

            # CRITICAL: Merge local SL/TP data if broker doesn't have them.
            # Capital.com returns DIFFERENT deal_ids for create vs list,
            # so we match by EPIC (one position per asset in our system).
            risk_local = False
            with self._lock:
                local = self._find_local_by_epic(p.epic)
            if local:
                if pos_dict["stop_level"] is None and local.get("stop_level"):
                    pos_dict["stop_level"] = local["stop_level"]
                    risk_local = True
                    logger.debug(
                        f"[{p.epic}] Merged local SL={local['stop_level']} "
                        f"(broker has no SL set)"
                    )
                if pos_dict["profit_level"] is None and local.get("profit_level"):
                    pos_dict["profit_level"] = local["profit_level"]
                    risk_local = True

            # Apply emergency SL/TP if still missing after merge
            had_sl = pos_dict["stop_level"] is not None
            had_tp = pos_dict["profit_level"] is not None
            self._apply_emergency_levels(pos_dict)
            if not had_sl and pos_dict["stop_level"] is not None:
                risk_local = True
            if not had_tp and pos_dict["profit_level"] is not None:
                risk_local = True

            # Flag: broker has no SL/TP, risk is managed locally
            pos_dict["risk_managed_locally"] = risk_local

            result.append(pos_dict)
        return result

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
        # Check local memory first (all modes)
        with self._lock:
            local = self._paper_positions.get(deal_id)
        if local:
            return local

        # PAPER mode: local memory is the only source
        if self._mode == ExecutionMode.PAPER:
            return None

        # DEMO/LIVE: query broker API as fallback
        positions = await self.sync_positions()
        for p in positions:
            if p.get("deal_id") == deal_id:
                return p
        return None

    def update_stops(
        self, deal_id: str, stop_level: float | None = None, profit_level: float | None = None
    ) -> None:
        """
        Update SL/TP on a local position (thread-safe).
        Used when broker rejects SL/TP and we need to store adjusted levels locally.
        """
        with self._lock:
            position = self._paper_positions.get(deal_id)
            if position is None:
                # Try matching by epic (Capital.com deal_id mismatch)
                for pos in self._paper_positions.values():
                    if pos.get("deal_id") == deal_id:
                        position = pos
                        break
            if position is None:
                return
            if stop_level is not None:
                position["stop_level"] = stop_level
            if profit_level is not None:
                position["profit_level"] = profit_level
            logger.debug(
                f"Local stops updated for {deal_id}: "
                f"SL={stop_level}, TP={profit_level}"
            )

    @staticmethod
    def _apply_emergency_levels(pos_dict: dict) -> None:
        """
        Compute emergency SL/TP for positions missing them.
        Emergency SL: 3% from entry. Emergency TP: R:R 2.0 from SL distance.
        Mutates pos_dict in place.
        """
        entry = pos_dict.get("level")
        direction = pos_dict.get("direction")
        if not entry or entry <= 0 or not direction:
            return

        # Emergency SL: 3% from entry
        if pos_dict.get("stop_level") is None:
            if direction == "BUY":
                pos_dict["stop_level"] = round(entry * 0.97, 6)
            else:
                pos_dict["stop_level"] = round(entry * 1.03, 6)
            logger.warning(
                f"[{pos_dict.get('epic')}] EMERGENCY SL at 3%: "
                f"SL={pos_dict['stop_level']}"
            )

        # Emergency TP: R:R 2.0 from SL distance
        if pos_dict.get("profit_level") is None and pos_dict.get("stop_level") is not None:
            sl_distance = abs(entry - pos_dict["stop_level"])
            rr_ratio = 2.0
            if direction == "BUY":
                pos_dict["profit_level"] = round(entry + sl_distance * rr_ratio, 6)
            else:
                pos_dict["profit_level"] = round(entry - sl_distance * rr_ratio, 6)
            logger.warning(
                f"[{pos_dict.get('epic')}] EMERGENCY TP at R:R {rr_ratio}: "
                f"TP={pos_dict['profit_level']}"
            )

    def _find_local_by_epic(self, epic: str) -> dict | None:
        """Find local position by epic (must be called within self._lock)."""
        for pos in self._paper_positions.values():
            if pos.get("epic") == epic:
                return pos
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
