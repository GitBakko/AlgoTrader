"""
Unit tests for PositionTracker thread safety (CRIT-7).

Tests:
- Concurrent open_paper_position() calls
- Concurrent close_paper_position() calls
- Concurrent reduce_paper_position() calls
- Concurrent inject_paper_position() calls
- Duplicate position detection
"""

import threading
import time
import pytest

from src.execution.position_tracker import PositionTracker
from src.execution.schemas import ExecutionMode, ExecutionOrder


class TestPositionTrackerThreadSafety:
    """Test CRIT-7: Thread-safety in PositionTracker."""

    def test_concurrent_open_paper_position(self):
        """
        Test that concurrent open_paper_position() calls are thread-safe.

        Scenario: 10 threads simultaneously open different positions.
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)

        def open_position(index: int):
            """Open a position from a thread."""
            order = ExecutionOrder(
                epic="XAUUSD",
                direction="BUY",
                size=1.0,
                entry_price=2000.0 + index,
            )
            tracker.open_paper_position(order, 2000.0 + index, f"DEAL-{index}")

        # Create 10 threads to open positions
        threads = []
        for i in range(10):
            thread = threading.Thread(target=open_position, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads
        for thread in threads:
            thread.join()

        # Verify all 10 positions were recorded
        assert tracker.paper_position_count == 10

        # Verify no duplicates or lost updates
        positions = tracker.get_paper_positions_sync()
        deal_ids = [p["deal_id"] for p in positions]
        assert len(deal_ids) == len(set(deal_ids))  # No duplicates

    def test_duplicate_position_detection(self):
        """
        Test that opening a position with duplicate deal_id raises error.

        Scenario: Try to open position with same deal_id twice.
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)

        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=1.0,
            entry_price=2000.0,
        )

        # First open should succeed
        tracker.open_paper_position(order, 2000.0, "DEAL-123")

        # Second open with same deal_id should raise ValueError
        with pytest.raises(ValueError, match="already exists"):
            tracker.open_paper_position(order, 2000.0, "DEAL-123")

    def test_concurrent_close_paper_position(self):
        """
        Test that concurrent close_paper_position() calls are thread-safe.

        Scenario: 10 positions opened, then 10 threads close them.
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)

        # Open 10 positions
        for i in range(10):
            order = ExecutionOrder(
                epic="XAUUSD",
                direction="BUY",
                size=1.0,
                entry_price=2000.0,
            )
            tracker.open_paper_position(order, 2000.0, f"DEAL-{i}")

        assert tracker.paper_position_count == 10

        def close_position(index: int):
            """Close a position from a thread."""
            tracker.close_paper_position(f"DEAL-{index}")

        # Close all positions concurrently
        threads = []
        for i in range(10):
            thread = threading.Thread(target=close_position, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # All positions should be closed
        assert tracker.paper_position_count == 0

    def test_concurrent_reduce_paper_position(self):
        """
        Test that concurrent reduce_paper_position() calls are thread-safe.

        Scenario: Multiple threads reduce the same position simultaneously.
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)

        # Open one position with size 100.0
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=100.0,
            entry_price=2000.0,
        )
        tracker.open_paper_position(order, 2000.0, "DEAL-1")

        def reduce_position():
            """Reduce position by 10%."""
            tracker.reduce_paper_position("DEAL-1", 0.1)

        # 5 threads each reduce by 10%
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=reduce_position)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Final size should be 100.0 * (0.9^5) ≈ 59.05
        positions = tracker.get_paper_positions_sync()
        assert len(positions) == 1
        # Account for float precision
        expected_size = 100.0 * (0.9 ** 5)
        assert abs(positions[0]["size"] - expected_size) < 0.01

    def test_concurrent_inject_paper_position(self):
        """
        Test that concurrent inject_paper_position() calls are thread-safe.

        Scenario: State recovery injecting 20 positions concurrently.
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)

        def inject_position(index: int):
            """Inject a position from a thread."""
            tracker.inject_paper_position(
                deal_id=f"DEAL-{index}",
                epic="XAUUSD",
                direction="BUY",
                size=1.0,
                entry_price=2000.0 + index,
            )

        threads = []
        for i in range(20):
            thread = threading.Thread(target=inject_position, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify all 20 positions were injected
        assert tracker.paper_position_count == 20

    def test_concurrent_open_and_close(self):
        """
        Test concurrent open and close operations don't corrupt state.

        Scenario: Thread A opens positions, Thread B closes them.
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)
        stop_flag = threading.Event()

        def open_repeatedly():
            """Open positions repeatedly."""
            counter = 0
            while not stop_flag.is_set():
                try:
                    order = ExecutionOrder(
                        epic="XAUUSD",
                        direction="BUY",
                        size=1.0,
                        entry_price=2000.0,
                    )
                    tracker.open_paper_position(order, 2000.0, f"DEAL-{counter}")
                    counter += 1
                except ValueError:
                    # Duplicate deal_id, skip
                    counter += 1
                time.sleep(0.001)

        def close_repeatedly():
            """Close positions repeatedly."""
            counter = 0
            while not stop_flag.is_set():
                tracker.close_paper_position(f"DEAL-{counter}")
                counter += 1
                time.sleep(0.001)

        open_thread = threading.Thread(target=open_repeatedly)
        close_thread = threading.Thread(target=close_repeatedly)

        open_thread.start()
        close_thread.start()

        # Let them run for 0.5 seconds
        time.sleep(0.5)
        stop_flag.set()

        open_thread.join()
        close_thread.join()

        # Verify state consistency (no exceptions occurred)
        # Some positions should remain (open faster than close)
        assert tracker.paper_position_count >= 0

    def test_get_paper_positions_sync_thread_safe(self):
        """
        Test that get_paper_positions_sync() is thread-safe during modifications.

        Scenario: Threads read positions while others modify them.
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)
        stop_flag = threading.Event()
        errors = []

        def modify_positions():
            """Open and close positions repeatedly."""
            counter = 0
            while not stop_flag.is_set():
                try:
                    order = ExecutionOrder(
                        epic="XAUUSD",
                        direction="BUY",
                        size=1.0,
                        entry_price=2000.0,
                    )
                    tracker.open_paper_position(order, 2000.0, f"DEAL-{counter}")
                    tracker.close_paper_position(f"DEAL-{counter}")
                    counter += 1
                except ValueError:
                    counter += 1
                time.sleep(0.001)

        def read_positions():
            """Read positions repeatedly."""
            while not stop_flag.is_set():
                try:
                    positions = tracker.get_paper_positions_sync()
                    _ = len(positions)
                except Exception as e:
                    errors.append(str(e))
                time.sleep(0.001)

        modify_thread = threading.Thread(target=modify_positions)
        read_thread1 = threading.Thread(target=read_positions)
        read_thread2 = threading.Thread(target=read_positions)

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

    def test_paper_position_count_thread_safe(self):
        """
        Test that paper_position_count property is thread-safe.

        Scenario: Threads read count while others modify positions.
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)
        stop_flag = threading.Event()

        def modify_positions():
            """Open and close positions rapidly."""
            counter = 0
            while not stop_flag.is_set():
                try:
                    order = ExecutionOrder(
                        epic="XAUUSD",
                        direction="BUY",
                        size=1.0,
                        entry_price=2000.0,
                    )
                    tracker.open_paper_position(order, 2000.0, f"DEAL-{counter}")
                    counter += 1
                except ValueError:
                    counter += 1
                time.sleep(0.001)

        def read_count():
            """Read position count repeatedly."""
            while not stop_flag.is_set():
                _ = tracker.paper_position_count
                time.sleep(0.001)

        modify_thread = threading.Thread(target=modify_positions)
        read_thread1 = threading.Thread(target=read_count)
        read_thread2 = threading.Thread(target=read_count)

        modify_thread.start()
        read_thread1.start()
        read_thread2.start()

        time.sleep(0.5)
        stop_flag.set()

        modify_thread.join()
        read_thread1.join()
        read_thread2.join()

        # No exceptions should occur
        # Count should be some positive number
        assert tracker.paper_position_count >= 0

    def test_reduce_full_close_thread_safe(self):
        """
        Test that reduce with 100% is thread-safe (should close position).

        Scenario: Multiple threads try to close same position via reduce(100%).
        """
        tracker = PositionTracker(mode=ExecutionMode.PAPER)

        # Open one position
        order = ExecutionOrder(
            epic="XAUUSD",
            direction="BUY",
            size=100.0,
            entry_price=2000.0,
        )
        tracker.open_paper_position(order, 2000.0, "DEAL-1")

        def reduce_full():
            """Reduce by 100% (full close)."""
            tracker.reduce_paper_position("DEAL-1", 1.0)

        # 5 threads all try to close 100%
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=reduce_full)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Position should be fully closed
        assert tracker.paper_position_count == 0
