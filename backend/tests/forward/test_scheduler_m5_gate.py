import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock


def _mk(tmp_path, client, strategies, name="g.db"):
    from forward.scheduler import ExperimentScheduler
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / name), dry_run=True)
    return ExperimentScheduler(client=client, executor=ex, strategies=strategies), ex


def _day_candle(close):
    from src.broker.models import OHLCCandle
    return OHLCCandle.model_validate(
        {"snapshotTime": datetime(2026, 6, 11, 2, tzinfo=timezone.utc),
         "openPrice": close, "highPrice": close, "lowPrice": close, "closePrice": close})


def _m5_candle(ts_utc, open_):
    # NOTE: verify the UTC alias on OHLCCandle in src/broker/models.py
    # (expected "snapshotTimeUTC"); scheduler filters on timestamp_utc.
    from src.broker.models import OHLCCandle
    return OHLCCandle.model_validate(
        {"snapshotTime": ts_utc, "snapshotTimeUTC": ts_utc,
         "openPrice": open_, "highPrice": open_ + 0.5,
         "lowPrice": open_ - 0.5, "closePrice": open_ + 0.1})


NOW = datetime(2026, 6, 12, 14, 30, tzinfo=timezone.utc)  # Fri 10:30 ET
OPEN_BAR_TS = datetime(2026, 6, 12, 13, 30, tzinfo=timezone.utc)  # 09:30 ET


@pytest.mark.asyncio
async def test_gap_fade_skips_pass_when_m5_open_bar_missing(tmp_path):
    from forward.strategy import GapFadeStrategy
    from src.broker.models import Resolution

    async def hist(epic, resolution, max_candles=10):
        if resolution == Resolution.DAY:
            return [_day_candle(100.0)]
        return []  # no M5 bar yet

    client = AsyncMock()
    client.get_historical_prices.side_effect = hist
    client.get_market_details.return_value = {"snapshot": {"bid": 102.9, "offer": 103.1}}
    client.get_active_account_id.return_value = "EXP"
    sched, ex = _mk(tmp_path, client, [GapFadeStrategy(epics=["AMD"])])
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=NOW)
    ex.try_enter.assert_not_awaited()  # gated: no entry on mid-fallback gap


@pytest.mark.asyncio
async def test_gap_fade_enters_with_true_m5_open_when_bar_present(tmp_path):
    from forward.strategy import GapFadeStrategy
    from src.broker.models import Resolution

    async def hist(epic, resolution, max_candles=10):
        if resolution == Resolution.DAY:
            return [_day_candle(100.0)]
        return [_m5_candle(OPEN_BAR_TS, 103.0)]

    client = AsyncMock()
    client.get_historical_prices.side_effect = hist
    client.get_market_details.return_value = {"snapshot": {"bid": 102.9, "offer": 103.1}}
    client.get_active_account_id.return_value = "EXP"
    sched, ex = _mk(tmp_path, client, [GapFadeStrategy(epics=["AMD"])], "g2.db")
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=NOW)
    ex.try_enter.assert_awaited_once()
    ctx = ex.try_enter.await_args.args[1]
    assert ctx.today_open == 103.0  # true M5 open, not mid


@pytest.mark.asyncio
async def test_orb_not_gated_by_m5_open(tmp_path):
    """ORB (uses_today_open=False) must not be gated: M5 session-open fetch never
    happens for it; eligibility-gated path proceeds on or_levels alone."""
    from forward.strategy import ORBStrategy
    from src.broker.models import Resolution

    async def hist(epic, resolution, max_candles=10):
        # only MINUTE_5 ever requested for ORB (OR window); return bars in OR window
        assert resolution == Resolution.MINUTE_5
        return [_m5_candle(OPEN_BAR_TS, 103.0)]

    client = AsyncMock()
    client.get_historical_prices.side_effect = hist
    client.get_market_details.return_value = {"snapshot": {"bid": 104.9, "offer": 105.1}}
    client.get_active_account_id.return_value = "EXP"
    sched, ex = _mk(tmp_path, client, [ORBStrategy(epics=["AMD"])], "g3.db")
    sched._state.ensure_day(NOW.date())
    sched._state.eligible = {"AMD"}
    sched._state.rvol = {"AMD": 2.0}
    sched._state.screened = True
    ex.try_enter = AsyncMock()
    await sched.entry_pass(now=NOW)
    ex.try_enter.assert_awaited_once()


def test_on_session_open_deleted(tmp_path):
    from forward.scheduler import ExperimentScheduler
    assert not hasattr(ExperimentScheduler, "on_session_open")


@pytest.mark.asyncio
async def test_mark_pass_ctx_today_open_from_ledger_not_entry(tmp_path):
    from forward.strategy import GapFadeStrategy
    from forward.scheduler import ExperimentScheduler
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    seen = {}

    class SpyGapFade(GapFadeStrategy):
        def exit_rule(self, pos, ctx):
            seen["ctx_today_open"] = ctx.today_open
            seen["pos_today_open"] = pos.today_open
            return False

    client = AsyncMock()
    client.list_positions.return_value = []
    client.get_market_details.return_value = {"snapshot": {"bid": 101.9, "offer": 102.1}}
    client.get_active_account_id.return_value = "EXP"
    client.get_transaction_history.return_value = []
    client.get_activity_history.return_value = []
    led = ForwardLedger(tmp_path / "m.db")
    led.record_open(strategy="gap_fade", epic="AMD", session_date="2026-06-12",
                    deal_id="D1", direction="SELL", entry=103.0, size=1.0,
                    stop_level=104.5, rationale="t",
                    opened_at=datetime.now(timezone.utc).isoformat(),
                    prev_close=100.0, today_open=105.0)
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[SpyGapFade(epics=["AMD"])])
    await sched.mark_pass(now=NOW)
    assert seen["pos_today_open"] == 105.0
    assert seen["ctx_today_open"] == 105.0  # was row['entry']=103.0 before fix
