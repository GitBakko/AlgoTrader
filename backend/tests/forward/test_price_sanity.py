"""Entry price-sanity gate — reject an order when the broker entry price deviates
implausibly from an INDEPENDENT reference (yfinance daily close). Catches gross
broker price-feed anomalies (e.g. KLAC quoted ~9x on 2026-06-09/10 then ~245
from 06-12) that no intra-broker check can see (prev_close/OR/mid are all the
same poisoned feed). Inert by default: fires only when a reference is present."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from src.broker.models import DealConfirmation, Resolution

NOW = datetime(2026, 6, 12, 14, 0, tzinfo=timezone.utc)
SC = datetime(2026, 6, 12, 19, 45, tzinfo=timezone.utc)


def _ctx(prev, open_, cur, ref):
    from forward.strategy import MarketContext
    return MarketContext("AAPL", prev, open_, cur, NOW, SC, reference_price=ref)


def _strat():
    # min_rr=0.0 so the +3% gap always yields a signal — we test the PRICE gate here.
    from forward.strategy import GapFadeStrategy
    return GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015, min_rr=0.0)


def _exec_client():
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.get_market_details.return_value = {
        "dealingRules": {"minStopOrProfitDistance": {"unit": "PERCENTAGE", "value": 0.01}},
        "snapshot": {"bid": 102.9, "offer": 103.1}}
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "SELL", "size": 1.0, "level": 103.0, "status": "OPEN"})
    return client


def _exec(tmp_path, client, name="p.db"):
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    return ExperimentExecutor(client=client, experiment_account_id="EXP",
                              ledger=ForwardLedger(tmp_path / name), dry_run=False)


# --- MarketContext field + executor default -------------------------------

def test_market_context_reference_price_defaults_none():
    from forward.strategy import MarketContext
    ctx = MarketContext("AAPL", 100.0, 103.0, 103.0, NOW, SC)
    assert ctx.reference_price is None


def test_executor_default_max_price_deviation():
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    ex = ExperimentExecutor(client=None, experiment_account_id="EXP",
                            ledger=ForwardLedger(":memory:"))
    assert ex.max_price_deviation == 0.35


# --- the gate -------------------------------------------------------------

@pytest.mark.asyncio
async def test_skips_on_anomalous_entry_price(tmp_path):
    # broker mid 103 vs independent reference 11 -> ~836% deviation -> skip (KLAC-shape)
    client = _exec_client()
    ex = _exec(tmp_path, client, "anom.db")
    res = await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0, ref=11.0), "2026-06-12")
    assert res is None
    client.create_position.assert_not_called()
    assert ex.ledger.list_open() == []


@pytest.mark.asyncio
async def test_enters_when_price_near_reference(tmp_path):
    # broker mid 103 vs reference 103 -> 0% deviation -> normal entry
    client = _exec_client()
    ex = _exec(tmp_path, client, "ok.db")
    await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0, ref=103.0), "2026-06-12")
    client.create_position.assert_awaited_once()
    assert len(ex.ledger.list_open()) == 1


@pytest.mark.asyncio
async def test_inert_when_no_reference(tmp_path):
    # reference_price None -> gate inert (back-compat with the pre-fix entry path)
    client = _exec_client()
    ex = _exec(tmp_path, client, "none.db")
    await ex.try_enter(_strat(), _ctx(100.0, 103.0, 103.0, ref=None), "2026-06-12")
    client.create_position.assert_awaited_once()


@pytest.mark.asyncio
async def test_modest_gap_within_threshold_not_flagged(tmp_path):
    # a real 20% earnings gap (mid 120 vs ref 100) must NOT trip the 35% gate
    client = _exec_client()
    ex = _exec(tmp_path, client, "gap.db")
    await ex.try_enter(_strat(), _ctx(100.0, 120.0, 120.0, ref=100.0), "2026-06-12")
    client.create_position.assert_awaited_once()


# --- scheduler wiring -----------------------------------------------------

def _sched(tmp_path, client, strategies, ref_fetch, name="s.db"):
    from forward.scheduler import ExperimentScheduler
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / name), dry_run=False)
    return ExperimentScheduler(client=client, executor=ex, strategies=strategies,
                               ref_price_fetch=ref_fetch), ex


def _gapfade_client():
    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.get_market_details.return_value = {
        "dealingRules": {"minStopOrProfitDistance": {"unit": "PERCENTAGE", "value": 0.01}},
        "snapshot": {"bid": 102.9, "offer": 103.1}}  # mid 103

    async def hist(epic, resolution, max_candles=10):
        from src.broker.models import OHLCCandle
        if resolution == Resolution.MINUTE_5:
            return [OHLCCandle.model_validate(
                {"snapshotTime": datetime(2026, 6, 12, 13, 30, tzinfo=timezone.utc),
                 "snapshotTimeUTC": datetime(2026, 6, 12, 13, 30, tzinfo=timezone.utc),
                 "openPrice": 103.0, "highPrice": 104.0, "lowPrice": 102.0, "closePrice": 103.0})]
        return []
    client.get_historical_prices.side_effect = hist
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "DG", "dealReference": "RG", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "SELL", "size": 1.9, "level": 103.0, "status": "OPEN"})
    return client


_IN_WINDOW = datetime(2026, 6, 12, 13, 35, tzinfo=timezone.utc)  # Fri 09:35 ET, in entry window


@pytest.mark.asyncio
async def test_entry_pass_threads_reference_into_ctx(tmp_path, monkeypatch):
    from forward.strategy import GapFadeStrategy
    client = _gapfade_client()
    sched, ex = _sched(tmp_path, client, [GapFadeStrategy(epics=["AAPL"], min_rr=0.0)],
                       ref_fetch=lambda epic: 103.0)
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=100.0))  # +3% gap
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=_IN_WINDOW)
    ex.try_enter.assert_awaited_once()
    ctx = ex.try_enter.await_args.args[1]
    assert ctx.reference_price == 103.0


@pytest.mark.asyncio
async def test_entry_pass_reference_none_without_fetcher(tmp_path, monkeypatch):
    from forward.strategy import GapFadeStrategy
    client = _gapfade_client()
    sched, ex = _sched(tmp_path, client, [GapFadeStrategy(epics=["AAPL"], min_rr=0.0)],
                       ref_fetch=None, name="s2.db")
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=100.0))
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=_IN_WINDOW)
    ctx = ex.try_enter.await_args.args[1]
    assert ctx.reference_price is None


@pytest.mark.asyncio
async def test_entry_pass_end_to_end_skips_anomaly(tmp_path, monkeypatch):
    """Full chain: an independent reference far from the broker mid blocks the order."""
    from forward.strategy import GapFadeStrategy
    client = _gapfade_client()
    sched, ex = _sched(tmp_path, client, [GapFadeStrategy(epics=["AAPL"], min_rr=0.0)],
                       ref_fetch=lambda epic: 11.0, name="s3.db")  # ref 11 vs mid 103 -> skip
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=100.0))
    await sched.entry_pass(now=_IN_WINDOW)
    client.create_position.assert_not_called()
    assert ex.ledger.list_open() == []


@pytest.mark.asyncio
async def test_reference_price_cached_per_day(tmp_path, monkeypatch):
    from forward.strategy import GapFadeStrategy
    client = _gapfade_client()
    calls = {"n": 0}

    def fetch(epic):
        calls["n"] += 1
        return 103.0

    sched, ex = _sched(tmp_path, client, [GapFadeStrategy(epics=["AAPL"], min_rr=0.0)],
                       ref_fetch=fetch, name="s4.db")
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=100.0))
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=_IN_WINDOW)
    await sched.entry_pass(now=_IN_WINDOW + __import__("datetime").timedelta(minutes=5))
    assert calls["n"] == 1  # fetched once for AAPL this session, then cached
