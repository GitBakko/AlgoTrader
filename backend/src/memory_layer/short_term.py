# MANTIS-EVOLUTION: Short Term Memory
"""Short-term memory with exponential decay — stores recent signals and trades."""

from __future__ import annotations

import math
import pickle
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from src.memory_layer.schemas import MemoryConfig, MemoryItem, TradeOutcome


class MantisShortTermMemory:
    """
    Short-term memory: recent signals and trades with exponential decay.

    Items decay with weight = e^(-λ * age_hours).
    Default λ = 0.1 → half-life ≈ 7 hours.

    Persistence: pickle snapshot to disk (optional).
    Redis support deferred to a later task.
    """

    def __init__(self, config: MemoryConfig | None = None):
        self.config = config or MemoryConfig()
        self._signals: deque[MemoryItem] = deque(maxlen=self.config.stm_max_signals)
        self._trades: deque[MemoryItem] = deque(maxlen=self.config.stm_max_trades)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def signal_count(self) -> int:
        return len(self._signals)

    @property
    def trade_count(self) -> int:
        return len(self._trades)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def add_signal(
        self,
        epic: str,
        direction: str,
        confidence: float,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add a signal to STM. Returns the generated item ID."""
        item_id = str(uuid.uuid4())[:8]
        item = MemoryItem(
            id=item_id,
            epic=epic,
            category="signal",
            data={
                "direction": direction,
                "confidence": confidence,
                **(metadata or {}),
            },
            weight=1.0,
        )
        self._signals.append(item)
        return item_id

    def add_trade_outcome(self, outcome: TradeOutcome) -> str:
        """Add a completed trade outcome to STM."""
        item_id = str(uuid.uuid4())[:8]
        item = MemoryItem(
            id=item_id,
            epic=outcome.epic,
            category="trade",
            data=outcome.model_dump(),
            weight=1.0,
        )
        self._trades.append(item)
        return item_id

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_recent_signals(self, n: int = 10) -> list[MemoryItem]:
        """Get N most recent signals, sorted by decay-adjusted weight (highest first)."""
        self._apply_decay()
        items = sorted(self._signals, key=lambda x: x.weight, reverse=True)
        return items[:n]

    def get_recent_trades(self, n: int = 10) -> list[MemoryItem]:
        """Get N most recent trades, sorted by decay-adjusted weight (highest first)."""
        self._apply_decay()
        items = sorted(self._trades, key=lambda x: x.weight, reverse=True)
        return items[:n]

    def get_recent_context(self, n: int = 10) -> list[MemoryItem]:
        """Get N most recent items from both signals and trades, sorted by decay weight."""
        self._apply_decay()
        all_items = list(self._signals) + list(self._trades)
        all_items.sort(key=lambda x: x.weight, reverse=True)
        return all_items[:n]

    def get_win_rate_recent(self, window_hours: float = 24) -> float:
        """
        Win rate for trades that completed within the last ``window_hours``.

        Returns 0.5 (neutral) when there are no trades in the window.
        """
        now = datetime.now(timezone.utc)
        wins = 0
        total = 0
        for item in self._trades:
            age_hours = (now - item.timestamp).total_seconds() / 3600
            if age_hours <= window_hours:
                total += 1
                if item.data.get("pnl_pct", 0) > 0:
                    wins += 1
        return wins / total if total > 0 else 0.5

    # ------------------------------------------------------------------
    # Decay
    # ------------------------------------------------------------------

    def _apply_decay(self) -> None:
        """Apply exponential decay to all items based on their age."""
        now = datetime.now(timezone.utc)
        lam = self.config.decay_lambda
        for item in self._signals:
            age_hours = (now - item.timestamp).total_seconds() / 3600
            item.weight = math.exp(-lam * age_hours)
        for item in self._trades:
            age_hours = (now - item.timestamp).total_seconds() / 3600
            item.weight = math.exp(-lam * age_hours)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Clear all STM data."""
        self._signals.clear()
        self._trades.clear()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save_snapshot(self, path: str | Path | None = None) -> bool:
        """
        Save STM state to a pickle file.

        Returns True on success, False on failure (never raises).
        """
        save_path = Path(path) if path else Path("data/memory/stm_snapshot.pkl")
        try:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "signals": list(self._signals),
                "trades": list(self._trades),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            with open(save_path, "wb") as f:
                pickle.dump(data, f)
            logger.debug(f"STM snapshot saved to {save_path}")
            return True
        except Exception as exc:
            logger.warning(f"STM snapshot save failed: {exc!r}")
            return False

    def load_snapshot(self, path: str | Path | None = None) -> bool:
        """
        Load STM state from a pickle file.

        Returns True on success, False when file is missing or on error.
        """
        load_path = Path(path) if path else Path("data/memory/stm_snapshot.pkl")
        try:
            if not load_path.exists():
                return False
            with open(load_path, "rb") as f:
                data = pickle.load(f)
            self._signals = deque(data.get("signals", []), maxlen=self.config.stm_max_signals)
            self._trades = deque(data.get("trades", []), maxlen=self.config.stm_max_trades)
            logger.debug(
                f"STM snapshot loaded from {load_path}: "
                f"{len(self._signals)} signals, {len(self._trades)} trades"
            )
            return True
        except Exception as exc:
            logger.warning(f"STM snapshot load failed: {exc!r}")
            return False
