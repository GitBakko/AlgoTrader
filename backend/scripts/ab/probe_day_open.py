"""Probe: does the Capital.com DAY candle .open == cash-session open (09:30 ET)?

Decides whether the future fix "source H2 open_px from today's DAY candle open"
(instead of first in-window mid, which a mid-session restart re-snapshots into a
false gap) is valid. If the CFD DAY candle is anchored to broker-midnight / the
overnight roll, its .open != cash open and the fix would be WRONG.

Read-only market data (NOT account-scoped) on a separate experiment session — no
orders, no account switch, no interference with the live loop. Run from backend/.
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from src.broker.models import Resolution  # noqa: E402
from forward_lab import _connected_client  # noqa: E402

EPICS = ["NVDA", "AAPL", "MSFT", "AMD", "TSLA", "AVGO"]
# Last completed US session relative to "now". Pass an explicit date so the probe
# is reproducible regardless of when it runs (Date.now-free determinism not
# required here, but explicit is clearer).
PROBE_DAY = datetime(2026, 6, 5, tzinfo=timezone.utc).date()  # Friday 2026-06-05
CASH_OPEN_UTC = datetime(PROBE_DAY.year, PROBE_DAY.month, PROBE_DAY.day, 13, 30, tzinfo=timezone.utc)  # 09:30 ET EDT


def _utc(c) -> datetime:
    raw = c.timestamp_utc or c.timestamp
    return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)


async def probe_epic(client, epic: str) -> None:
    print(f"\n===== {epic} =====")
    # --- DAY candles around the probe day ---
    try:
        days = await client.get_historical_prices(
            epic, Resolution.DAY,
            from_date=datetime(2026, 6, 2, tzinfo=timezone.utc),
            to_date=datetime(2026, 6, 6, 23, 0, tzinfo=timezone.utc))
    except Exception as e:  # noqa: BLE001
        print(f"  DAY fetch failed: {e}")
        return
    day_candle = None
    prev_close = None
    for c in days:
        if _utc(c).date() == PROBE_DAY:
            day_candle = c
        elif _utc(c).date() < PROBE_DAY:
            prev_close = c.close
    if day_candle is None:
        print(f"  no DAY candle for {PROBE_DAY} (got {[_utc(c).date().isoformat() for c in days]})")
        return
    print(f"  DAY candle  snapshotTime(local)={day_candle.timestamp}  "
          f"snapshotTimeUTC={day_candle.timestamp_utc}")
    print(f"  DAY open={day_candle.open}  high={day_candle.high}  "
          f"low={day_candle.low}  close={day_candle.close}")
    if prev_close is not None:
        print(f"  prev DAY close={prev_close}")

    # --- M5 bars around cash open ---
    try:
        m5 = await client.get_historical_prices(
            epic, Resolution.MINUTE_5,
            from_date=CASH_OPEN_UTC - timedelta(minutes=20),
            to_date=CASH_OPEN_UTC + timedelta(minutes=35))
    except Exception as e:  # noqa: BLE001
        print(f"  M5 fetch failed: {e}")
        return
    cash_bar = None
    print("  M5 bars (UTC bar-start -> open):")
    for c in m5:
        ts = _utc(c)
        flag = ""
        if ts == CASH_OPEN_UTC:
            cash_bar = c
            flag = "  <- CASH OPEN 09:30 ET"
        print(f"    {ts.isoformat()}  open={c.open}{flag}")

    # --- verdict ---
    if cash_bar is None:
        print("  ?? no M5 bar exactly at 13:30 UTC — inspect bars above")
        return
    diff = abs(day_candle.open - cash_bar.open)
    rel = diff / cash_bar.open if cash_bar.open else float("inf")
    print(f"  >>> DAY.open={day_candle.open}  cash-open M5.open={cash_bar.open}  "
          f"abs_diff={diff:.4f}  rel={rel*100:.3f}%  "
          f"{'CASH-ANCHORED (fix valid)' if rel < 0.001 else 'NOT cash-anchored (fix INVALID)'}")


async def main() -> None:
    client = await _connected_client(experiment=True)
    try:
        for epic in EPICS:
            await probe_epic(client, epic)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
