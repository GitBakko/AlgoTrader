"""
Step trailing stop manager with 4 phases.
Manages stop-loss progression from initial -> breakeven -> TP1 lock -> trailing.
"""

from enum import IntEnum

from loguru import logger
from pydantic import BaseModel, Field


class TrailingPhase(IntEnum):
    """Stop-loss management phases."""

    INITIAL = 0  # SL at initial level
    BREAKEVEN = 1  # SL moved to entry (price reached TP1)
    TP1_LOCK = 2  # SL moved to TP1 (price reached TP2)
    TRAILING = 3  # Trailing ATR from highest/lowest (after TP2)


class TrailingStopConfig(BaseModel):
    """Configuration for step trailing stop."""

    tp1_risk_multiple: float = Field(default=0.5, ge=0.1, le=5.0)
    tp2_risk_multiple: float = Field(default=1.5, ge=0.5, le=10.0)
    trailing_atr_multiplier: float = Field(default=1.5, ge=0.5, le=5.0)
    # 0.0 = pure breakeven (SL exactly at entry, maximum buffer between
    # current price and SL). Non-zero values lock a small profit at the
    # cost of a tighter buffer — fine on calm assets, but on noisy or
    # tight-stop instruments (NVDA mean-reversion at TP1 distance ~0.5
    # USD) a 0.1% offset chops the post-TP1 buffer in half and triggers
    # SL on a single tick of retracement. Default flipped from 0.001 to
    # 0.0 (2026-04-29) per live observation: BREAKEVEN was firing then
    # closing for $0.02 because the buffer was sub-spread. Set non-zero
    # via env BREAKEVEN_OFFSET_PCT only if you have a specific reason.
    breakeven_offset_pct: float = Field(default=0.0, ge=0.0, le=0.01)


class PositionStopState(BaseModel):
    """Tracks stop state for a single position."""

    deal_id: str
    epic: str
    direction: str  # "BUY" or "SELL"
    entry_price: float
    initial_stop: float
    current_stop: float
    tp1_level: float
    tp2_level: float
    risk_distance: float
    phase: int = TrailingPhase.INITIAL
    highest_price: float = 0.0
    lowest_price: float = float("inf")


