import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock
from src.broker.models import Direction, Transaction


@pytest.mark.asyncio
async def test_ensure_account_switches_when_reverted(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_active_account_id.return_value = "WRONG_DEFAULT"   # reverted after re-auth
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP_ACCT",
                            ledger=ForwardLedger(tmp_path / "ea.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    await sched._ensure_account()
    client.switch_account.assert_awaited_once_with("EXP_ACCT")


@pytest.mark.asyncio
async def test_ensure_account_noop_when_already_active(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP_ACCT"
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP_ACCT",
                            ledger=ForwardLedger(tmp_path / "eb.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    await sched._ensure_account()
    client.switch_account.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_pass_reasserts_account_before_list_positions(tmp_path):
    # mark_pass must re-assert the experiment account (session reverts on re-auth) BEFORE reading positions
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_active_account_id.return_value = "WRONG_DEFAULT"   # reverted
    client.get_market_details.return_value = {"snapshot": {"bid": 100.0, "offer": 100.0}}
    client.list_positions.return_value = []
    client.get_transaction_history.return_value = []
    client.get_activity_history.return_value = []
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP_ACCT",
                            ledger=ForwardLedger(tmp_path / "mp.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-03",
                          deal_id="D1", direction="SELL", entry=100.0, size=1.0,
                          stop_level=102.0, rationale="x", opened_at="2026-06-03T14:00:00+00:00",
                          prev_close=98.0, today_open=100.0)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    await sched.mark_pass(now=datetime(2026, 6, 3, 17, 0, tzinfo=timezone.utc))
    client.switch_account.assert_awaited_with("EXP_ACCT")   # re-asserted before reading positions


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
                    dealId="D1", transactionType="TRADE", instrumentName="AAPL",
                    size="2.91", currency="USD")]

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP123",
                            ledger=ForwardLedger(tmp_path / "m.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-02",
                          deal_id="D1", direction="SELL", entry=103.0, size=1.94,
                          stop_level=105.0, rationale="x", opened_at="2026-06-02T14:00:00+00:00")
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    await sched.mark_pass(now=datetime(2026, 6, 2, 16, 0, tzinfo=timezone.utc))
    rz = ex.ledger.realized("gap_fade")
    assert len(rz) == 1
    assert rz[0]["net_pnl"] == 2.91
    assert rz[0]["close_reason"] == "BROKER_TRADE"


@pytest.mark.asyncio
async def test_prev_close_from_broker_last_completed(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import OHLCCandle

    def _c(d, close):
        return OHLCCandle.model_validate(
            {"snapshotTime": d, "openPrice": close, "highPrice": close,
             "lowPrice": close, "closePrice": close})

    client = AsyncMock()
    now = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    # ascending; last candle is "today" (still forming) -> prev_close = prior day 98.0
    client.get_historical_prices.return_value = [
        _c(datetime(2026, 6, 1, 2, tzinfo=timezone.utc), 92.0),
        _c(datetime(2026, 6, 2, 2, tzinfo=timezone.utc), 98.0),
        _c(datetime(2026, 6, 3, 2, tzinfo=timezone.utc), 100.0),
    ]
    ex = ExperimentExecutor(client=client, experiment_account_id="X",
                            ledger=ForwardLedger(tmp_path / "p.db"), dry_run=True)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AMD"])])
    assert await sched._prev_close("AMD", now) == 98.0
    client.get_historical_prices.return_value = []
    assert await sched._prev_close("AMD", now) is None


@pytest.mark.asyncio
async def test_mark_pass_dispatches_exit_rule_by_owning_strategy(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy, ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Transaction

    client = AsyncMock()
    client.get_market_details.return_value = {"snapshot": {"bid": 101.0, "offer": 101.0}}
    client.list_positions.return_value = []          # both broker-closed -> realize both
    client.get_transaction_history.return_value = [
        Transaction(date=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc), reference="rg",
                    dealId="DG", transactionType="TRADE", instrumentName="AAPL",
                    size="1.50", currency="USD"),
        Transaction(date=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc), reference="ro",
                    dealId="DO", transactionType="TRADE", instrumentName="NVDA",
                    size="-2.00", currency="USD")]

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "mm.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-03",
                          deal_id="DG", direction="SELL", entry=103.0, size=1.0,
                          stop_level=105.0, rationale="x", opened_at="2026-06-03T14:00:00+00:00")
    ex.ledger.record_open(strategy="orb", epic="NVDA", session_date="2026-06-03",
                          deal_id="DO", direction="BUY", entry=500.0, size=1.0,
                          stop_level=490.0, rationale="y", opened_at="2026-06-03T14:30:00+00:00")
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"]),
                                            ORBStrategy(epics=["NVDA"])])
    # past session_close -> both exit_rules return True (EOD)
    await sched.mark_pass(now=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc))
    assert ex.ledger.realized("gap_fade")[0]["net_pnl"] == 1.50
    assert ex.ledger.realized("orb")[0]["net_pnl"] == -2.00


