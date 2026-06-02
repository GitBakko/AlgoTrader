import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_on_session_open_enters_on_gap(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP123"
    client.get_market_details.return_value = {"snapshot": {"bid": 102.9, "offer": 103.1}}
    from src.broker.models import DealConfirmation
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "SELL", "size": 1.94, "level": 103.0, "status": "OPEN"})

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "s.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategy=GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01))
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=100.0))
    now = datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc)
    await sched.on_session_open(now=now)
    client.create_position.assert_awaited_once()
    assert len(ex.ledger.list_open()) == 1
