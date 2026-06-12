import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from src.broker.models import DealConfirmation


def _ctx():
    from forward.strategy import MarketContext
    return MarketContext("AAPL", 100.0, 103.0, 103.0,
                         datetime(2026, 6, 12, 14, 0, tzinfo=timezone.utc),
                         datetime(2026, 6, 12, 19, 45, tzinfo=timezone.utc))


def _strat():
    from forward.strategy import GapFadeStrategy
    return GapFadeStrategy(epics=["AAPL"])


def _seed_closed(led, session_date, pnl, key):
    led.record_open(strategy="orb", epic=f"E{key}", session_date=session_date,
                    deal_id=f"D{key}", direction="BUY", entry=100.0, size=1.0,
                    stop_level=99.0, rationale="t",
                    opened_at=f"{session_date}T14:00:00+00:00")
    led.record_close(deal_id=f"D{key}", exit_price=99.0, net_pnl=pnl,
                     closed_at=f"{session_date}T19:45:00+00:00", close_reason="BROKER_TRADE")


@pytest.mark.asyncio
async def test_blocks_new_entries_at_daily_loss_limit(tmp_path):
    # NOTE: loguru does NOT propagate to std logging, so pytest's caplog can't see
    # it (no bridge in tests/conftest.py) — capture via a direct loguru sink.
    from loguru import logger as loguru_logger
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "g1.db")
    _seed_closed(led, "2026-06-12", -120.0, 1)
    client = AsyncMock()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, daily_loss_limit_eur=100.0, dry_run=False)
    records = []
    sink_id = loguru_logger.add(lambda m: records.append(m.record), level="CRITICAL")
    try:
        out = await ex.try_enter(_strat(), _ctx(), "2026-06-12")
    finally:
        loguru_logger.remove(sink_id)
    assert out is None
    client.create_position.assert_not_called()
    assert any(r["level"].name == "CRITICAL" for r in records)


@pytest.mark.asyncio
async def test_allows_entries_below_limit(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "g2.db")
    _seed_closed(led, "2026-06-12", -50.0, 1)
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED",
        "epic": "AAPL", "direction": "SELL", "size": 1.94, "level": 103.0,
        "status": "OPEN"})
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, daily_loss_limit_eur=100.0, dry_run=False)
    await ex.try_enter(_strat(), _ctx(), "2026-06-12")
    client.create_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_guard_is_stateless_day_rolls(tmp_path):
    """Yesterday's blowout must NOT block today (no persistent _halted flag)."""
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    led = ForwardLedger(tmp_path / "g3.db")
    _seed_closed(led, "2026-06-11", -500.0, 1)
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D2", "dealReference": "R2", "dealStatus": "ACCEPTED",
        "epic": "AAPL", "direction": "SELL", "size": 1.94, "level": 103.0,
        "status": "OPEN"})
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, daily_loss_limit_eur=100.0, dry_run=False)
    await ex.try_enter(_strat(), _ctx(), "2026-06-12")
    client.create_position.assert_awaited_once()


def test_halted_field_removed(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    ex = ExperimentExecutor(client=None, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "g4.db"))
    assert not hasattr(ex, "_halted")