@pytest.mark.asyncio
async def test_mark_pass_gapfade_50pct_fill_exit(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Transaction

    client = AsyncMock()
    # SELL gap-fade: prev_close=100, today_open=104 (gap +4) -> 50% target = 102.
    # live mid 101.5 (<= 102) -> exit_rule fires the 50%-fill BEFORE EOD.
    client.get_market_details.return_value = {"snapshot": {"bid": 101.4, "offer": 101.6}}
    # stub includes epic/direction/level so the new _match_broker_position can find it
    client.list_positions.return_value = [
        type("P", (), {"deal_id": "DG", "epic": "AAPL",
                       "direction": Direction.SELL, "level": 104.0})()
    ]   # still open at broker
    client.get_transaction_history.return_value = [
        Transaction(date=datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc), reference="rg",
                    dealId="DG", transactionType="TRADE", instrumentName="AAPL",
                    size="2.50", currency="USD")]
    client.close_position.return_value = None

    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "fill.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-03",
                          deal_id="DG", direction="SELL", entry=104.0, size=1.0,
                          stop_level=106.0, rationale="x", opened_at="2026-06-03T14:00:00+00:00",
                          prev_close=100.0, today_open=104.0)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"], fill_fraction=0.5)])
    # mid-session (well before EOD) -> only the 50%-fill arm can close it
    # pass 1: close sent, reconcile DEFERRED -> row still open
    await sched.mark_pass(now=datetime(2026, 6, 3, 17, 0, tzinfo=timezone.utc))
    client.close_position.assert_awaited_once_with("DG")
    assert len(ex.ledger.list_open()) == 1                    # deferred, not finalized yet
    # pass 2: broker confirms gone + TRADE history posted -> finalize with real P&L
    client.list_positions.return_value = []
    await sched.mark_pass(now=datetime(2026, 6, 3, 17, 15, tzinfo=timezone.utc))
    assert ex.ledger.realized("gap_fade")[0]["net_pnl"] == 2.50


@pytest.mark.asyncio
async def test_mark_pass_still_open_via_epic_dir_level_not_dealid(tmp_path):
    # broker rotated the open-position dealId (+1) vs what we stored -> exact dealId match
    # would FALSE-close it. Matcher must keep it OPEN via epic+direction+level, and NOT realize it.
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    class _P:
        def __init__(self, epic, direction, level, deal_id):
            self.epic = epic; self.direction = direction; self.level = level; self.deal_id = deal_id

    client = AsyncMock()
    client.get_market_details.return_value = {"snapshot": {"bid": 219.0, "offer": 219.1}}
    # broker position dealId ends ...095a; ledger stored ...0959 (rotated)
    client.list_positions.return_value = [_P("NVDA", Direction.BUY, 219.29,
                                             "00396101-0055-311e-0000-000080c8095a")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "rot.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="NVDA", session_date="2026-06-03",
                          deal_id="00396101-0055-311e-0000-000080c80959", direction="BUY",
                          entry=219.29, size=0.9, stop_level=215.94, rationale="gap fade long",
                          opened_at="2026-06-03T13:36:00+00:00", prev_close=221.79, today_open=219.23)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["NVDA"], fill_fraction=0.5)])
    # mid-session (well before EOD), price not at target -> should NOT exit, must stay OPEN
    await sched.mark_pass(now=datetime(2026, 6, 3, 17, 0, tzinfo=timezone.utc))
    client.close_position.assert_not_awaited()
    assert ex.ledger.realized("gap_fade") == []          # NOT falsely closed
    assert len(ex.ledger.list_open()) == 1               # still open


@pytest.mark.asyncio
async def test_mark_pass_eod_closes_using_broker_dealid(tmp_path):
    # at EOD the matched broker position must be closed using the BROKER's (rotated) dealId
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Transaction, ActivityEvent

    class _P:
        def __init__(self, epic, direction, level, deal_id):
            self.epic = epic; self.direction = direction; self.level = level; self.deal_id = deal_id

    client = AsyncMock()
    client.get_market_details.return_value = {"snapshot": {"bid": 219.0, "offer": 219.1}}
    client.list_positions.return_value = [_P("NVDA", Direction.BUY, 219.29,
                                             "00396101-0055-311e-0000-000080c8095a")]
    # realized P&L via Tier-2 activity linkage (rotated dealId on close TRADE)
    client.get_transaction_history.return_value = [
        Transaction(date=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc), reference="r",
                    dealId="00396101-0055-311e-0000-000080c8095a", transactionType="TRADE",
                    instrumentName="NVDA", size="3.10", currency="USD")]
    client.get_activity_history.return_value = [ActivityEvent.model_validate({
        "date": "2026-06-03T21:00:00", "epic": "NVDA", "source": "USER", "type": "POSITION",
        "status": "ACCEPTED", "dealId": "00396101-0055-311e-0000-000080c8095a",
        "details": {"openPrice": 219.29, "direction": "SELL"}})]
    client.close_position.return_value = None
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "eod.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="NVDA", session_date="2026-06-03",
                          deal_id="00396101-0055-311e-0000-000080c80959", direction="BUY",
                          entry=219.29, size=0.9, stop_level=215.94, rationale="x",
                          opened_at="2026-06-03T13:36:00+00:00", prev_close=221.79, today_open=219.23)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["NVDA"])])
    # 21:00 UTC is past EOD (16:45 ET = 20:45 UTC summer) -> exit_rule True -> close deferred
    await sched.mark_pass(now=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc))
    client.close_position.assert_awaited_once_with("00396101-0055-311e-0000-000080c8095a")  # broker id
    # pass 1: close sent, reconcile DEFERRED (position still in ledger as open)
    assert len(ex.ledger.list_open()) == 1
    # pass 2: broker confirms gone + TRADE history posted -> finalize
    client.list_positions.return_value = []
    await sched.mark_pass(now=datetime(2026, 6, 3, 21, 15, tzinfo=timezone.utc))
    rz = ex.ledger.realized("gap_fade")
    assert len(rz) == 1 and rz[0]["net_pnl"] == 3.10


