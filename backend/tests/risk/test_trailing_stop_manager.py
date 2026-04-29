"""
Comprehensive tests for TrailingStopManager.

Tests cover all phase transitions (INITIAL -> BREAKEVEN -> TP1_LOCK -> TRAILING)
for both BUY and SELL positions, with concrete numeric examples.
"""

import pytest

from src.risk.trailing_stop_manager import (
    PositionStopState,
    TrailingPhase,
    TrailingStopConfig,
    TrailingStopManager,
)


@pytest.fixture
def default_config():
    """Default trailing stop configuration."""
    return TrailingStopConfig(
        tp1_risk_multiple=1.0,
        tp2_risk_multiple=2.0,
        trailing_atr_multiplier=1.5,
        breakeven_offset_pct=0.001,
    )


@pytest.fixture
def manager(default_config):
    """TrailingStopManager instance with default config."""
    return TrailingStopManager(config=default_config)


# =============================================================================
# REGISTRATION TESTS
# =============================================================================


@pytest.mark.unit
@pytest.mark.risk
def test_register_position_buy_initial_state(manager):
    """Test register_position() for BUY - verify TP1/TP2 levels and initial state."""
    # Arrange
    deal_id = "DEAL001"
    epic = "XAUUSD"
    direction = "BUY"
    entry_price = 2000.0
    stop_loss = 1980.0
    atr = 10.0

    # Act
    state = manager.register_position(
        deal_id=deal_id,
        epic=epic,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        atr=atr,
    )

    # Assert
    assert state.deal_id == deal_id
    assert state.epic == epic
    assert state.direction == direction
    assert state.entry_price == pytest.approx(2000.0)
    assert state.initial_stop == pytest.approx(1980.0)
    assert state.current_stop == pytest.approx(1980.0)
    assert state.risk_distance == pytest.approx(20.0)
    # TP1 = entry + risk * 1.0 = 2000 + 20 = 2020
    assert state.tp1_level == pytest.approx(2020.0)
    # TP2 = entry + risk * 2.0 = 2000 + 40 = 2040
    assert state.tp2_level == pytest.approx(2040.0)
    assert state.phase == TrailingPhase.INITIAL
    assert state.highest_price == pytest.approx(2000.0)
    assert state.lowest_price == pytest.approx(2000.0)

    # Verify manager tracking
    assert deal_id in manager.tracked_positions
    assert manager.get_state(deal_id) == state


@pytest.mark.unit
@pytest.mark.risk
def test_register_position_sell_initial_state(manager):
    """Test register_position() for SELL - verify TP1/TP2 levels."""
    # Arrange
    deal_id = "DEAL002"
    epic = "BTCUSD"
    direction = "SELL"
    entry_price = 50000.0
    stop_loss = 50200.0
    atr = 500.0

    # Act
    state = manager.register_position(
        deal_id=deal_id,
        epic=epic,
        direction=direction,
        entry_price=entry_price,
        stop_loss=stop_loss,
        atr=atr,
    )

    # Assert
    assert state.deal_id == deal_id
    assert state.direction == direction
    assert state.entry_price == pytest.approx(50000.0)
    assert state.initial_stop == pytest.approx(50200.0)
    assert state.current_stop == pytest.approx(50200.0)
    assert state.risk_distance == pytest.approx(200.0)
    # TP1 = entry - risk * 1.0 = 50000 - 200 = 49800
    assert state.tp1_level == pytest.approx(49800.0)
    # TP2 = entry - risk * 2.0 = 50000 - 400 = 49600
    assert state.tp2_level == pytest.approx(49600.0)
    assert state.phase == TrailingPhase.INITIAL
    assert state.highest_price == pytest.approx(50000.0)
    assert state.lowest_price == pytest.approx(50000.0)


# =============================================================================
# BUY POSITION TESTS
# =============================================================================


@pytest.mark.unit
@pytest.mark.risk
def test_buy_initial_phase_price_below_tp1(manager):
    """BUY INITIAL phase - price below TP1, no stop change."""
    # Arrange
    manager.register_position(
        deal_id="BUY001",
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,
        atr=10.0,
    )

    # Act - price moves up but doesn't reach TP1 (2020)
    new_stop, phase = manager.update_price("BUY001", current_price=2010.0)

    # Assert
    assert new_stop is None  # No stop change
    assert phase == TrailingPhase.INITIAL
    state = manager.get_state("BUY001")
    assert state.current_stop == pytest.approx(1980.0)
    assert state.highest_price == pytest.approx(2010.0)


