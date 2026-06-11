"""Regression: a broker fetch failure in DEMO/LIVE must SKIP the reconciler
tick, not run it against an empty book (audit M1.4 / finding H4).

On HEAD the except branch falls back to get_paper_positions(), which
returns [] for any non-PAPER mode; the empty list then unregisters every
trailing-stop state and (after 600s) arms false UNRECONCILED closes.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.schemas import ExecutionMode
from src.trading.paper_loop import PaperTradingLoop


def _make_loop(mode: ExecutionMode) -> PaperTradingLoop:
    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop.execution_engine = MagicMock(mode=mode)
    loop.get_positions_async = AsyncMock(side_effect=TimeoutError("broker down"))
    loop._detect_broker_closed = AsyncMock()
    loop._update_trailing_stops = AsyncMock()
    loop._check_stop_losses = AsyncMock()
    loop._reconciler_skip_count = 0
    return loop


@pytest.mark.asyncio
async def test_fetch_failure_skips_tick_in_demo_mode():
    loop = _make_loop(ExecutionMode.DEMO)

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