@pytest.mark.asyncio
async def test_mark_pass_our_close_defers_reconcile(tmp_path):
    # when mark_pass itself closes (EOD/fill), it must NOT reconcile in the same pass
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Direction

    class _P:
        def __init__(self, epic, direction, level, deal_id):
            self.epic = epic; self.direction = direction; self.level = level; self.deal_id = deal_id

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.get_market_details.return_value = {"snapshot": {"bid": 100.0, "offer": 100.0}}
    client.list_positions.return_value = [_P("AAPL", Direction.SELL, 104.0, "BROKER_ID")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "defer.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-03",
                          deal_id="LEDGER_ID", direction="SELL", entry=104.0, size=1.0,
                          stop_level=106.0, rationale="x", opened_at="2026-06-03T14:00:00+00:00",
                          prev_close=100.0, today_open=104.0)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    # past EOD -> exit_rule True -> our close
    await sched.mark_pass(now=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc))
    client.close_position.assert_awaited_once_with("BROKER_ID")
    client.get_transaction_history.assert_not_called()        # no same-pass reconcile
    assert len(ex.ledger.list_open()) == 1                    # row still open for next pass
    assert ex.ledger.realized("gap_fade") == []


@pytest.mark.asyncio
async def test_mark_pass_pending_retries_until_history_posts(tmp_path):
    # broker-closed but history not posted yet -> retry (row stays open), then finalize when posted
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Transaction

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.get_market_details.return_value = {"snapshot": {"bid": 100.0, "offer": 100.0}}
    client.list_positions.return_value = []                   # broker already closed it
    client.get_transaction_history.return_value = []          # history NOT posted yet
    client.get_activity_history.return_value = []
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "retry.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-03",
                          deal_id="D1", direction="SELL", entry=104.0, size=1.0,
                          stop_level=106.0, rationale="x", opened_at="2026-06-03T14:00:00+00:00",
                          prev_close=100.0, today_open=104.0)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    await sched.mark_pass(now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc))
    assert len(ex.ledger.list_open()) == 1                    # retried, not finalized
    # now the TRADE posts -> next pass finalizes with real P&L
    client.get_transaction_history.return_value = [
        Transaction(date=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc), reference="r",
                    dealId="D1", transactionType="TRADE", instrumentName="AAPL",
                    size="2.50", currency="USD")]
    await sched.mark_pass(now=datetime(2026, 6, 3, 15, 15, tzinfo=timezone.utc))
    rz = ex.ledger.realized("gap_fade")
    assert len(rz) == 1 and rz[0]["net_pnl"] == 2.50 and rz[0]["close_reason"] == "BROKER_TRADE"


@pytest.mark.asyncio
async def test_mark_pass_pending_finalizes_after_24h(tmp_path):
    # zombie guard: row older than 24h with still-missing history -> finalize PENDING $0
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_active_account_id.return_value = "EXP"
    client.get_market_details.return_value = {"snapshot": {"bid": 100.0, "offer": 100.0}}
    client.list_positions.return_value = []
    client.get_transaction_history.return_value = []
    client.get_activity_history.return_value = []
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "zombie.db"), dry_run=False)
    ex.ledger.record_open(strategy="gap_fade", epic="AAPL", session_date="2026-06-01",
                          deal_id="D1", direction="SELL", entry=104.0, size=1.0,
                          stop_level=106.0, rationale="x", opened_at="2026-06-01T14:00:00+00:00",
                          prev_close=100.0, today_open=104.0)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    await sched.mark_pass(now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc))   # 2 days later
    rz = ex.ledger.realized("gap_fade")
    assert len(rz) == 1 and rz[0]["close_reason"] == "PENDING_RECONCILE"
