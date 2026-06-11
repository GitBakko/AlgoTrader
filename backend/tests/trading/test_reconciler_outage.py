"""Regression: a broker fetch failure in DEMO/LIVE must SKIP the reconciler
tick, not run it against an empty book (audit M1.4 / finding H4).

On HEAD the except branch falls back to get_paper_positions(), which
returns [] for any non-PAPER mode; the empty list then unregisters every
trailing-stop state and (after 600s) arms false UNRECONCILED closes.

Review follow-up: a sustained outage must NOT stay silent forever — the
clean skip-return resets _run_reconciler_loop's consecutive_errors, so a
deterministic fetch bug would disable close detection + trailing + local
SL/TP enforcement indefinitely at WARNING level. After 20 CONSECUTIVE
skips (~5 min at 15s) the tick escalates: ERROR log + CRITICAL alert,
fired once per outage (== threshold, re-arms after a successful fetch).
"""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.execution.schemas import ExecutionMode
from src.trading.paper_loop import (
    _RECONCILER_SKIP_ESCALATION_THRESHOLD,
    PaperTradingLoop,
)


def _make_loop(mode: ExecutionMode) -> PaperTradingLoop:
    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop.execution_engine = MagicMock(mode=mode)
    loop.get_positions_async = AsyncMock(side_effect=TimeoutError("broker down"))
    loop._detect_broker_closed = AsyncMock()
    loop._update_trailing_stops = AsyncMock()
    loop._check_stop_losses = AsyncMock()
    loop._reconciler_skip_count = 0
    loop._reconciler_consecutive_skips = 0
    loop._reconciler_interval = 15
    return loop


@pytest.fixture
def propagate_loguru(caplog):
    """Forward loguru records to stdlib logging so caplog can capture them
    (same pattern as tests/broker/test_transaction_model.py)."""
    from loguru import logger

    class _PropagateHandler:
        def write(self, message):
            record = message.record
            logging.getLogger(record["name"]).log(record["level"].no, record["message"])

    handler_id = logger.add(_PropagateHandler(), format="{message}", level="WARNING")
    yield
    logger.remove(handler_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", [ExecutionMode.DEMO, ExecutionMode.LIVE])
async def test_fetch_failure_skips_tick_in_broker_modes(mode):
    loop = _make_loop(mode)

    await loop._run_reconciler_tick()

    loop._detect_broker_closed.assert_not_awaited()
    loop._update_trailing_stops.assert_not_awaited()
    loop._check_stop_losses.assert_not_awaited()
    assert loop._reconciler_skip_count == 1


@pytest.mark.asyncio
async def test_fetch_failure_in_paper_mode_uses_local_cache():
    """PAPER mode has a genuine local book — the legacy fallback stays."""
    loop = _make_loop(ExecutionMode.PAPER)
    local_book = [{"deal_id": "P1", "epic": "XAUUSD"}]
    loop.get_paper_positions = MagicMock(return_value=local_book)

    await loop._run_reconciler_tick()

    loop._detect_broker_closed.assert_awaited_once_with(local_book)
    assert loop._reconciler_skip_count == 0


@pytest.mark.asyncio
async def test_consecutive_skips_accumulate():
    """Two failing ticks → consecutive==2, lifetime==2, downstream never run."""
    loop = _make_loop(ExecutionMode.DEMO)

    await loop._run_reconciler_tick()
    await loop._run_reconciler_tick()

    assert loop._reconciler_consecutive_skips == 2
    assert loop._reconciler_skip_count == 2
    loop._detect_broker_closed.assert_not_awaited()
    loop._update_trailing_stops.assert_not_awaited()
    loop._check_stop_losses.assert_not_awaited()


@pytest.mark.asyncio
async def test_successful_fetch_resets_consecutive_but_not_lifetime():
    """Fail, then succeed → consecutive resets to 0 (escalation re-armed),
    lifetime counter keeps the skip, downstream runs on the second tick."""
    loop = _make_loop(ExecutionMode.DEMO)
    broker_book = [{"deal_id": "D1", "epic": "BTCUSD"}]

    await loop._run_reconciler_tick()  # fail → skip
    loop.get_positions_async = AsyncMock(return_value=broker_book)
    await loop._run_reconciler_tick()  # success

    assert loop._reconciler_consecutive_skips == 0
    assert loop._reconciler_skip_count == 1
    loop._detect_broker_closed.assert_awaited_once_with(broker_book)
    loop._update_trailing_stops.assert_awaited_once_with(broker_book)
    loop._check_stop_losses.assert_awaited_once_with(broker_book)


@pytest.mark.asyncio
async def test_escalation_fires_once_at_threshold(propagate_loguru, caplog):
    """Skip #20 → ERROR log + CRITICAL alert via get_alert_manager()."""
    loop = _make_loop(ExecutionMode.DEMO)
    loop._reconciler_consecutive_skips = _RECONCILER_SKIP_ESCALATION_THRESHOLD - 1
    loop._reconciler_skip_count = _RECONCILER_SKIP_ESCALATION_THRESHOLD - 1

    alert_manager = MagicMock()
    alert_manager.send_alert = AsyncMock()
    with (
        patch(
            "src.monitoring.alerting.alert_manager.get_alert_manager",
            return_value=alert_manager,
        ),
        patch(
            "src.utils.config.get_settings",
            return_value=MagicMock(alerts_enabled=True),
        ),
        caplog.at_level(logging.ERROR, logger="src.trading.paper_loop"),
    ):
        await loop._run_reconciler_tick()

    assert loop._reconciler_consecutive_skips == _RECONCILER_SKIP_ESCALATION_THRESHOLD
    assert any(
        "OFFLINE" in r.message for r in caplog.records if r.levelno >= logging.ERROR
    ), f"Expected OFFLINE ERROR log, got: {[r.message for r in caplog.records]}"
    alert_manager.send_alert.assert_awaited_once()
    alert = alert_manager.send_alert.await_args.args[0]
    assert alert.severity.value == "CRITICAL"
    assert alert.details["consecutive_skips"] == _RECONCILER_SKIP_ESCALATION_THRESHOLD


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "preset",
    [_RECONCILER_SKIP_ESCALATION_THRESHOLD, _RECONCILER_SKIP_ESCALATION_THRESHOLD + 1],
)
async def test_escalation_does_not_refire_past_threshold(preset):
    """Counter already past the threshold → escalation must NOT fire again
    (only when the counter EQUALS the threshold)."""
    loop = _make_loop(ExecutionMode.DEMO)
    loop._reconciler_consecutive_skips = preset
    loop._reconciler_skip_count = preset

    alert_manager = MagicMock()
    alert_manager.send_alert = AsyncMock()
    with (
        patch(
            "src.monitoring.alerting.alert_manager.get_alert_manager",
            return_value=alert_manager,
        ),
        patch(
            "src.utils.config.get_settings",
            return_value=MagicMock(alerts_enabled=True),
        ),
    ):
        await loop._run_reconciler_tick()

    assert loop._reconciler_consecutive_skips == preset + 1
    alert_manager.send_alert.assert_not_awaited()
