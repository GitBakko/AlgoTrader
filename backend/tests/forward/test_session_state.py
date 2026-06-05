import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone, date
from unittest.mock import AsyncMock


def test_session_state_resets_on_new_day():
    from forward.scheduler import SessionState
    st = SessionState()
    st.ensure_day(date(2026, 6, 3))
    st.open_px["AAPL"] = 100.0
    st.ensure_day(date(2026, 6, 3))           # same day -> keep
    assert st.open_px.get("AAPL") == 100.0
    st.ensure_day(date(2026, 6, 4))           # new day -> reset
    assert st.open_px == {} and st.eligible == set()


@pytest.mark.asyncio
async def test_opening_range_from_minute5_bars():
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import OHLCCandle
    import pathlib, tempfile

    def _c(ts, hi, lo):
        return OHLCCandle.model_validate(
            {"snapshotTime": ts, "openPrice": (hi + lo) / 2, "highPrice": hi,
             "lowPrice": lo, "closePrice": (hi + lo) / 2})

    client = AsyncMock()
    client.get_historical_prices.return_value = [
        _c(datetime(2026, 6, 3, 13, 30, tzinfo=timezone.utc), 101.0, 99.0),
        _c(datetime(2026, 6, 3, 13, 35, tzinfo=timezone.utc), 102.0, 100.0),
        _c(datetime(2026, 6, 3, 13, 55, tzinfo=timezone.utc), 101.5, 98.5),
    ]
    tmp = pathlib.Path(tempfile.mkdtemp()) / "o.db"
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp), dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    now = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    hi, lo = await sched._opening_range("AAPL", now)
    assert hi == 102.0 and lo == 98.5


@pytest.mark.asyncio
async def test_opening_range_winter_est():
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import OHLCCandle
    import pathlib, tempfile

    def _c(ts, hi, lo):
        return OHLCCandle.model_validate(
            {"snapshotTime": ts, "openPrice": (hi + lo) / 2, "highPrice": hi,
             "lowPrice": lo, "closePrice": (hi + lo) / 2})

    client = AsyncMock()
    # Jan (EST): US open 09:30 ET = 14:30 UTC. OR window 14:30-15:00 UTC.
    client.get_historical_prices.return_value = [
        _c(datetime(2026, 1, 7, 13, 30, tzinfo=timezone.utc), 999.0, 998.0),  # 08:30 EST pre-mkt -> excluded
        _c(datetime(2026, 1, 7, 14, 30, tzinfo=timezone.utc), 101.0, 99.0),
        _c(datetime(2026, 1, 7, 14, 55, tzinfo=timezone.utc), 102.0, 98.5),
    ]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(pathlib.Path(tempfile.mkdtemp()) / "win.db"), dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    now = datetime(2026, 1, 7, 15, 0, tzinfo=timezone.utc)   # after winter OR window
    hi, lo = await sched._opening_range("AAPL", now)
    assert hi == 102.0 and lo == 98.5    # pre-market 999/998 excluded


@pytest.mark.asyncio
async def test_opening_range_uses_snapshot_time_utc_not_server_local():
    """Regression — live broker bars carry snapshotTime in SERVER-LOCAL time
    (UTC+2 in summer) and snapshotTimeUTC in true UTC. Filtering the OR window
    on snapshotTime shifted every bar +2h out of [13:30,14:00) UTC, so
    _opening_range returned None on every pass and ORB never armed (3 days
    N=0 live, missed AVGO breakout 2026-06-05)."""
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import OHLCCandle
    import pathlib, tempfile

    def _c(local, utc, hi, lo):
        return OHLCCandle.model_validate(
            {"snapshotTime": local, "snapshotTimeUTC": utc,
             "openPrice": (hi + lo) / 2, "highPrice": hi,
             "lowPrice": lo, "closePrice": (hi + lo) / 2})

    client = AsyncMock()
    # exact live shape: naive strings, snapshotTime = UTC+2 (CEST server)
    client.get_historical_prices.return_value = [
        _c("2026-06-05T15:25:00", "2026-06-05T13:25:00", 999.0, 998.0),  # pre-open -> excluded
        _c("2026-06-05T15:30:00", "2026-06-05T13:30:00", 101.0, 99.0),
        _c("2026-06-05T15:55:00", "2026-06-05T13:55:00", 102.0, 98.5),
        _c("2026-06-05T16:00:00", "2026-06-05T14:00:00", 103.0, 97.0),   # post-OR -> excluded
    ]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(pathlib.Path(tempfile.mkdtemp()) / "utc.db"),
                            dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AVGO"])])
    now = datetime(2026, 6, 5, 14, 5, tzinfo=timezone.utc)
    rng = await sched._opening_range("AVGO", now)
    assert rng is not None, "OR must form from snapshotTimeUTC despite local snapshotTime"
    hi, lo = rng
    assert hi == 102.0 and lo == 98.5


