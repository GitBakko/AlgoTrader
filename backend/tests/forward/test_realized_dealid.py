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
