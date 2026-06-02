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


@pytest.mark.asyncio
async def test_mark_pass_closes_and_reconciles(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Transaction

    client = AsyncMock()
    client.get_market_details.return_value = {"snapshot": {"bid": 101.4, "offer": 101.6}}
    client.list_positions.return_value = []  # broker already closed the position
    client.get_transaction_history.return_value = [
        Transaction(date=datetime(2026, 6, 2, 16, 0, tzinfo=timezone.utc), reference="r1",
                    transactionType="TRADE", instrumentName="AAPL", size="2.91", currency="USD")]

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "m.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-02",
                          deal_id="D1", direction="SELL", entry=103.0, size=1.94,
                          stop_level=105.0, rationale="x", opened_at="2026-06-02T14:00:00+00:00")
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategy=GapFadeStrategy(epics=["AAPL"]))
    await sched.mark_pass(now=datetime(2026, 6, 2, 16, 0, tzinfo=timezone.utc))
    rz = ex.ledger.realized("gap_fade")
    assert len(rz) == 1
    assert rz[0]["net_pnl"] == 2.91
    assert rz[0]["close_reason"] == "BROKER_TRADE"
