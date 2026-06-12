import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_pacing_sleep_precedes_every_per_epic_broker_get(tmp_path, monkeypatch):
    """Cold-cache gap-fade pass fires 3 GETs (_prev_close DAY, _mid, _session_open_price M5).
    A pacing sleep must come BEFORE each of them (pre-call), not only after _mid."""
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import OHLCCandle, Resolution

    events: list[str] = []

    async def fake_sleep(_s):
        events.append("SLEEP")

    monkeypatch.setattr("forward.scheduler.asyncio.sleep", fake_sleep)

    def _day(d, close):
        return OHLCCandle.model_validate(
            {"snapshotTime": d, "openPrice": close, "highPrice": close,
             "lowPrice": close, "closePrice": close})

    async def fake_hist(epic, resolution, max_candles=10):
        events.append("GET")
        if resolution == Resolution.DAY:
            return [_day(datetime(2026, 6, 11, 2, tzinfo=timezone.utc), 100.0)]
        return []  # M5: no bar yet (irrelevant for pacing assertion)

    async def fake_details(epic):
        events.append("GET")
        return {"snapshot": {"bid": 100.0, "offer": 100.2}}

    client = AsyncMock()
    client.get_historical_prices.side_effect = fake_hist
    client.get_market_details.side_effect = fake_details
    client.get_active_account_id.return_value = "EXP"

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "pace.db"), dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AMD"])],
                                scan_pacing_s=0.2)
    # Friday 2026-06-12 14:30 UTC = 10:30 ET (in window)
    await sched.entry_pass(now=datetime(2026, 6, 12, 14, 30, tzinfo=timezone.utc))

    gets = events.count("GET")
    assert gets == 3, f"expected 3 broker GETs cold-cache, got {gets}: {events}"
    # every GET must be immediately preceded by a SLEEP
    for i, e in enumerate(events):
        if e == "GET":
            assert i > 0 and events[i - 1] == "SLEEP", f"GET at {i} not paced: {events}"


@pytest.mark.asyncio
async def test_pacing_zero_means_no_sleep(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    slept = []

    async def fake_sleep(_s):
        slept.append(_s)

    monkeypatch.setattr("forward.scheduler.asyncio.sleep", fake_sleep)
    client = AsyncMock()
    client.get_historical_prices.return_value = []
    client.get_market_details.return_value = {"snapshot": {"bid": 1.0, "offer": 1.0}}
    client.get_active_account_id.return_value = "EXP"
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "z.db"), dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AMD"])],
                                scan_pacing_s=0.0)
    await sched.entry_pass(now=datetime(2026, 6, 12, 14, 30, tzinfo=timezone.utc))
    assert slept == []
