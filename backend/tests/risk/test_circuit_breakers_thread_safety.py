"""
Unit tests for CircuitBreakerManager thread safety (CRIT-4).

Tests:
- Concurrent trip() calls
- Concurrent clear() calls
- Concurrent record_trade_result() calls
- Race condition in _try_auto_reset()
- Thread-safe property access
"""

import threading
import time
import pytest

from src.risk.circuit_breakers import CircuitBreakerManager, CircuitBreakerConfig, CircuitBreakerType


class TestCircuitBreakerThreadSafety:
    """Test CRIT-4: Thread-safety in CircuitBreakerManager."""

    def test_concurrent_trip_calls(self):
        """
        Test that concurrent trip() calls don't cause race conditions.

        Scenario: 10 threads simultaneously trip different circuit breakers.
        """
        manager = CircuitBreakerManager()

        def trip_breaker(cb_type: CircuitBreakerType):
            """Trip a specific breaker from a thread."""
            manager._trip(cb_type, f"Test trip {cb_type.value}")

        breaker_types = [
            CircuitBreakerType.DAILY_LOSS,
            CircuitBreakerType.CONSECUTIVE_LOSSES,
            CircuitBreakerType.MAX_POSITIONS,
            CircuitBreakerType.SLIPPAGE_ANOMALY,
            CircuitBreakerType.HEARTBEAT_TIMEOUT,
            CircuitBreakerType.VOLATILITY_SPIKE,
        ]

        # Create threads to trip each breaker
        threads = []
        for cb_type in breaker_types:
            thread = threading.Thread(target=trip_breaker, args=(cb_type,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify all breakers are tripped
        assert len(manager._tripped) == len(breaker_types)
        assert len(manager._tripped_at) == len(breaker_types)

        # Verify no duplicates or lost updates
        for cb_type in breaker_types:
            assert cb_type in manager._tripped
            assert cb_type in manager._tripped_at

    def test_concurrent_record_trade_result(self):
        """
        Test that concurrent record_trade_result() calls are thread-safe.

        Scenario: 100 threads record trades (50 wins, 50 losses).
        """
        manager = CircuitBreakerManager()

        def record_trade(is_win: bool):
            """Record a trade from a thread."""
            manager.record_trade_result(is_win)

        # Create 50 winning and 50 losing threads
        threads = []
        for _ in range(50):
            thread = threading.Thread(target=record_trade, args=(True,))
            threads.append(thread)
        for _ in range(50):
            thread = threading.Thread(target=record_trade, args=(False,))
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Consecutive losses should be <= 50 (wins reset the counter)
        # The exact value depends on thread scheduling
        assert manager._consecutive_losses <= 50

    def test_concurrent_clear_and_trip(self):
        """
        Test concurrent trip and clear operations don't corrupt state.

        Scenario: Thread A trips breakers, Thread B clears them, repeatedly.
        """
        manager = CircuitBreakerManager()
        stop_flag = threading.Event()

        def trip_repeatedly():
            """Trip DAILY_LOSS breaker repeatedly."""
            while not stop_flag.is_set():
                manager._trip(CircuitBreakerType.DAILY_LOSS, "Test trip")
                time.sleep(0.001)

        def clear_repeatedly():
            """Clear DAILY_LOSS breaker repeatedly."""
            while not stop_flag.is_set():
                manager._clear(CircuitBreakerType.DAILY_LOSS)
                time.sleep(0.001)

        # Start both threads
        trip_thread = threading.Thread(target=trip_repeatedly)
        clear_thread = threading.Thread(target=clear_repeatedly)

        trip_thread.start()
        clear_thread.start()

        # Let them run for 0.5 seconds
        time.sleep(0.5)
        stop_flag.set()

        trip_thread.join()
        clear_thread.join()

        # Verify state is consistent (no KeyError, no corruption)
        # _tripped and _tripped_at should always be in sync
        assert set(manager._tripped.keys()) == set(manager._tripped_at.keys())

    def test_concurrent_check_all_calls(self):
        """
        Test that concurrent check_all() calls are thread-safe.

        Scenario: 20 threads call check_all() simultaneously.
        """
        config = CircuitBreakerConfig(max_open_positions=5)
        manager = CircuitBreakerManager(config)

        results = []
        lock = threading.Lock()

        def check_all_thread():
            """Call check_all from thread."""
            is_ok, reasons = manager.check_all(
                daily_pnl_pct=-0.01,
                open_position_count=10,  # Exceeds limit
            )
            with lock:
                results.append((is_ok, reasons))

        # Create 20 threads
        threads = []
        for _ in range(20):
            thread = threading.Thread(target=check_all_thread)
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # All threads should get consistent results
        assert len(results) == 20
        # All should fail (positions > limit)
        assert all(not is_ok for is_ok, _ in results)

        # Verify internal state is consistent
        assert set(manager._tripped.keys()) == set(manager._tripped_at.keys())

    def test_concurrent_record_slippage(self):
        """
        Test that concurrent record_slippage() calls are thread-safe.

        Scenario: 100 threads record slippage simultaneously.
        """
        manager = CircuitBreakerManager()

        def record_slip():
            """Record slippage from thread."""
            manager.record_slippage(0.001)  # 0.1% slippage

        threads = []
        for _ in range(100):
            thread = threading.Thread(target=record_slip)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Slippage history is capped at slippage_window * 3 (default 5 * 3 = 15)
        max_history = manager.config.slippage_window * 3
        # Verify we hit the cap (all 100 were recorded, but only last 15 kept)
        assert len(manager._slippage_history) == max_history
        # Verify no duplicates or corruption
        assert all(s == 0.001 for s in manager._slippage_history)

    def test_concurrent_reset_and_trip(self):
        """
        Test concurrent reset_all() and trip() don't corrupt state.

        Scenario: Thread A trips breakers, Thread B calls reset_all().
        """
        manager = CircuitBreakerManager()
        stop_flag = threading.Event()

        def trip_all_repeatedly():
            """Trip all breakers repeatedly."""
            while not stop_flag.is_set():
                manager._trip(CircuitBreakerType.DAILY_LOSS, "Test 1")
                manager._trip(CircuitBreakerType.MAX_POSITIONS, "Test 2")
                time.sleep(0.001)

        def reset_repeatedly():
            """Reset all breakers repeatedly."""
            while not stop_flag.is_set():
                manager.reset_all()
                time.sleep(0.001)

        trip_thread = threading.Thread(target=trip_all_repeatedly)
        reset_thread = threading.Thread(target=reset_repeatedly)

        trip_thread.start()
        reset_thread.start()

        time.sleep(0.5)
        stop_flag.set()

        trip_thread.join()
        reset_thread.join()

        # Verify state consistency
        assert set(manager._tripped.keys()) == set(manager._tripped_at.keys())

    def test_property_access_thread_safe(self):
        """
        Test that property access (is_tripped, tripped_breakers) is thread-safe.

        Scenario: Threads read properties while other threads modify state.
        """
        manager = CircuitBreakerManager()
        stop_flag = threading.Event()
        errors = []

        def modify_state():
            """Trip and clear breakers repeatedly."""
            while not stop_flag.is_set():
                manager._trip(CircuitBreakerType.DAILY_LOSS, "Test")
                manager._clear(CircuitBreakerType.DAILY_LOSS)
                time.sleep(0.001)

        def read_properties():
            """Read properties repeatedly."""
            while not stop_flag.is_set():
                try:
                    _ = manager.is_tripped
                    _ = manager.tripped_breakers
                except Exception as e:
                    errors.append(str(e))
                time.sleep(0.001)

        modify_thread = threading.Thread(target=modify_state)
        read_thread1 = threading.Thread(target=read_properties)
        read_thread2 = threading.Thread(target=read_properties)

        modify_thread.start()
        read_thread1.start()
        read_thread2.start()

        time.sleep(0.5)
        stop_flag.set()

        modify_thread.join()
        read_thread1.join()
        read_thread2.join()

        # No exceptions should occur
        assert len(errors) == 0

    def test_heartbeat_thread_safe(self):
        """
        Test that heartbeat() is thread-safe when called concurrently.

        Scenario: Multiple threads call heartbeat() simultaneously.
        """
        manager = CircuitBreakerManager()

        def call_heartbeat():
            """Call heartbeat from thread."""
            manager.heartbeat()

        threads = []
        for _ in range(50):
            thread = threading.Thread(target=call_heartbeat)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Heartbeat should update without errors
        # Verify heartbeat timeout breaker is cleared
        assert CircuitBreakerType.HEARTBEAT_TIMEOUT not in manager._tripped

    def test_baseline_atr_concurrent_access(self):
        """
        Test concurrent update_baseline_atr() and get_baseline_atr() calls.

        Scenario: Threads update ATRs while others read them.
        """
        manager = CircuitBreakerManager()
        stop_flag = threading.Event()

        def update_atr():
            """Update ATRs repeatedly."""
            while not stop_flag.is_set():
                manager.update_baseline_atr("XAUUSD", 10.0)
                manager.update_baseline_atr("BTCUSD", 20.0)
                time.sleep(0.001)

        def read_atr():
            """Read ATRs repeatedly."""
            while not stop_flag.is_set():
                manager.get_baseline_atr("XAUUSD")
                manager.get_baseline_atr("BTCUSD")
                time.sleep(0.001)

        update_thread = threading.Thread(target=update_atr)
        read_thread1 = threading.Thread(target=read_atr)
        read_thread2 = threading.Thread(target=read_atr)

        update_thread.start()
        read_thread1.start()
        read_thread2.start()

        time.sleep(0.5)
        stop_flag.set()

        update_thread.join()
        read_thread1.join()
        read_thread2.join()

        # Verify final state
        assert manager.get_baseline_atr("XAUUSD") == 10.0
        assert manager.get_baseline_atr("BTCUSD") == 20.0