def test_in_window_guards_weekday_and_hours():
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    import pathlib, tempfile
    from unittest.mock import AsyncMock as AM
    tmp = pathlib.Path(tempfile.mkdtemp()) / "w.db"
    ex = ExperimentExecutor(client=AM(), experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp), dry_run=True)
    sched = ExperimentScheduler(client=AM(), executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    wed = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)        # Wed in-window
    assert sched._in_window(wed) is True
    assert sched._in_window(wed.replace(hour=12)) is False        # before 13:30
    assert sched._in_window(wed.replace(hour=17)) is False        # after 16:00
    assert sched._in_window(wed.replace(hour=16, minute=0)) is False   # 16:00 exclusive end
    assert sched._in_window(wed.replace(hour=13, minute=30)) is True    # 13:30 inclusive start
    sat = datetime(2026, 6, 6, 14, 0, tzinfo=timezone.utc)        # Saturday
    assert sched._in_window(sat) is False


@pytest.mark.asyncio
async def test_entry_pass_orb_enters_only_eligible_on_breakout(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import DealConfirmation

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    # live mid 105 (breakout above OR high 102)
    client.get_market_details.return_value = {"snapshot": {"bid": 104.9, "offer": 105.1}}
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "D1", "dealReference": "R1", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "BUY", "size": 1.9, "level": 105.0, "status": "OPEN"})

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "ep.db"), dry_run=False)

    class _Screener:
        def select(self, symbols, now):
            return {"rvol": {"AAPL": 3.0}, "eligible": {"AAPL"}}

    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"], rvol_min=1.5)],
                                screener=_Screener())
    monkeypatch.setattr(sched, "_opening_range", AsyncMock(return_value=(102.0, 100.0)))
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=101.0))
    now = datetime(2026, 6, 3, 14, 5, tzinfo=timezone.utc)   # after OR window (13:30+30)
    await sched.entry_pass(now=now)
    client.create_position.assert_awaited_once()
    assert ex.ledger.realized("orb") == [] and len(ex.ledger.list_open()) == 1


def test_in_window_dst_summer_vs_winter():
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    import pathlib, tempfile
    from unittest.mock import AsyncMock
    from datetime import datetime, timezone
    ex = ExperimentExecutor(client=AsyncMock(), experiment_account_id="EXP",
                            ledger=ForwardLedger(pathlib.Path(tempfile.mkdtemp()) / "d.db"), dry_run=True)
    sched = ExperimentScheduler(client=AsyncMock(), executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    # Summer (EDT): open 13:30 UTC. 13:45 UTC is in-window; 13:15 UTC is before open.
    jun = datetime(2026, 6, 3, 13, 45, tzinfo=timezone.utc)   # Wed, EDT, after 13:30 open
    assert sched._in_window(jun) is True
    assert sched._in_window(jun.replace(hour=13, minute=15)) is False   # before 13:30 EDT open
    # Winter (EST): open is 14:30 UTC. 13:45 UTC is BEFORE the open -> out; 14:45 UTC is in.
    jan = datetime(2026, 1, 7, 13, 45, tzinfo=timezone.utc)   # Wed, EST
    assert sched._in_window(jan) is False                      # 13:45 < 14:30 EST open
    assert sched._in_window(jan.replace(hour=14, minute=45)) is True


def test_session_close_dst_aware():
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    import pathlib, tempfile
    from unittest.mock import AsyncMock
    from datetime import datetime, timezone
    ex = ExperimentExecutor(client=AsyncMock(), experiment_account_id="EXP",
                            ledger=ForwardLedger(pathlib.Path(tempfile.mkdtemp()) / "d2.db"), dry_run=True)
    sched = ExperimentScheduler(client=AsyncMock(), executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    jun = sched._session_close(datetime(2026, 6, 3, 18, 0, tzinfo=timezone.utc))
    assert jun.hour == 20 and jun.minute == 45                 # 16:45 EDT = 20:45 UTC
    jan = sched._session_close(datetime(2026, 1, 7, 18, 0, tzinfo=timezone.utc))
    assert jan.hour == 21 and jan.minute == 45                 # 16:45 EST = 21:45 UTC


@pytest.mark.asyncio
async def test_entry_pass_gapfade_enters_on_gap(tmp_path, monkeypatch):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import DealConfirmation

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.get_market_details.return_value = {"snapshot": {"bid": 102.9, "offer": 103.1}}  # mid 103
    client.create_position.return_value = DealConfirmation.model_validate({
        "dealId": "DG", "dealReference": "RG", "dealStatus": "ACCEPTED", "epic": "AAPL",
        "direction": "SELL", "size": 1.9, "level": 103.0, "status": "OPEN"})
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "g.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01)])
    monkeypatch.setattr(sched, "_prev_close", AsyncMock(return_value=100.0))  # +3% gap -> short
    now = datetime(2026, 6, 3, 13, 35, tzinfo=timezone.utc)   # in window
    await sched.entry_pass(now=now)
    client.create_position.assert_awaited_once()
    assert len(ex.ledger.list_open()) == 1
