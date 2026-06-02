import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from src.broker.models import Direction, DealConfirmation


def _ctx(prev, open_, cur):
    from forward.strategy import MarketContext
    return MarketContext("AAPL", prev, open_, cur,
                         datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc),
                         datetime(2026, 6, 2, 20, 45, tzinfo=timezone.utc))


def _strat():
    from forward.strategy import GapFadeStrategy
    return GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015)


@pytest.mark.asyncio
async def test_dry_run_does_not_place_order(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    client = AsyncMock()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "d.db"),
                            notional_usd=200.0, dry_run=True)
    sig = await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0), "2026-06-02")
    assert sig is not None and sig.direction == Direction.SELL
    client.create_position.assert_not_called()
    assert ex.ledger.list_open() == []


@pytest.mark.asyncio
async def test_live_places_order_when_isolated(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP123"
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED",
        "epic": "AAPL", "direction": "SELL", "size": 1.94, "level": 103.0,
        "status": "OPEN"})
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "l.db"),
                            notional_usd=200.0, dry_run=False)
    await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0), "2026-06-02")
    client.create_position.assert_awaited_once()
    req = client.create_position.call_args.args[0]
    assert req.epic == "AAPL" and req.direction == Direction.SELL
    assert req.size == round(200.0 / 103.0, 4) and req.stop_level > 103.0
    assert len(ex.ledger.list_open()) == 1


@pytest.mark.asyncio
async def test_live_refuses_when_wrong_account(tmp_path):
    from forward.executor import ExperimentExecutor, IsolationError
    from forward.ledger import ForwardLedger
    client = AsyncMock()
    client.get_active_account_id.return_value = "SOAK999"
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "x.db"), dry_run=False)
    with pytest.raises(IsolationError):
        await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0), "2026-06-02")
    client.create_position.assert_not_called()
