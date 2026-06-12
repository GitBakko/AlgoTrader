import sys, pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock


def _txn(deal_id, size, epic="AAPL"):
    from src.broker.models import Transaction

    return Transaction(
        date=datetime(2026, 6, 3, 16, 0, tzinfo=timezone.utc),
        reference=f"r-{deal_id}",
        dealId=deal_id,
        transactionType="TRADE",
        instrumentName=epic,
        size=size,
        currency="USD",
    )


@pytest.mark.asyncio
async def test_realized_picks_txn_by_dealid(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    # two TRADE rows, same epic, different dealId (H2 short vs H3 long on AAPL same day)
    client.get_transaction_history.return_value = [_txn("DH2", "3.00"), _txn("DH3", "-5.00")]
    ex = ExperimentExecutor(
        client=client,
        experiment_account_id="EXP",
        ledger=ForwardLedger(tmp_path / "r.db"),
        dry_run=False,
    )
    sched = ExperimentScheduler(
        client=client, executor=ex, strategies=[GapFadeStrategy(epics=["AAPL"])]
    )
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
    ex = ExperimentExecutor(
        client=client,
        experiment_account_id="EXP",
        ledger=ForwardLedger(tmp_path / "r2.db"),
        dry_run=False,
    )
    sched = ExperimentScheduler(
        client=client, executor=ex, strategies=[GapFadeStrategy(epics=["AAPL"])]
    )
    row = {"epic": "AAPL", "deal_id": "DMINE"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == 0.0 and reason == "PENDING_RECONCILE"


def _activity(deal_id, open_price, epic="AAPL", source="SL", level=None):
    from src.broker.models import ActivityEvent

    details = {"openPrice": open_price, "direction": "SELL"}
    if level is not None:
        details["level"] = level
    return ActivityEvent.model_validate(
        {
            "date": "2026-06-03T16:00:00",
            "epic": epic,
            "source": source,
            "type": "POSITION",
            "status": "ACCEPTED",
            "dealId": deal_id,
            "details": details,
        }
    )


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
    ex = ExperimentExecutor(
        client=client,
        experiment_account_id="EXP",
        ledger=ForwardLedger(tmp_path / "t2.db"),
        dry_run=False,
    )
    sched = ExperimentScheduler(
        client=client, executor=ex, strategies=[ORBStrategy(epics=["AAPL"])]
    )
    row = {
        "epic": "AAPL",
        "deal_id": "DPOS",
        "entry": 103.0,
        "opened_at": "2026-06-03T14:30:00+00:00",
        "direction": "BUY",
    }
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
    ex = ExperimentExecutor(
        client=client,
        experiment_account_id="EXP",
        ledger=ForwardLedger(tmp_path / "t1.db"),
        dry_run=False,
    )
    sched = ExperimentScheduler(
        client=client, executor=ex, strategies=[GapFadeStrategy(epics=["AAPL"])]
    )
    row = {
        "epic": "AAPL",
        "deal_id": "DSAME",
        "entry": 100.0,
        "opened_at": "2026-06-03T14:00:00+00:00",
        "direction": "SELL",
    }
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
    client.get_activity_history.return_value = []  # nothing to link
    ex = ExperimentExecutor(
        client=client,
        experiment_account_id="EXP",
        ledger=ForwardLedger(tmp_path / "t3.db"),
        dry_run=False,
    )
    sched = ExperimentScheduler(
        client=client, executor=ex, strategies=[ORBStrategy(epics=["AAPL"])]
    )
    row = {
        "epic": "AAPL",
        "deal_id": "MINE",
        "entry": 103.0,
        "opened_at": "2026-06-03T14:30:00+00:00",
        "direction": "BUY",
    }
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == 0.0 and reason == "PENDING_RECONCILE"


@pytest.mark.asyncio
async def test_realized_window_clamps_future_to_and_uses_opened_at(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    captured = {}

    async def _txns(frm, to):
        captured["txn"] = (frm, to)
        return []

    async def _acts(frm, to):
        captured["act"] = (frm, to)
        return []

    client = AsyncMock()
    client.get_transaction_history.side_effect = _txns
    client.get_activity_history.side_effect = _acts
    ex = ExperimentExecutor(
        client=client,
        experiment_account_id="EXP",
        ledger=ForwardLedger(tmp_path / "win.db"),
        dry_run=False,
    )
    sched = ExperimentScheduler(
        client=client, executor=ex, strategies=[GapFadeStrategy(epics=["AMD"])]
    )
    row = {
        "epic": "AMD",
        "deal_id": "DX",
        "entry": 533.79,
        "opened_at": "2026-06-03T13:36:44+00:00",
        "direction": "SELL",
    }
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    now = datetime.now(timezone.utc)
    frm_t, to_t = captured["txn"]
    # `to` must NOT be in the future (clamped to ~now-60s)
    assert to_t <= now
    assert (now - to_t).total_seconds() >= 55
    # `from` tied to opened_at (1h before) for the wide TRANSACTION window
    assert frm_t < to_t
    # activity window is clamped to <24h: /history/activity rejects wider spans
    # (error.invalid.daterange), unlike /history/transactions which keeps the
    # wide window. They diverge once the txn span exceeds ~23h.
    act_frm, act_to = captured["act"]
    assert act_to == to_t
    assert (act_to - act_frm) <= timedelta(hours=24)
    assert act_frm == max(frm_t, to_t - timedelta(hours=23))
    assert reason == "PENDING_RECONCILE"  # empty histories -> pending (no invented P&L)


@pytest.mark.asyncio
async def test_realized_overnight_carry_clamps_activity_window(tmp_path):
    # CB-class bug: a position carried >24h (opened day N, EOD-flattened day N+1) made
    # _realized request /history/activity over a >24h span, which the broker rejects
    # with error.invalid.daterange -> Tier-2 link died -> stuck PENDING_RECONCILE with
    # P&L lost. The activity window must clamp to <=24h while Tier-2 still links the
    # rotated close dealId for realized P&L.
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import ActivityEvent

    captured = {}
    recent = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")

    async def _acts(frm, to):
        captured["act"] = (frm, to)
        # broker SL/flatten rotated the close dealId to "DPOS1"; close event is recent
        return [
            ActivityEvent.model_validate(
                {
                    "date": recent,
                    "epic": "CB",
                    "source": "SL",
                    "type": "POSITION",
                    "status": "ACCEPTED",
                    "dealId": "DPOS1",
                    "details": {"openPrice": 103.0, "direction": "SELL"},
                }
            )
        ]

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DPOS1", "-9.23", epic="CB")]
    client.get_activity_history.side_effect = _acts
    ex = ExperimentExecutor(
        client=client,
        experiment_account_id="EXP",
        ledger=ForwardLedger(tmp_path / "ovn.db"),
        dry_run=False,
    )
    sched = ExperimentScheduler(client=client, executor=ex, strategies=[ORBStrategy(epics=["CB"])])
    # opened ~31h before now -> wide txn window >24h, must NOT be passed verbatim to activity
    opened = datetime.now(timezone.utc) - timedelta(hours=31)
    row = {
        "epic": "CB",
        "deal_id": "DPOS",
        "entry": 103.0,
        "opened_at": opened.isoformat(),
        "direction": "BUY",
    }
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    # Tier-2 reconciles despite the overnight carry (was PENDING_RECONCILE before the fix)
    assert net == -9.23 and reason == "BROKER_ACTIVITY"
    # activity window clamped to <=24h (would have been ~31h, broker-rejected, before the fix)
    act_frm, act_to = captured["act"]
    assert (act_to - act_frm) <= timedelta(hours=24)


@pytest.mark.asyncio
async def test_tier2_exit_price_uses_activity_level(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DPOS1", "-7.50")]
    client.get_activity_history.return_value = [
        _activity("DPOS1", open_price=103.0, level=101.25)]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "lv.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DPOS", "entry": 103.0,
           "opened_at": "2026-06-03T14:30:00+00:00", "direction": "BUY"}
    net, px, reason = await sched._realized(row, fallback_px=100.0)
    assert reason == "BROKER_ACTIVITY" and px == 101.25  # broker close level, not mid


@pytest.mark.asyncio
async def test_tier2_exit_price_falls_back_to_mid_when_level_absent(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DPOS1", "-7.50")]
    client.get_activity_history.return_value = [_activity("DPOS1", open_price=103.0)]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "lv2.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DPOS", "entry": 103.0,
           "opened_at": "2026-06-03T14:30:00+00:00", "direction": "BUY"}
    net, px, reason = await sched._realized(row, fallback_px=100.0)
    assert reason == "BROKER_ACTIVITY" and px == 100.0


@pytest.mark.asyncio
async def test_tier1_matches_persisted_close_deal_id(tmp_path):
    """Our own close was sent with the broker's CURRENT (rotated) dealId; the TRADE
    row carries that id, not the stored create-confirmation id. Tier-1 must match
    via row['close_deal_id'] without any activity call."""
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import GapFadeStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger

    client = AsyncMock()
    client.get_transaction_history.return_value = [_txn("DROT", "4.00")]
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=ForwardLedger(tmp_path / "cdid.db"), dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[GapFadeStrategy(epics=["AAPL"])])
    row = {"epic": "AAPL", "deal_id": "DMINE", "close_deal_id": "DROT",
           "entry": 100.0, "opened_at": "2026-06-03T14:00:00+00:00",
           "direction": "SELL"}
    net, _px, reason = await sched._realized(row, fallback_px=100.0)
    assert net == 4.00 and reason == "BROKER_TRADE"
    client.get_activity_history.assert_not_called()


@pytest.mark.asyncio
async def test_mark_pass_persists_close_deal_id_on_our_close(tmp_path):
    from forward.scheduler import ExperimentScheduler
    from forward.strategy import ORBStrategy
    from forward.executor import ExperimentExecutor
    from forward.ledger import ForwardLedger
    from src.broker.models import Position

    client = AsyncMock()
    # broker position with ROTATED dealId vs the stored one; same epic+dir+level
    client.list_positions.return_value = [Position.model_validate({
        "dealId": "DCUR", "epic": "AAPL", "direction": "BUY",
        "size": 1.0, "level": 103.0, "currency": "USD",
        "createdDate": "2026-06-12T14:00:00"})]
    client.get_market_details.return_value = {"snapshot": {"bid": 104.0, "offer": 104.2}}
    client.get_active_account_id.return_value = "EXP"
    led = ForwardLedger(tmp_path / "mp.db")
    led.record_open(strategy="orb", epic="AAPL", session_date="2026-06-12",
                    deal_id="DSTORED", direction="BUY", entry=103.0, size=1.0,
                    stop_level=99.0, rationale="t",
                    opened_at="2026-06-12T14:00:00+00:00")
    ex = ExperimentExecutor(client=client, experiment_account_id="EXP",
                            ledger=led, dry_run=False)
    sched = ExperimentScheduler(client=client, executor=ex,
                                strategies=[ORBStrategy(epics=["AAPL"])])
    # past session_close (15:45 ET = 19:45 UTC) -> ORB exit_rule fires -> our close
    await sched.mark_pass(now=datetime(2026, 6, 12, 20, 0, tzinfo=timezone.utc))
    client.close_position.assert_awaited_once_with("DCUR")
    assert led.list_open()[0]["close_deal_id"] == "DCUR"