class TrailingStopManager:
    """
    Manages step trailing stops for open positions.

    Phase transitions:
    INITIAL -> BREAKEVEN: when price reaches TP1 (SL moves to entry + offset)
    BREAKEVEN -> TP1_LOCK: when price reaches TP2 (SL moves to TP1)
    TP1_LOCK -> TRAILING: beyond TP2, ratchet stop with ATR
    """

    def __init__(self, config: TrailingStopConfig | None = None):
        self.config = config or TrailingStopConfig()
        self._positions: dict[str, PositionStopState] = {}

    def register_position(
        self,
        deal_id: str,
        epic: str,
        direction: str,
        entry_price: float,
        stop_loss: float,
        atr: float,
        take_profit: float | None = None,
    ) -> PositionStopState:
        """
        Register a new position for trailing stop management.

        Args:
            deal_id: Position deal ID
            epic: Asset epic
            direction: "BUY" or "SELL"
            entry_price: Entry price
            stop_loss: Initial stop-loss level
            atr: Current ATR value
            take_profit: Strategy-calibrated take-profit level. When supplied,
                the trailing manager anchors its phase ladder to the strategy's
                actual TP rather than a generic risk_multiple — TP1 fires at the
                midpoint between entry and TP (50% progress to target), TP2
                fires at the strategy TP itself. This matters when the strategy
                R:R is below 2× the trailing manager's risk_multiple defaults
                (e.g., MR strategies running at 0.25R targets), where the
                broker would close on TP before the trailing ladder ever
                advanced. When None, falls back to the legacy
                risk_multiple-based ladder.

        Returns:
            PositionStopState for the registered position
        """
        risk_distance = abs(entry_price - stop_loss)

        tp1, tp2 = self._derive_tp_levels(
            direction, entry_price, risk_distance, take_profit
        )

        state = PositionStopState(
            deal_id=deal_id,
            epic=epic,
            direction=direction,
            entry_price=entry_price,
            initial_stop=stop_loss,
            current_stop=stop_loss,
            tp1_level=tp1,
            tp2_level=tp2,
            risk_distance=risk_distance,
            phase=TrailingPhase.INITIAL,
            highest_price=entry_price,
            lowest_price=entry_price,
        )

        self._positions[deal_id] = state
        logger.debug(
            f"[{epic}] Trailing stop registered: {direction} entry={entry_price:.2f} "
            f"SL={stop_loss:.2f} TP1={tp1:.2f} TP2={tp2:.2f}"
        )
        return state

    def update_price(
        self,
        deal_id: str,
        current_price: float,
        current_atr: float | None = None,
    ) -> tuple[float | None, TrailingPhase]:
        """
        Update price and potentially advance the trailing stop phase.

        Args:
            deal_id: Position deal ID
            current_price: Current market price
            current_atr: Current ATR (used for trailing phase)

        Returns:
            Tuple of (new_stop_level or None if unchanged, current_phase)
        """
        state = self._positions.get(deal_id)
        if state is None:
            return None, TrailingPhase.INITIAL

        # Update extremes
        if state.direction == "BUY":
            state.highest_price = max(state.highest_price, current_price)
        else:
            state.lowest_price = min(state.lowest_price, current_price)

        old_stop = state.current_stop
        old_phase = state.phase

        # Check phase transitions
        if state.direction == "BUY":
            new_stop = self._update_buy(state, current_price, current_atr)
        else:
            new_stop = self._update_sell(state, current_price, current_atr)

        if new_stop is not None and new_stop != old_stop:
            state.current_stop = new_stop
            if state.phase != old_phase:
                logger.info(
                    f"[{state.epic}] Trailing phase: {TrailingPhase(old_phase).name} -> "
                    f"{TrailingPhase(state.phase).name}, SL={new_stop:.2f}"
                )
            return new_stop, TrailingPhase(state.phase)

        return None, TrailingPhase(state.phase)

    def unregister_position(self, deal_id: str) -> None:
        """Remove a position from trailing stop management."""
        self._positions.pop(deal_id, None)

    def get_state(self, deal_id: str) -> PositionStopState | None:
        """Get current stop state for a position."""
        return self._positions.get(deal_id)

    def _derive_tp_levels(
        self,
        direction: str,
        entry_price: float,
        risk_distance: float,
        take_profit: float | None,
    ) -> tuple[float, float]:
        """Compute (tp1, tp2) for the trailing phase ladder.

        When ``take_profit`` is provided, anchor the ladder to the strategy's
        actual TP: TP1 = midpoint(entry, TP) (= 50% progress to target),
        TP2 = TP. When ``take_profit`` is None, fall back to the legacy
        risk_multiple ladder (TP1 = risk_multiple × risk_distance from entry).
        """
        if take_profit is not None and take_profit > 0:
            tp2 = float(take_profit)
            tp1 = entry_price + (tp2 - entry_price) * 0.5
            return tp1, tp2

        if direction == "BUY":
            tp1 = entry_price + risk_distance * self.config.tp1_risk_multiple
            tp2 = entry_price + risk_distance * self.config.tp2_risk_multiple
        else:
            tp1 = entry_price - risk_distance * self.config.tp1_risk_multiple
            tp2 = entry_price - risk_distance * self.config.tp2_risk_multiple
        return tp1, tp2

    def restore_state(
        self,
        deal_id: str,
        epic: str,
        direction: str,
        entry_price: float,
        current_stop: float,
        phase: int,
        tp1_level: float | None = None,
        tp2_level: float | None = None,
        highest_price: float | None = None,
        lowest_price: float | None = None,
        take_profit: float | None = None,
    ) -> PositionStopState:
        """
        Restore a trailing stop state from persisted data (for recovery).

        Args:
            deal_id: Position deal identifier
            epic: Asset symbol
            direction: BUY or SELL
            entry_price: Entry price
            current_stop: Current stop-loss level
            phase: Current trailing phase (0-3)
            tp1_level: First take profit level (from DB)
            tp2_level: Second take profit level (from DB)
            highest_price: Highest price reached (for longs)
            lowest_price: Lowest price reached (for shorts)
            take_profit: When provided, the strategy's current TP overrides any
                persisted tp1/tp2 levels — re-derives the ladder anchored to
                the strategy's actual TP. Use this on startup to migrate
                positions whose persisted tp1/tp2 were computed with the legacy
                risk_multiple ladder before the strategy-anchored fix.

        Returns:
            Restored PositionStopState
        """
        risk_distance = abs(entry_price - current_stop)

        # Strategy-anchored TP overrides any persisted ladder.
        if take_profit is not None and take_profit > 0:
            tp1_level, tp2_level = self._derive_tp_levels(
                direction, entry_price, risk_distance, take_profit
            )
        else:
            if tp1_level is None:
                if direction == "BUY":
                    tp1_level = entry_price + risk_distance * self.config.tp1_risk_multiple
                else:
                    tp1_level = entry_price - risk_distance * self.config.tp1_risk_multiple

            if tp2_level is None:
                if direction == "BUY":
                    tp2_level = entry_price + risk_distance * self.config.tp2_risk_multiple
                else:
                    tp2_level = entry_price - risk_distance * self.config.tp2_risk_multiple

        state = PositionStopState(
            deal_id=deal_id,
            epic=epic,
            direction=direction,
            entry_price=entry_price,
            initial_stop=current_stop,  # Assume initial = current for recovery
            current_stop=current_stop,
            tp1_level=tp1_level,
            tp2_level=tp2_level,
            risk_distance=risk_distance,
            phase=phase,
            highest_price=highest_price or entry_price,
            lowest_price=lowest_price or entry_price,
        )

        self._positions[deal_id] = state
        logger.debug(
            f"[{epic}] Trailing stop state restored: {direction} phase={phase} "
            f"entry={entry_price:.2f} SL={current_stop:.2f}"
        )
        return state

    @property
    def tracked_positions(self) -> list[str]:
        """List of tracked deal IDs."""
        return list(self._positions.keys())

    def _update_buy(
        self,
        state: PositionStopState,
        price: float,
        atr: float | None,
    ) -> float | None:
        """
        Update stop for a BUY position.

        CRITICAL FIX (CRIT-5): Handle gap scenarios where price jumps past multiple TP levels.
        """
        if state.phase == TrailingPhase.INITIAL:
            # CRITICAL FIX: Check TP2 first to handle gap scenarios
            if price >= state.tp2_level:
                # Price gapped through both TP1 and TP2 → Skip directly to TP1_LOCK
                logger.warning(
                    f"[{state.epic}] Gap detected: price {price:.2f} >= TP2 {state.tp2_level:.2f}, "
                    f"skipping BREAKEVEN phase, locking at TP1 {state.tp1_level:.2f}"
                )
                state.phase = TrailingPhase.TP1_LOCK
                return state.tp1_level
            elif price >= state.tp1_level:
                # Normal TP1 hit → Move to breakeven
                offset = state.entry_price * self.config.breakeven_offset_pct
                new_stop = state.entry_price + offset
                state.phase = TrailingPhase.BREAKEVEN
                return new_stop

        elif state.phase == TrailingPhase.BREAKEVEN:
            if price >= state.tp2_level:
                # Lock at TP1
                state.phase = TrailingPhase.TP1_LOCK
                return state.tp1_level

        elif state.phase == TrailingPhase.TP1_LOCK:
            if atr and atr > 0:
                # Start trailing
                trail_stop = state.highest_price - atr * self.config.trailing_atr_multiplier
                if trail_stop > state.current_stop:
                    state.phase = TrailingPhase.TRAILING
                    return trail_stop

        elif state.phase == TrailingPhase.TRAILING:
            if atr and atr > 0:
                # Ratchet trailing stop (only moves up)
                trail_stop = state.highest_price - atr * self.config.trailing_atr_multiplier
                if trail_stop > state.current_stop:
                    return trail_stop

        return None

    def _update_sell(
        self,
        state: PositionStopState,
        price: float,
        atr: float | None,
    ) -> float | None:
        """
        Update stop for a SELL position.

        CRITICAL FIX (CRIT-5): Handle gap scenarios where price jumps past multiple TP levels.
        """
        if state.phase == TrailingPhase.INITIAL:
            # CRITICAL FIX: Check TP2 first to handle gap scenarios
            if price <= state.tp2_level:
                # Price gapped through both TP1 and TP2 → Skip directly to TP1_LOCK
                logger.warning(
                    f"[{state.epic}] Gap detected: price {price:.2f} <= TP2 {state.tp2_level:.2f}, "
                    f"skipping BREAKEVEN phase, locking at TP1 {state.tp1_level:.2f}"
                )
                state.phase = TrailingPhase.TP1_LOCK
                return state.tp1_level
            elif price <= state.tp1_level:
                # Normal TP1 hit → Move to breakeven
                offset = state.entry_price * self.config.breakeven_offset_pct
                new_stop = state.entry_price - offset
                state.phase = TrailingPhase.BREAKEVEN
                return new_stop

        elif state.phase == TrailingPhase.BREAKEVEN:
            if price <= state.tp2_level:
                state.phase = TrailingPhase.TP1_LOCK
                return state.tp1_level

        elif state.phase == TrailingPhase.TP1_LOCK:
            if atr and atr > 0:
                trail_stop = state.lowest_price + atr * self.config.trailing_atr_multiplier
                if trail_stop < state.current_stop:
                    state.phase = TrailingPhase.TRAILING
                    return trail_stop

        elif state.phase == TrailingPhase.TRAILING:
            if atr and atr > 0:
                trail_stop = state.lowest_price + atr * self.config.trailing_atr_multiplier
                if trail_stop < state.current_stop:
                    return trail_stop

        return None