@pytest.mark.unit
@pytest.mark.risk
def test_buy_initial_to_breakeven_transition(manager):
    """BUY INITIAL → BREAKEVEN - price reaches TP1."""
    # Arrange
    manager.register_position(
        deal_id="BUY002",
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,
        atr=10.0,
    )

    # Act - price reaches TP1 = 2020
    new_stop, phase = manager.update_price("BUY002", current_price=2020.0)

    # Assert
    assert new_stop is not None
    # Breakeven offset = 2000 * 0.001 = 2.0, so new_stop = 2000 + 2 = 2002
    assert new_stop == pytest.approx(2002.0)
    assert phase == TrailingPhase.BREAKEVEN

    state = manager.get_state("BUY002")
    assert state.current_stop == pytest.approx(2002.0)
    assert state.phase == TrailingPhase.BREAKEVEN
    assert state.highest_price == pytest.approx(2020.0)


@pytest.mark.unit
@pytest.mark.risk
def test_buy_breakeven_to_tp1_lock_transition(manager):
    """BUY BREAKEVEN → TP1_LOCK - price reaches TP2."""
    # Arrange
    manager.register_position(
        deal_id="BUY003",
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,
        atr=10.0,
    )
    # Move to BREAKEVEN first
    manager.update_price("BUY003", current_price=2020.0)

    # Act - price reaches TP2 = 2040
    new_stop, phase = manager.update_price("BUY003", current_price=2040.0)

    # Assert
    assert new_stop is not None
    # Stop moves to TP1 level = 2020
    assert new_stop == pytest.approx(2020.0)
    assert phase == TrailingPhase.TP1_LOCK

    state = manager.get_state("BUY003")
    assert state.current_stop == pytest.approx(2020.0)
    assert state.phase == TrailingPhase.TP1_LOCK
    assert state.highest_price == pytest.approx(2040.0)


@pytest.mark.unit
@pytest.mark.risk
def test_buy_tp1_lock_to_trailing_transition(manager):
    """BUY TP1_LOCK → TRAILING - trailing with ATR."""
    # Arrange
    manager.register_position(
        deal_id="BUY004",
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,
        atr=10.0,
    )
    # Move to BREAKEVEN
    manager.update_price("BUY004", current_price=2020.0)
    # Move to TP1_LOCK
    manager.update_price("BUY004", current_price=2040.0)

    # Act - price moves higher, trailing stop kicks in
    # highest_price = 2050, ATR = 12, trail_stop = 2050 - 12*1.5 = 2050 - 18 = 2032
    new_stop, phase = manager.update_price(
        "BUY004", current_price=2050.0, current_atr=12.0
    )

    # Assert
    assert new_stop is not None
    assert new_stop == pytest.approx(2032.0)
    assert phase == TrailingPhase.TRAILING

    state = manager.get_state("BUY004")
    assert state.current_stop == pytest.approx(2032.0)
    assert state.phase == TrailingPhase.TRAILING
    assert state.highest_price == pytest.approx(2050.0)


@pytest.mark.unit
@pytest.mark.risk
def test_buy_trailing_ratchet_upward(manager):
    """BUY TRAILING - stop ratchets only upward."""
    # Arrange
    manager.register_position(
        deal_id="BUY005",
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,
        atr=10.0,
    )
    # Move through phases to TRAILING
    manager.update_price("BUY005", current_price=2020.0)
    manager.update_price("BUY005", current_price=2040.0)
    manager.update_price("BUY005", current_price=2050.0, current_atr=12.0)

    # Current stop = 2032, highest = 2050
    # Act - price climbs to 2060
    # trail_stop = 2060 - 12*1.5 = 2060 - 18 = 2042
    new_stop, phase = manager.update_price(
        "BUY005", current_price=2060.0, current_atr=12.0
    )

    # Assert
    assert new_stop is not None
    assert new_stop == pytest.approx(2042.0)
    assert phase == TrailingPhase.TRAILING

    state = manager.get_state("BUY005")
    assert state.current_stop == pytest.approx(2042.0)
    assert state.highest_price == pytest.approx(2060.0)


