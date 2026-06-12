import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import sqlite3
import pytest
from unittest.mock import AsyncMock


def _seed(db_path):
    from forward.ledger import ForwardLedger
    led = ForwardLedger(db_path)
    led.record_open(strategy="orb", epic="AAPL", session_date="2026-06-05",
                    deal_id="D1", direction="BUY", entry=103.0, size=1.0,
                    stop_level=99.0, rationale="t",
                    opened_at="2026-06-05T14:00:00+00:00")
    led.record_close(deal_id="D1", exit_price=104.99, net_pnl=-7.5,
                     closed_at="2026-06-05T16:00:00+00:00", close_reason="BROKER_ACTIVITY")
    led.record_open(strategy="orb", epic="NVDA", session_date="2026-06-05",
                    deal_id="D2", direction="BUY", entry=900.0, size=1.0,
                    stop_level=890.0, rationale="t",
                    opened_at="2026-06-05T14:00:00+00:00")
    led.record_close(deal_id="D2", exit_price=905.0, net_pnl=5.0,
                     closed_at="2026-06-05T16:00:00+00:00", close_reason="BROKER_ACTIVITY")
    return led


def _close_event(epic, open_price, level):
    from src.broker.models import ActivityEvent
    return ActivityEvent.model_validate({
        "date": "2026-06-05T16:00:00", "epic": epic, "source": "SL",
        "type": "POSITION", "status": "ACCEPTED", "dealId": "DROT",
        "details": {"openPrice": open_price, "direction": "SELL", "level": level}})


@pytest.mark.asyncio
async def test_backfill_updates_matching_rows_and_reports(tmp_path):
    from backfill_exit_price import backfill

    db = tmp_path / "bf.db"
    _seed(db)

    async def acts(frm, to):
        return [_close_event("AAPL", 103.0, 101.25)]  # only AAPL resolvable

    client = AsyncMock()
    client.get_activity_history.side_effect = acts
    report = await backfill(db, client, dry_run=False)
    assert report["updated"] == 1 and report["total"] == 2
    with sqlite3.connect(db) as c:
        px_aapl = c.execute("SELECT exit_price FROM trades WHERE deal_id='D1'").fetchone()[0]
        px_nvda = c.execute("SELECT exit_price FROM trades WHERE deal_id='D2'").fetchone()[0]
    assert px_aapl == 101.25       # backfilled from activity level
    assert px_nvda == 905.0        # untouched (no matching close event)


@pytest.mark.asyncio
async def test_backfill_dry_run_touches_nothing(tmp_path):
    from backfill_exit_price import backfill

    db = tmp_path / "bf2.db"
    _seed(db)

    async def acts(frm, to):
        return [_close_event("AAPL", 103.0, 101.25)]

    client = AsyncMock()
    client.get_activity_history.side_effect = acts
    report = await backfill(db, client, dry_run=True)
    assert report["updated"] == 1  # WOULD update
    with sqlite3.connect(db) as c:
        px = c.execute("SELECT exit_price FROM trades WHERE deal_id='D1'").fetchone()[0]
    assert px == 104.99  # unchanged
