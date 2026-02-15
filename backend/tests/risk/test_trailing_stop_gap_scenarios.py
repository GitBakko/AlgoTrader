"""
Unit tests for TrailingStopManager gap scenario fixes (CRIT-5).

Tests:
- Gap through TP1 only (normal path)
- Gap through BOTH TP1 and TP2 (critical fix)
- Gap from BREAKEVEN to beyond TP2
- Multiple gap scenarios for SELL positions
"""

import pytest

from src.risk.trailing_stop_manager import TrailingStopManager, TrailingStopConfig, TrailingPhase


class TestTrailingStopGapScenarios:
    """Test CRIT-5: Gap scenario handling in trailing stops."""

    def test_buy_normal_progression_no_gap(self):
        """
        Test normal BUY position progression without gaps.

        Scenario: Price moves smoothly through TP levels
        """
        manager = TrailingStopManager()

        # Register BUY position: entry=2000, SL=1980
        state = manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=10.0,
        )

        # TP1 should be at 2000 + 20*1.0 = 2020
        # TP2 should be at 2000 + 20*2.0 = 2040
        assert state.tp1_level == 2020.0
        assert state.tp2_level == 2040.0
        assert state.phase == TrailingPhase.INITIAL

        # Price reaches TP1 → Move to BREAKEVEN
        new_stop, phase = manager.update_price("DEAL-1", 2020.0, 10.0)
        assert phase == TrailingPhase.BREAKEVEN
        assert new_stop is not None
        assert new_stop > 2000.0  # Breakeven + offset

        # Price reaches TP2 → Move to TP1_LOCK
        new_stop, phase = manager.update_price("DEAL-1", 2040.0, 10.0)
        assert phase == TrailingPhase.TP1_LOCK
        assert new_stop == 2020.0  # Locked at TP1

    def test_buy_gap_through_both_tp_levels(self):
        """
        Test BUY position gap through BOTH TP1 and TP2.

        Scenario: Price gaps from 2010 → 2050 (skips TP1=2020, TP2=2040)
        Expected: Should skip BREAKEVEN phase, lock directly at TP1
        """
        manager = TrailingStopManager()

        # Register BUY position
        manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=10.0,
        )

        # Price gaps to 2050 (past both TP1=2020 and TP2=2040)
        new_stop, phase = manager.update_price("DEAL-1", 2050.0, 10.0)

        # CRITICAL: Should skip BREAKEVEN, go directly to TP1_LOCK
        assert phase == TrailingPhase.TP1_LOCK, f"Expected TP1_LOCK, got {phase}"
        assert new_stop == 2020.0, f"Expected TP1 lock at 2020, got {new_stop}"

    def test_buy_gap_to_exactly_tp2(self):
        """
        Test BUY position gap to exactly TP2 level.

        Scenario: Price gaps from entry directly to TP2=2040
        """
        manager = TrailingStopManager()

        manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=10.0,
        )

        # Price at exactly TP2
        new_stop, phase = manager.update_price("DEAL-1", 2040.0, 10.0)

        # Should lock at TP1
        assert phase == TrailingPhase.TP1_LOCK
        assert new_stop == 2020.0

    def test_buy_gap_between_tp1_and_tp2(self):
        """
        Test BUY position gap between TP1 and TP2.

        Scenario: Price gaps to 2035 (past TP1=2020, before TP2=2040)
        Expected: Move to BREAKEVEN (not TP1_LOCK yet)
        """
        manager = TrailingStopManager()

        manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=10.0,
        )

        # Price at 2035 (between TP1 and TP2)
        new_stop, phase = manager.update_price("DEAL-1", 2035.0, 10.0)

        # Should move to BREAKEVEN (not TP1_LOCK)
        assert phase == TrailingPhase.BREAKEVEN
        assert new_stop > 2000.0

    def test_sell_gap_through_both_tp_levels(self):
        """
        Test SELL position gap through BOTH TP1 and TP2.

        Scenario: Price gaps from 2000 → 1950 (skips TP1=1980, TP2=1960)
        Expected: Should skip BREAKEVEN, lock directly at TP1
        """
        manager = TrailingStopManager()

        # Register SELL position: entry=2000, SL=2020
        state = manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="SELL",
            entry_price=2000.0,
            stop_loss=2020.0,
            atr=10.0,
        )

        # TP1 should be at 2000 - 20*1.0 = 1980
        # TP2 should be at 2000 - 20*2.0 = 1960
        assert state.tp1_level == 1980.0
        assert state.tp2_level == 1960.0

        # Price gaps to 1950 (past both TP levels)
        new_stop, phase = manager.update_price("DEAL-1", 1950.0, 10.0)

        # CRITICAL: Should skip BREAKEVEN, go directly to TP1_LOCK
        assert phase == TrailingPhase.TP1_LOCK
        assert new_stop == 1980.0  # Locked at TP1

    def test_sell_gap_to_exactly_tp2(self):
        """
        Test SELL position gap to exactly TP2 level.

        Scenario: Price gaps from entry directly to TP2=1960
        """
        manager = TrailingStopManager()

        manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="SELL",
            entry_price=2000.0,
            stop_loss=2020.0,
            atr=10.0,
        )

        # Price at exactly TP2
        new_stop, phase = manager.update_price("DEAL-1", 1960.0, 10.0)

        # Should lock at TP1
        assert phase == TrailingPhase.TP1_LOCK
        assert new_stop == 1980.0

    def test_sell_gap_between_tp1_and_tp2(self):
        """
        Test SELL position gap between TP1 and TP2.

        Scenario: Price gaps to 1970 (past TP1=1980, before TP2=1960)
        Expected: Move to BREAKEVEN (not TP1_LOCK yet)
        """
        manager = TrailingStopManager()

        manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="SELL",
            entry_price=2000.0,
            stop_loss=2020.0,
            atr=10.0,
        )

        # Price at 1970 (between TP1 and TP2)
        new_stop, phase = manager.update_price("DEAL-1", 1970.0, 10.0)

        # Should move to BREAKEVEN (not TP1_LOCK)
        assert phase == TrailingPhase.BREAKEVEN
        assert new_stop < 2000.0

    def test_breakeven_to_tp2_gap(self):
        """
        Test gap from BREAKEVEN phase directly past TP2.

        Scenario: Position in BREAKEVEN, price gaps from 2025 → 2055
        """
        manager = TrailingStopManager()

        manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=10.0,
        )

        # First move to BREAKEVEN
        manager.update_price("DEAL-1", 2020.0, 10.0)  # Hit TP1

        # Now gap to 2055 (past TP2=2040)
        new_stop, phase = manager.update_price("DEAL-1", 2055.0, 10.0)

        # Should move to TP1_LOCK
        assert phase == TrailingPhase.TP1_LOCK
        assert new_stop == 2020.0

    def test_multiple_gaps_in_sequence(self):
        """
        Test multiple gap scenarios in sequence.

        Scenario: Price gaps multiple times
        """
        manager = TrailingStopManager()

        manager.register_position(
            deal_id="DEAL-1",
            epic="BTCUSD",
            direction="BUY",
            entry_price=50000.0,
            stop_loss=49000.0,
            atr=500.0,
        )

        # TP1 = 50000 + 1000*1.0 = 51000
        # TP2 = 50000 + 1000*2.0 = 52000

        # Gap 1: Directly to TP2+
        new_stop, phase = manager.update_price("DEAL-1", 52500.0, 500.0)
        assert phase == TrailingPhase.TP1_LOCK
        assert new_stop == 51000.0

        # Gap 2: Start trailing
        new_stop, phase = manager.update_price("DEAL-1", 53000.0, 500.0)
        if phase == TrailingPhase.TRAILING:
            assert new_stop is not None
            assert new_stop > 51000.0  # Stop should ratchet up

    def test_no_regression_normal_path(self):
        """
        Test that normal (non-gap) scenarios still work correctly.

        Ensures fix doesn't break existing functionality.
        """
        manager = TrailingStopManager()

        manager.register_position(
            deal_id="DEAL-1",
            epic="XAUUSD",
            direction="BUY",
            entry_price=2000.0,
            stop_loss=1980.0,
            atr=10.0,
        )

        # Normal progression: 2020 → 2040 → trailing
        new_stop1, phase1 = manager.update_price("DEAL-1", 2020.0, 10.0)
        assert phase1 == TrailingPhase.BREAKEVEN

        new_stop2, phase2 = manager.update_price("DEAL-1", 2040.0, 10.0)
        assert phase2 == TrailingPhase.TP1_LOCK
        assert new_stop2 == 2020.0

        # Continue to trailing
        new_stop3, phase3 = manager.update_price("DEAL-1", 2050.0, 10.0)
        if phase3 == TrailingPhase.TRAILING:
            assert new_stop3 is not None