@pytest.mark.unit
@pytest.mark.risk
def test_buy_trailing_stop_does_not_decrease(manager):
    """BUY TRAILING - stop doesn't decrease when price pulls back."""
    # Arrange
    manager.register_position(
        deal_id="BUY006",
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,
        atr=10.0,
    )
    # Move to TRAILING with stop at 2042, highest = 2060
    manager.update_price("BUY006", current_price=2020.0)
    manager.update_price("BUY006", current_price=2040.0)
    manager.update_price("BUY006", current_price=2050.0, current_atr=12.0)
    manager.update_price("BUY006", current_price=2060.0, current_atr=12.0)

    # Act - price pulls back to 2045, trail_stop would be 2060 - 18 = 2042 (same)
    new_stop, phase = manager.update_price(
        "BUY006", current_price=2045.0, current_atr=12.0
    )

    # Assert - no change because highest_price hasn't increased
    assert new_stop is None
    assert phase == TrailingPhase.TRAILING

    state = manager.get_state("BUY006")
    assert state.current_stop == pytest.approx(2042.0)  # Unchanged
    assert state.highest_price == pytest.approx(2060.0)  # Still 2060


# =============================================================================
# SELL POSITION TESTS
# =============================================================================


@pytest.mark.unit
@pytest.mark.risk
def test_sell_initial_to_breakeven_transition(manager):
    """SELL INITIAL → BREAKEVEN - price reaches TP1."""
    # Arrange
    manager.register_position(
        deal_id="SELL001",
        epic="BTCUSD",
        direction="SELL",
        entry_price=50000.0,
        stop_loss=50200.0,
        atr=500.0,
    )

    # Act - price drops to TP1 = 49800
    new_stop, phase = manager.update_price("SELL001", current_price=49800.0)

    # Assert
    # Breakeven offset = 50000 * 0.001 = 50, so new_stop = 50000 - 50 = 49950
    assert new_stop is not None
    assert new_stop == pytest.approx(49950.0)
    assert phase == TrailingPhase.BREAKEVEN

    state = manager.get_state("SELL001")
    assert state.current_stop == pytest.approx(49950.0)
    assert state.phase == TrailingPhase.BREAKEVEN
    assert state.lowest_price == pytest.approx(49800.0)


@pytest.mark.unit
@pytest.mark.risk
def test_sell_breakeven_to_tp1_lock_transition(manager):
    """SELL BREAKEVEN → TP1_LOCK - price reaches TP2."""
    # Arrange
    manager.register_position(
        deal_id="SELL002",
        epic="BTCUSD",
        direction="SELL",
        entry_price=50000.0,
        stop_loss=50200.0,
        atr=500.0,
    )
    # Move to BREAKEVEN
    manager.update_price("SELL002", current_price=49800.0)

    # Act - price drops to TP2 = 49600
    new_stop, phase = manager.update_price("SELL002", current_price=49600.0)

    # Assert - stop moves to TP1 = 49800
    assert new_stop is not None
    assert new_stop == pytest.approx(49800.0)
    assert phase == TrailingPhase.TP1_LOCK

    state = manager.get_state("SELL002")
    assert state.current_stop == pytest.approx(49800.0)
    assert state.phase == TrailingPhase.TP1_LOCK
    assert state.lowest_price == pytest.approx(49600.0)


@pytest.mark.unit
@pytest.mark.risk
def test_sell_tp1_lock_to_trailing_transition(manager):
    """SELL TP1_LOCK → TRAILING - trailing with ATR."""
    # Arrange
    manager.register_position(
        deal_id="SELL003",
        epic="BTCUSD",
        direction="SELL",
        entry_price=50000.0,
        stop_loss=50200.0,
        atr=500.0,
    )
    # Move to TP1_LOCK
    manager.update_price("SELL003", current_price=49800.0)
    manager.update_price("SELL003", current_price=49600.0)

    # Act - price drops further, trailing kicks in
    # lowest_price = 49400, ATR = 600, trail_stop = 49400 + 600*1.5 = 49400 + 900 = 50300
    # Current stop is 49800, but trail_stop (50300) > current_stop, so no change yet
    # Let's use smaller ATR: 200, trail_stop = 49400 + 200*1.5 = 49400 + 300 = 49700
    new_stop, phase = manager.update_price(
        "SELL003", current_price=49400.0, current_atr=200.0
    )

    # Assert
    assert new_stop is not None
    assert new_stop == pytest.approx(49700.0)
    assert phase == TrailingPhase.TRAILING

    state = manager.get_state("SELL003")
    assert state.current_stop == pytest.approx(49700.0)
    assert state.phase == TrailingPhase.TRAILING
    assert state.lowest_price == pytest.approx(49400.0)


