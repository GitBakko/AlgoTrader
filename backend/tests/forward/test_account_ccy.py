import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


def _txn(deal_id, size, currency="EUR"):
    from src.broker.models import Transaction
    return Transaction(
        date=datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc),
        reference=f"r-{deal_id}", dealId=deal_id, transactionType="TRADE",
        instrumentName="AAPL", size=size, currency=currency)


@pytest.mark.asyncio
async def test_realized_passes_account_ccy_to_pl_value_in(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker import models as broker_models

    seen = []
    orig = broker_models.Transaction.pl_value_in

    def spy(self, account_currency):
        seen.append(account_currency)
        return orig(self, account_currency)

    monkeypatch.setattr(broker_models.Transaction, "pl_value_in", spy)
    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("D1", "3.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "c.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "D1"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert reason == "BROKER_TRADE" and net == 3.00
    assert seen == ["EUR"]  # executor default account_ccy, not hardcoded "USD"


def test_executor_default_account_ccy_is_eur(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    ex = ExperimentExecutor(client=None, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "d.db"))
    assert ex.account_ccy == "EUR"
