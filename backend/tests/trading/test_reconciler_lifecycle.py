"""
Tests for the dedicated reconciler sub-loop (Step 4 of broker-position
reconciliation split, see docs/handoff/reconciler_split_PLAN.md).

Coverage:
- spawn / no-spawn based on RECONCILER_DEDICATED_ENABLED flag
- stop() cancels both tasks
- re-entrancy: lock prevents overlapping ticks
- crash containment: reconciler exception does not kill strategy task
- _run_iteration gating in both modes (calls present when off, absent when on)
- state-recovery handoff: pending closes survive into the first reconciler tick
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.execution.schemas import ExecutionMode
from src.trading.paper_loop import PaperTradingLoop, PendingClose
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def loop_factory():
    """Factory that builds a minimally-wired PaperTradingLoop with the
    reconciler flag set as requested. Uses pure MagicMock for collaborators
    — these tests target lifecycle, not business logic.
    """

    def _build(reconciler_enabled: bool = False, reconciler_interval: int = 15):
        prediction_service = MagicMock()
        prediction_service.has_model_for.return_value = False
        prediction_service.get_loaded_models.return_value = {}

        strategy_manager = MagicMock()

        risk_manager = MagicMock()
        risk_manager.circuit_breakers = MagicMock()
        risk_manager.circuit_breakers.heartbeat = MagicMock()
        risk_manager.circuit_breakers.tripped_breakers = {}
        risk_manager.circuit_breakers.config.max_open_positions = 6
        risk_manager.equity_curve_filter = MagicMock()
        risk_manager.drawdown_monitor = MagicMock()
        risk_manager.drawdown_monitor.state = MagicMock()
        risk_manager.drawdown_monitor.state.current_equity = 10000.0

        execution_engine = AsyncMock()
        execution_engine.mode = ExecutionMode.PAPER
        execution_engine.get_open_positions = AsyncMock(return_value=[])
        tracker = MagicMock()
        tracker.get_paper_positions_sync.return_value = []
        execution_engine._position_tracker = tracker

        loop = PaperTradingLoop(
            prediction_service=prediction_service,
            strategy_manager=strategy_manager,
            risk_manager=risk_manager,
            execution_engine=execution_engine,
            interval_seconds=1,
            epics=["XAUUSD"],
        )
        # Override flag post-init (avoids monkeypatching get_settings cache).
        loop._reconciler_enabled = reconciler_enabled
        loop._reconciler_interval = reconciler_interval
        return loop

    return _build


# ---------------------------------------------------------------------------
# Spawn / cancel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconciler_not_started_when_flag_false(loop_factory):
    loop = loop_factory(reconciler_enabled=False)
    with patch.object(loop, "_run_loop", new=AsyncMock()):
        loop.start()
        await asyncio.sleep(0)  # let task start
        assert loop._reconciler_task is None
        loop.stop()
        await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_reconciler_started_when_flag_true(loop_factory):
    loop = loop_factory(reconciler_enabled=True)

    async def _noop():
        # Sleep forever so the task stays alive long enough to assert on it.
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return

    with patch.object(loop, "_run_loop", new=AsyncMock(side_effect=_noop)), \
            patch.object(loop, "_run_reconciler_loop", new=AsyncMock(side_effect=_noop)):
        loop.start()
        await asyncio.sleep(0)
        try:
            assert loop._reconciler_task is not None
            assert isinstance(loop._reconciler_task, asyncio.Task)
            assert not loop._reconciler_task.done()
        finally:
            loop.stop()
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_reconciler_stop_cancels_both_tasks(loop_factory):
    loop = loop_factory(reconciler_enabled=True)

    async def _wait_forever():
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return

    with patch.object(loop, "_run_loop", new=AsyncMock(side_effect=_wait_forever)), \
            patch.object(loop, "_run_reconciler_loop", new=AsyncMock(side_effect=_wait_forever)):
        loop.start()
        await asyncio.sleep(0)
        strategy_task = loop._task
        reconciler_task = loop._reconciler_task

        loop.stop()
        await asyncio.sleep(0.05)

        assert strategy_task.done() or strategy_task.cancelled()
        assert reconciler_task.done() or reconciler_task.cancelled()


# ---------------------------------------------------------------------------
# _run_iteration gating
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_strategy_loop_skips_reconciler_calls_when_enabled(loop_factory):
    loop = loop_factory(reconciler_enabled=True)
    loop.get_positions_async = AsyncMock(return_value=[])
    loop._refresh_spread_blocks = AsyncMock()
    loop._refresh_correlation_matrix = AsyncMock()
    loop._refresh_correlation_regime = AsyncMock()
    loop._init_regime_gate = MagicMock()

    with patch.object(loop, "_detect_broker_closed", new=AsyncMock()) as mock_detect, \
            patch.object(loop, "_update_trailing_stops", new=AsyncMock()) as mock_trail, \
            patch.object(loop, "_check_stop_losses", new=AsyncMock()) as mock_sl:
        await loop._run_iteration(force=False)

        mock_detect.assert_not_called()
        mock_trail.assert_not_called()
        mock_sl.assert_not_called()


@pytest.mark.asyncio
async def test_strategy_loop_calls_reconciler_methods_when_disabled(loop_factory):
    loop = loop_factory(reconciler_enabled=False)
    loop.get_positions_async = AsyncMock(return_value=[])
    loop._refresh_spread_blocks = AsyncMock()
    loop._refresh_correlation_matrix = AsyncMock()
    loop._refresh_correlation_regime = AsyncMock()
    loop._init_regime_gate = MagicMock()

    with patch.object(loop, "_detect_broker_closed", new=AsyncMock()) as mock_detect, \
            patch.object(loop, "_update_trailing_stops", new=AsyncMock()) as mock_trail, \
            patch.object(loop, "_check_stop_losses", new=AsyncMock()) as mock_sl:
        await loop._run_iteration(force=False)

        mock_detect.assert_called_once()
        mock_trail.assert_called_once()
        mock_sl.assert_called_once()


# ---------------------------------------------------------------------------
# Re-entrancy + crash containment
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconciler_reentrancy_guard(loop_factory):
    """Two concurrent acquires of _reconciler_lock must serialize.

    We simulate by holding the lock from outside while the reconciler
    body would run. The body should not start until the outer holder
    releases. The lock is asyncio.Lock — fairness guarantee.
    """
    loop = loop_factory(reconciler_enabled=True)
    started_at: list[float] = []

    async def _slow_tick():
        started_at.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.05)

    with patch.object(loop, "_run_reconciler_tick", new=AsyncMock(side_effect=_slow_tick)):
        async with loop._reconciler_lock:
            # While we hold it, schedule a second acquire via the same path.
            async def _try_acquire():
                async with loop._reconciler_lock:
                    await loop._run_reconciler_tick()

            blocked_task = asyncio.create_task(_try_acquire())
            await asyncio.sleep(0.05)
            # Should not have started yet — lock held by us.
            assert not started_at
        # Release. The other task can now run.
        await blocked_task
        assert len(started_at) == 1


@pytest.mark.asyncio
async def test_reconciler_crash_does_not_kill_strategy_loop(loop_factory):
    """A raise inside _run_reconciler_loop must not propagate to the
    strategy task. The done callback handles the crash separately.
    """
    loop = loop_factory(reconciler_enabled=True)

    strategy_alive = asyncio.Event()

    async def _strategy_alive_marker():
        strategy_alive.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            return

    async def _crashing_reconciler():
        raise RuntimeError("boom")

    with patch.object(loop, "_run_loop", new=AsyncMock(side_effect=_strategy_alive_marker)), \
            patch.object(loop, "_run_reconciler_loop", new=AsyncMock(side_effect=_crashing_reconciler)):
        loop.start()
        await asyncio.wait_for(strategy_alive.wait(), timeout=1.0)
        await asyncio.sleep(0.05)  # let reconciler crash

        try:
            assert loop._task is not None
            assert not loop._task.done()
            assert loop._reconciler_task is not None
            assert loop._reconciler_task.done()
            # Crash captured on reconciler task, not strategy task.
            assert isinstance(loop._reconciler_task.exception(), RuntimeError)
        finally:
            loop.stop()
            await asyncio.sleep(0.05)


# ---------------------------------------------------------------------------
# State-recovery handoff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_state_recovery_handoff_before_start(loop_factory):
    """Orphans written into _pending_close_detections by state_recovery
    BEFORE start() must survive — the reconciler shares the same dict
    and picks them up on its first tick.
    """
    loop = loop_factory(reconciler_enabled=True)
    pending = PendingClose(
        deal_id="ORPHAN-001",
        deal_reference=None,
        epic="XAUUSD",
        direction="BUY",
        size=0.1,
        entry_price=2000.0,
        prev_pos={"deal_id": "ORPHAN-001", "epic": "XAUUSD"},
        first_seen=datetime.now(timezone.utc),
        retry_count=0,
    )
    loop._pending_close_detections["ORPHAN-001"] = pending

    # The reconciler tick must observe the orphan in _pending_close_detections.
    seen_pending: list[str] = []

    async def _capture_pending(_current):
        seen_pending.extend(loop._pending_close_detections.keys())

    loop.get_positions_async = AsyncMock(return_value=[])
    with patch.object(loop, "_detect_broker_closed", new=AsyncMock(side_effect=_capture_pending)), \
            patch.object(loop, "_update_trailing_stops", new=AsyncMock()), \
            patch.object(loop, "_check_stop_losses", new=AsyncMock()):
        await loop._run_reconciler_tick()

    assert "ORPHAN-001" in seen_pending