@pytest.mark.unit
@pytest.mark.risk
def test_sell_trailing_ratchet_downward(manager):
    """SELL TRAILING - stop ratchets only downward."""
    # Arrange
    manager.register_position(
        deal_id="SELL004",
        epic="BTCUSD",
        direction="SELL",
        entry_price=50000.0,
        stop_loss=50200.0,
        atr=500.0,
    )
    # Move to TRAILING with stop at 49700, lowest = 49400
    manager.update_price("SELL004", current_price=49800.0)
    manager.update_price("SELL004", current_price=49600.0)
    manager.update_price("SELL004", current_price=49400.0, current_atr=200.0)

    # Act - price drops to 49200
    # trail_stop = 49200 + 200*1.5 = 49200 + 300 = 49500
    new_stop, phase = manager.update_price(
        "SELL004", current_price=49200.0, current_atr=200.0
    )

    # Assert
    assert new_stop is not None
    assert new_stop == pytest.approx(49500.0)
    assert phase == TrailingPhase.TRAILING

    state = manager.get_state("SELL004")
    assert state.current_stop == pytest.approx(49500.0)
    assert state.lowest_price == pytest.approx(49200.0)


# =============================================================================
# MANAGER LIFECYCLE TESTS
# =============================================================================


@pytest.mark.unit
@pytest.mark.risk
def test_unregister_position_and_get_state(manager):
    """Test unregister_position() and get_state() for non-existent position."""
    # Arrange
    manager.register_position(
        deal_id="DEAL999",
        epic="US500",
        direction="BUY",
        entry_price=4500.0,
        stop_loss=4480.0,
        atr=15.0,
    )

    # Act - verify position exists
    assert "DEAL999" in manager.tracked_positions
    assert manager.get_state("DEAL999") is not None

    # Unregister
    manager.unregister_position("DEAL999")

    # Assert
    assert "DEAL999" not in manager.tracked_positions
    assert manager.get_state("DEAL999") is None


@pytest.mark.unit
@pytest.mark.risk
def test_update_price_for_unknown_deal_id(manager):
    """Test update_price() for a deal_id that doesn't exist."""
    # Act
    new_stop, phase = manager.update_price("UNKNOWN_DEAL", current_price=2000.0)

    # Assert
    assert new_stop is None
    assert phase == TrailingPhase.INITIAL


@pytest.mark.unit
@pytest.mark.risk
def test_full_lifecycle_buy_initial_to_trailing(manager):
    """Full lifecycle BUY: INITIAL → BREAKEVEN → TP1_LOCK → TRAILING."""
    # Arrange
    deal_id = "LIFECYCLE_BUY"
    manager.register_position(
        deal_id=deal_id,
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,
        atr=10.0,
    )

    # Phase 0: INITIAL
    state = manager.get_state(deal_id)
    assert state.phase == TrailingPhase.INITIAL
    assert state.current_stop == pytest.approx(1980.0)

    # Phase 1: Price at 2019 (below TP1) - stay INITIAL
    new_stop, phase = manager.update_price(deal_id, current_price=2019.0)
    assert new_stop is None
    assert phase == TrailingPhase.INITIAL

    # Phase 2: Price reaches TP1 = 2020 → BREAKEVEN
    new_stop, phase = manager.update_price(deal_id, current_price=2020.0)
    assert new_stop == pytest.approx(2002.0)
    assert phase == TrailingPhase.BREAKEVEN

    # Phase 3: Price at 2030 (between TP1 and TP2) - stay BREAKEVEN
    new_stop, phase = manager.update_price(deal_id, current_price=2030.0)
    assert new_stop is None
    assert phase == TrailingPhase.BREAKEVEN

    # Phase 4: Price reaches TP2 = 2040 → TP1_LOCK
    new_stop, phase = manager.update_price(deal_id, current_price=2040.0)
    assert new_stop == pytest.approx(2020.0)
    assert phase == TrailingPhase.TP1_LOCK

    # Phase 5: Price climbs to 2055 with ATR=12 → TRAILING
    # trail_stop = 2055 - 12*1.5 = 2055 - 18 = 2037
    new_stop, phase = manager.update_price(
        deal_id, current_price=2055.0, current_atr=12.0
    )
    assert new_stop == pytest.approx(2037.0)
    assert phase == TrailingPhase.TRAILING

    # Phase 6: Price climbs to 2070 → trailing stop ratchets up
    # trail_stop = 2070 - 18 = 2052
    new_stop, phase = manager.update_price(
        deal_id, current_price=2070.0, current_atr=12.0
    )
    assert new_stop == pytest.approx(2052.0)
    assert phase == TrailingPhase.TRAILING

    # Final state verification
    state = manager.get_state(deal_id)
    assert state.phase == TrailingPhase.TRAILING
    assert state.current_stop == pytest.approx(2052.0)
    assert state.highest_price == pytest.approx(2070.0)


