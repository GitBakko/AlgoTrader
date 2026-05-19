"""MT5 2026-05-19: trading-hours time-stop.

Wall-clock 12h timer killed AAPL/AMD positions opened in evening / Friday
because mr_max_hold_hours burned through overnight + weekend closures.
New behavior: accumulator increments ONLY while market_status==TRADEABLE.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.execution.schemas import ExecutionResult
from src.trading.paper_loop import PaperTradingLoop


@pytest.fixture
def loop():
    broker = MagicMock()
    broker.get_market_details = AsyncMock(
        return_value={"snapshot": {"bid": 100.0, "offer": 100.0}}
    )
    pl = PaperTradingLoop(
        prediction_service=MagicMock(),
        strategy_manager=MagicMock(),
        risk_manager=MagicMock(),
        execution_engine=MagicMock(),
        data_access=MagicMock(),
        broker=broker,
        epics=["AAPL"],
    )
    pl.execution_engine.close_position = AsyncMock(
        return_value=ExecutionResult(
            success=True, deal_id="DEAL1", realized_pnl=0.0
        )
    )
    return pl


def _pos(market_status: str, opened_at: datetime):
    return {
        "deal_id": "DEAL1",
        "epic": "AAPL",
        "direction": "BUY",
        "level": 100.0,
        "stop_level": 90.0,
        "profit_level": 110.0,
        "size": 1.0,
        "market_status": market_status,
        "opened_at": opened_at.isoformat(),
    }


@pytest.mark.asyncio
async def test_closed_market_does_not_accumulate(loop):
    """Position opened 24h ago but market CLOSED all the time → no TIME_STOP."""
    opened = datetime.now(UTC) - timedelta(hours=24)
    pos = _pos("CLOSED", opened)
    with patch("src.trading.paper_loop.get_settings") as gs:
        gs.return_value.mr_primary_enabled = True
        gs.return_value.mr_max_hold_hours = 12.0
        gs.return_value.scalp_max_hold_hours = 12.0
        gs.return_value.mr_ou_halflife_enabled = False
        await loop._check_stop_losses([pos])
    loop.execution_engine.close_position.assert_not_called()
    # Counter not seeded for CLOSED-only ticks
    assert loop._position_trading_seconds.get("DEAL1", 0.0) == 0.0


@pytest.mark.asyncio
async def test_tradeable_accumulates_across_ticks(loop):
    """Two TRADEABLE ticks 30 min apart → ~30 min accumulated."""
    opened = datetime.now(UTC) - timedelta(hours=1)
    pos = _pos("TRADEABLE", opened)

    # Seed first tick
    loop._position_last_tick["DEAL1"] = datetime.now(UTC) - timedelta(minutes=30)
    loop._position_trading_seconds["DEAL1"] = 0.0

    with patch("src.trading.paper_loop.get_settings") as gs:
        gs.return_value.mr_primary_enabled = True
        gs.return_value.mr_max_hold_hours = 12.0
        gs.return_value.scalp_max_hold_hours = 12.0
        gs.return_value.mr_ou_halflife_enabled = False
        await loop._check_stop_losses([pos])

    elapsed = loop._position_trading_seconds["DEAL1"]
    assert 1700 < elapsed < 1900, f"Expected ~1800s, got {elapsed}"
    loop.execution_engine.close_position.assert_not_called()


@pytest.mark.asyncio
async def test_time_stop_fires_only_on_trading_hours(loop):
    """Accumulator at 12h+ → TIME_STOP fires."""
    opened = datetime.now(UTC) - timedelta(hours=2)  # wall-clock young
    pos = _pos("TRADEABLE", opened)
    # Pre-loaded with 12.5h of TRADEABLE seconds (e.g. across many ticks)
    loop._position_trading_seconds["DEAL1"] = 12.5 * 3600
    loop._position_last_tick["DEAL1"] = datetime.now(UTC) - timedelta(seconds=15)

    with patch("src.trading.paper_loop.get_settings") as gs:
        gs.return_value.mr_primary_enabled = True
        gs.return_value.mr_max_hold_hours = 12.0
        gs.return_value.scalp_max_hold_hours = 12.0
        gs.return_value.mr_ou_halflife_enabled = False
        await loop._check_stop_losses([pos])

    loop.execution_engine.close_position.assert_called_once_with(
        deal_id="DEAL1", reason="TIME_STOP"
    )


@pytest.mark.asyncio
async def test_closed_then_open_does_not_double_count(loop):
    """CLOSED tick resets baseline; reopen tick must NOT count the closed gap."""
    opened = datetime.now(UTC) - timedelta(hours=10)
    pos_closed = _pos("CLOSED", opened)
    pos_open = _pos("TRADEABLE", opened)

    with patch("src.trading.paper_loop.get_settings") as gs:
        gs.return_value.mr_primary_enabled = True
        gs.return_value.mr_max_hold_hours = 12.0
        gs.return_value.scalp_max_hold_hours = 12.0
        gs.return_value.mr_ou_halflife_enabled = False

        # Tick 1 (CLOSED): baseline cleared.
        await loop._check_stop_losses([pos_closed])
        assert "DEAL1" not in loop._position_last_tick

        # Tick 2 (TRADEABLE): seeds with 0 (no delta from prior CLOSED tick).
        await loop._check_stop_losses([pos_open])

    assert loop._position_trading_seconds["DEAL1"] == 0.0
    loop.execution_engine.close_position.assert_not_called()


@pytest.mark.asyncio
async def test_authoritative_snapshot_overrides_stale_position_status():
    """Capital.com /positions[].market.marketStatus can lag /markets/{epic}.snapshot
    during extended-hours (US stocks at 08:00 UTC). Snapshot is authoritative;
    accumulator must advance when snapshot says TRADEABLE even if position field
    says CLOSED.
    """
    broker = MagicMock()
    broker.get_market_details = AsyncMock(
        return_value={
            "snapshot": {"marketStatus": "TRADEABLE", "bid": 100.0, "offer": 100.0}
        }
    )
    pl = PaperTradingLoop(
        prediction_service=MagicMock(),
        strategy_manager=MagicMock(),
        risk_manager=MagicMock(),
        execution_engine=MagicMock(),
        data_access=MagicMock(),
        broker=broker,
        epics=["AAPL"],
    )
    pl.execution_engine.close_position = AsyncMock(
        return_value=ExecutionResult(success=True, deal_id="DEAL1", realized_pnl=0.0)
    )

    pos = _pos("CLOSED", datetime.now(UTC) - timedelta(hours=1))
    pl._position_last_tick["DEAL1"] = datetime.now(UTC) - timedelta(minutes=10)
    pl._position_trading_seconds["DEAL1"] = 0.0

    with patch("src.trading.paper_loop.get_settings") as gs:
        gs.return_value.mr_primary_enabled = True
        gs.return_value.mr_max_hold_hours = 12.0
        gs.return_value.scalp_max_hold_hours = 12.0
        gs.return_value.mr_ou_halflife_enabled = False
        await pl._check_stop_losses([pos])

    elapsed = pl._position_trading_seconds["DEAL1"]
    assert 590 < elapsed < 610, (
        f"Expected ~600s accumulated (snapshot authoritative TRADEABLE), got {elapsed}"
    )


@pytest.mark.asyncio
async def test_resolve_market_status_caches_within_ttl(loop):
    """Two calls within TTL → broker hit only once. Third after TTL expiry → 2 hits."""
    loop.broker.get_market_details = AsyncMock(
        return_value={"snapshot": {"marketStatus": "TRADEABLE"}}
    )
    s1 = await loop._resolve_market_status("AAPL", "CLOSED")
    s2 = await loop._resolve_market_status("AAPL", "CLOSED")
    assert s1 == s2 == "TRADEABLE"
    assert loop.broker.get_market_details.await_count == 1

    # Force TTL expiry by aging the cache entry.
    status, _ts = loop._market_status_cache["AAPL"]
    loop._market_status_cache["AAPL"] = (status, 0.0)

    s3 = await loop._resolve_market_status("AAPL", "CLOSED")
    assert s3 == "TRADEABLE"
    assert loop.broker.get_market_details.await_count == 2


@pytest.mark.asyncio
async def test_authoritative_status_falls_back_on_broker_error(loop):
    """Broker unreachable → fall back to position.market_status (legacy behavior)."""
    loop.broker.get_market_details = AsyncMock(side_effect=TimeoutError("net down"))
    pos = _pos("CLOSED", datetime.now(UTC) - timedelta(hours=24))

    with patch("src.trading.paper_loop.get_settings") as gs:
        gs.return_value.mr_primary_enabled = True
        gs.return_value.mr_max_hold_hours = 12.0
        gs.return_value.scalp_max_hold_hours = 12.0
        gs.return_value.mr_ou_halflife_enabled = False
        await loop._check_stop_losses([pos])

    # CLOSED fallback honored: no accumulation, no close.
    assert loop._position_trading_seconds.get("DEAL1", 0.0) == 0.0
    loop.execution_engine.close_position.assert_not_called()


@pytest.mark.asyncio
async def test_gc_clears_closed_deals(loop):
    """Deals not in current_positions get evicted from accumulator dicts."""
    loop._position_trading_seconds["GHOST"] = 3600.0
    loop._position_last_tick["GHOST"] = datetime.now(UTC)
    loop._position_trading_seconds["DEAL1"] = 600.0
    loop._position_last_tick["DEAL1"] = datetime.now(UTC) - timedelta(seconds=15)

    pos = _pos("TRADEABLE", datetime.now(UTC) - timedelta(hours=1))
    with patch("src.trading.paper_loop.get_settings") as gs:
        gs.return_value.mr_primary_enabled = True
        gs.return_value.mr_max_hold_hours = 12.0
        gs.return_value.scalp_max_hold_hours = 12.0
        gs.return_value.mr_ou_halflife_enabled = False
        await loop._check_stop_losses([pos])

    assert "GHOST" not in loop._position_trading_seconds
    assert "GHOST" not in loop._position_last_tick
    assert "DEAL1" in loop._position_trading_seconds
