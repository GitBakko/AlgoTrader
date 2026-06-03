import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


def _txn(deal_id, size, epic="AAPL"):
    from src.broker.models import Transaction
    return Transaction(date=datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc),
                       reference=f"r-{deal_id}", dealId=deal_id, transactionType="TRADE",
                       instrumentName=epic, size=size, currency="USD")


@pytest.mark.asyncio
async def test_realized_picks_txn_by_dealid(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    # two TRADE rows, same epic, different dealId (H2 short vs H3 long on AAPL same day)
    client.get_transaction_history.return_value = [_txn("DH2", "3.00"), _txn("DH3", "-5.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "r.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DH3"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == -5.00 and reason == "BROKER_TRADE"


@pytest.mark.asyncio
async def test_realized_unmatched_dealid_is_pending(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DOTHER", "3.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "r2.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DMINE"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == 0.0 and reason == "PENDING_RECONCILE"


def _activity(deal_id, open_price, epic="AAPL", source="SL"):
    from src.broker.models import ActivityEvent
    return ActivityEvent.model_validate({
        "date": "2026-06-03T16:00:00", "epic": epic, "source": source,
        "type": "POSITION", "status": "ACCEPTED", "dealId": deal_id,
        "details": {"openPrice": open_price, "direction": "SELL"}})


@pytest.mark.asyncio
async def test_realized_tier2_links_rotated_dealid_via_activity(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    # our position dealId = "DPOS"; broker SL close rotated the TRADE dealId to "DPOS1"
    client.get_transaction_history.return_value = [_txn("DPOS1", "-7.50")]
    client.get_activity_history.return_value = [_activity("DPOS1", open_price=103.0)]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "t2.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DPOS", "entry": 103.0,
           "opened_at": "2026-06-03T14:30:00+00:00", "direction": "BUY"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == -7.50 and reason == "BROKER_ACTIVITY"


@pytest.mark.asyncio
async def test_realized_tier1_skips_activity_call(tmp_path):
    # exact dealId match (our DELETE close) must NOT need an activity call
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DSAME", "4.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "t1.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DSAME", "entry": 100.0,
           "opened_at": "2026-06-03T14:00:00+00:00", "direction": "SELL"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == 4.00 and reason == "BROKER_TRADE"
    client.get_activity_history.assert_not_called()


@pytest.mark.asyncio
async def test_realized_no_match_anywhere_is_pending(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("OTHER", "1.00")]
    client.get_activity_history.return_value = []   # nothing to link
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "t3.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "MINE", "entry": 103.0,
           "opened_at": "2026-06-03T14:30:00+00:00", "direction": "BUY"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == 0.0 and reason == "PENDING_RECONCILE"