@pytest.mark.unit
@pytest.mark.risk
def test_full_lifecycle_sell_initial_to_trailing(manager):
    """Full lifecycle SELL: INITIAL → BREAKEVEN → TP1_LOCK → TRAILING."""
    # Arrange
    deal_id = "LIFECYCLE_SELL"
    manager.register_position(
        deal_id=deal_id,
        epic="BTCUSD",
        direction="SELL",
        entry_price=50000.0,
        stop_loss=50400.0,
        atr=400.0,
    )

    # Phase 0: INITIAL
    state = manager.get_state(deal_id)
    assert state.phase == TrailingPhase.INITIAL
    assert state.current_stop == pytest.approx(50400.0)
    # risk_distance = 400, TP1 = 50000 - 400 = 49600, TP2 = 50000 - 800 = 49200

    # Phase 1: Price at 49700 (above TP1) - stay INITIAL
    new_stop, phase = manager.update_price(deal_id, current_price=49700.0)
    assert new_stop is None
    assert phase == TrailingPhase.INITIAL

    # Phase 2: Price reaches TP1 = 49600 → BREAKEVEN
    # Breakeven offset = 50000 * 0.001 = 50, new_stop = 50000 - 50 = 49950
    new_stop, phase = manager.update_price(deal_id, current_price=49600.0)
    assert new_stop == pytest.approx(49950.0)
    assert phase == TrailingPhase.BREAKEVEN

    # Phase 3: Price at 49400 (between TP1 and TP2) - stay BREAKEVEN
    new_stop, phase = manager.update_price(deal_id, current_price=49400.0)
    assert new_stop is None
    assert phase == TrailingPhase.BREAKEVEN

    # Phase 4: Price reaches TP2 = 49200 → TP1_LOCK
    new_stop, phase = manager.update_price(deal_id, current_price=49200.0)
    assert new_stop == pytest.approx(49600.0)
    assert phase == TrailingPhase.TP1_LOCK

    # Phase 5: Price drops to 49000 with ATR=300 → TRAILING
    # trail_stop = 49000 + 300*1.5 = 49000 + 450 = 49450
    new_stop, phase = manager.update_price(
        deal_id, current_price=49000.0, current_atr=300.0
    )
    assert new_stop == pytest.approx(49450.0)
    assert phase == TrailingPhase.TRAILING

    # Phase 6: Price drops to 48700 → trailing stop ratchets down
    # trail_stop = 48700 + 450 = 49150
    new_stop, phase = manager.update_price(
        deal_id, current_price=48700.0, current_atr=300.0
    )
    assert new_stop == pytest.approx(49150.0)
    assert phase == TrailingPhase.TRAILING

    # Final state verification
    state = manager.get_state(deal_id)
    assert state.phase == TrailingPhase.TRAILING
    assert state.current_stop == pytest.approx(49150.0)
    assert state.lowest_price == pytest.approx(48700.0)


# =============================================================================
# STRATEGY-ANCHORED TP LADDER (take_profit override)
# =============================================================================


@pytest.mark.unit
@pytest.mark.risk
def test_register_position_with_take_profit_anchors_tp1_at_midpoint_buy(manager):
    """When take_profit is supplied, TP1 = midpoint(entry, TP), TP2 = TP."""
    state = manager.register_position(
        deal_id="DEAL-TP-BUY",
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,  # risk = 20
        atr=10.0,
        take_profit=2010.0,  # strategy R:R = 0.5 (well below 1× risk_multiple)
    )
    # Strategy-anchored: TP1 = (2000 + 2010) / 2 = 2005, TP2 = 2010.
    assert state.tp1_level == pytest.approx(2005.0)
    assert state.tp2_level == pytest.approx(2010.0)
    # Risk distance is unchanged — only the TP ladder is re-anchored.
    assert state.risk_distance == pytest.approx(20.0)


