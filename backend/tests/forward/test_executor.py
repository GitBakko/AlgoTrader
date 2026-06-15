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


# ---------------------------------------------------------------------------
# Task 5 — size on current_price + idempotent entry guard
# ---------------------------------------------------------------------------

def _orb_ctx(today_open, current):
    from forward.strategy import MarketContext
    now = datetime(2026, 6, 3, 14, 30, tzinfo=timezone.utc)
    sc = datetime(2026, 6, 3, 20, 45, tzinfo=timezone.utc)
    return MarketContext("AAPL", 100.0, today_open, current, now, sc,
                         or_high=199.0, or_low=190.0, rvol=2.0)


def _orb_client():
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D9", "dealReference": "R9", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "BUY", "size": 1.0, "level": 200.0, "status": "OPEN"})
    return client


@pytest.mark.asyncio
async def test_size_uses_current_price_not_today_open(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from forward.strategy import ORBStrategy

    client = _orb_client()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "e.db"),
                            notional_usd=200.0, dry_run=False)
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    # today_open 100 (stale), current_price 200 (breakout) -> size 200/200 = 1.0, not 2.0
    await ex.try_enter(s, _orb_ctx(100.0, 200.0), "2026-06-03")
    assert client.create_position.call_args.args[0].size == 1.0


# ---------------------------------------------------------------------------
# Broker stop-side validation — gap-up that keeps running leaves a fade-short
# stop BELOW spot (wrong side); the broker rejects it. We skip, never crash.
# ---------------------------------------------------------------------------

def _rules_client(level=103.0, min_pct=0.01):
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.get_market_details.return_value = {
        "dealingRules": {"minStopOrProfitDistance": {"unit": "PERCENTAGE", "value": min_pct}}}
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "SELL", "size": 1.0, "level": level, "status": "OPEN"})
    return client


@pytest.mark.asyncio
async def test_skips_when_sell_stop_below_spot(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    client = _rules_client()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "w.db"),
                            notional_usd=200.0, dry_run=False)
    # gap +3% -> SELL stop ~104.5, but price ran to 110 -> stop is below spot -> wrong side
    res = await ex.try_enter(_strat(), _ctx(100.0, 103.0, 110.0), "2026-06-02")
    assert res is None
    client.create_position.assert_not_called()
    assert ex.ledger.list_open() == []


@pytest.mark.asyncio
async def test_sends_and_records_clamped_stop_when_correct_side(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    client = _rules_client(level=103.0)
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "ok.db"),
                            notional_usd=200.0, dry_run=False)
    await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0), "2026-06-02")  # stop ~104.5 > spot
    client.create_position.assert_awaited_once()
    req = client.create_position.call_args.args[0]
    assert req.stop_level > 103.0
    # ledger persists the stop ACTUALLY sent (not the raw signal stop)
    assert ex.ledger.list_open()[0]["stop_level"] == req.stop_level


@pytest.mark.asyncio
async def test_try_enter_idempotent_no_double_order(tmp_path):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from forward.strategy import ORBStrategy

    client = _orb_client()
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "i.db"),
                            notional_usd=200.0, dry_run=False)
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    await ex.try_enter(s, _orb_ctx(200.0, 200.0), "2026-06-03")   # 1st: orders + records
    await ex.try_enter(s, _orb_ctx(200.0, 200.0), "2026-06-03")   # 2nd: guard skips
    assert client.create_position.await_count == 1
    assert len(ex.ledger.list_open()) == 1