@pytest.mark.unit
@pytest.mark.risk
def test_register_position_with_take_profit_anchors_tp1_at_midpoint_sell(manager):
    """SELL variant — strategy-TP-anchored ladder is below entry."""
    state = manager.register_position(
        deal_id="DEAL-TP-SELL",
        epic="NVDA",
        direction="SELL",
        entry_price=211.36,
        stop_loss=215.667,  # risk = 4.307
        atr=2.0,
        take_profit=210.2833,  # strategy R:R = 0.25 — TP < TP1 of legacy ladder
    )
    # TP1 = (211.36 + 210.2833) / 2 = 210.82165
    assert state.tp1_level == pytest.approx(210.82165, abs=1e-4)
    # TP2 = 210.2833 (= strategy TP, broker would close here)
    assert state.tp2_level == pytest.approx(210.2833, abs=1e-4)
    # Critical regression guard: legacy risk_multiple ladder would have placed
    # TP1 at 211.36 - 4.307 = 207.053, BELOW the strategy TP. The trailing
    # ladder would never advance because the broker would close on TP first.
    legacy_tp1 = 211.36 - 4.307 * manager.config.tp1_risk_multiple
    assert state.tp1_level > legacy_tp1
    assert state.tp1_level > state.tp2_level  # SELL: TP1 above TP2 (closer to entry)


@pytest.mark.unit
@pytest.mark.risk
def test_register_position_falls_back_to_risk_multiple_when_take_profit_none(manager):
    """take_profit=None preserves legacy risk_multiple behavior."""
    state = manager.register_position(
        deal_id="DEAL-LEGACY",
        epic="XAUUSD",
        direction="BUY",
        entry_price=2000.0,
        stop_loss=1980.0,
        atr=10.0,
        take_profit=None,
    )
    # Legacy: TP1 = entry + risk * tp1_risk_multiple (1.0) = 2020
    assert state.tp1_level == pytest.approx(2020.0)
    assert state.tp2_level == pytest.approx(2040.0)


@pytest.mark.unit
@pytest.mark.risk
def test_restore_state_with_take_profit_overrides_persisted_levels(manager):
    """On restart, supplying take_profit must override stale persisted tp1/tp2
    levels — this is the migration path for positions that were registered
    with the legacy risk_multiple ladder before the strategy-anchored fix.
    """
    # Persisted (stale) tp1/tp2 — computed with legacy ladder, OUTSIDE the
    # strategy TP (impossible target for a 0.25R strategy).
    state = manager.restore_state(
        deal_id="NVDA-STALE",
        epic="NVDA",
        direction="SELL",
        entry_price=211.36,
        current_stop=215.667,
        phase=TrailingPhase.INITIAL,
        tp1_level=209.2065,  # stale — would never fire
        tp2_level=204.8995,  # stale
        take_profit=210.2833,  # live strategy TP
    )
    # Override applied: TP1 at midpoint, TP2 at strategy TP.
    assert state.tp1_level == pytest.approx(210.82165, abs=1e-4)
    assert state.tp2_level == pytest.approx(210.2833, abs=1e-4)


@pytest.mark.unit
@pytest.mark.risk
def test_phase_advances_on_strategy_tp_progress_sell(manager):
    """End-to-end: SELL position with strategy-anchored TP advances to
    BREAKEVEN at 50% strategy progress, not at 1× risk_multiple."""
    deal_id = "DEAL-E2E"
    manager.register_position(
        deal_id=deal_id,
        epic="NVDA",
        direction="SELL",
        entry_price=211.36,
        stop_loss=215.667,
        atr=2.0,
        take_profit=210.2833,
    )
    # Price drops to midpoint (210.82) — should fire BREAKEVEN.
    new_stop, phase = manager.update_price(
        deal_id=deal_id, current_price=210.82, current_atr=2.0
    )
    assert phase == TrailingPhase.BREAKEVEN
    # SELL breakeven SL = entry - offset (entry * breakeven_offset_pct = 0.001).
    expected_sl = 211.36 - 211.36 * manager.config.breakeven_offset_pct
    assert new_stop == pytest.approx(expected_sl, abs=1e-3)
