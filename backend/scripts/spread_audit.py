"""
Spread audit — passive collector for Capital.com bid/ask snapshots.

Polls `get_market_details(epic).snapshot` for the TRADABLE_ASSETS basket on a
configurable interval, persists raw observations + computed spread metrics to
monthly parquet partitions under `data/diagnostics/spread_audit/`.

Intended as a 48-72h fire-and-forget runner to calibrate
`backend/src/backtest/costs.py:ASSET_SPREADS` against real broker spreads
across all sessions (US/EU/Asia + overnight + weekend) before re-running
Phase 3 cost validation.

Usage (from `backend/`):
    .venv/Scripts/python.exe scripts/spread_audit.py
    .venv/Scripts/python.exe scripts/spread_audit.py --interval 300 --duration-hours 72
    .venv/Scripts/python.exe scripts/spread_audit.py --epics BTCUSD,ETHUSD,XAUUSD
"""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
from loguru import logger

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.broker.client import CapitalComClient  # noqa: E402
from src.utils.constants import TRADABLE_ASSETS  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "diagnostics" / "spread_audit"

# Asset class mapping for downstream analysis (matches paper_loop.py spread filter).
CRYPTO = {"BTCUSD", "ETHUSD", "SOLUSD", "BNBUSD", "DOGUSD", "DASHUSD", "ICPUSD"}
PRECIOUS = {"XAUUSD", "XAGUSD", "PLATINUM"}
FOREX = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "USDCAD", "AUDUSD", "NZDUSD", "EURJPY"}
INDEX = {"US500", "DE40", "NAS100"}
STOCKS = {"NVDA", "TSLA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "AMD"}


def _asset_class(epic: str) -> str:
    if epic in CRYPTO:
        return "crypto"
    if epic in PRECIOUS:
        return "precious"
    if epic in FOREX:
        return "forex"
    if epic in INDEX:
        return "index"
    if epic in STOCKS:
        return "stocks"
    return "other"


def _extract_snapshot(payload: dict, epic: str) -> dict | None:
    """Pull bid/offer/marketStatus from market-details payload. Returns None on malformed."""
    snap = payload.get("snapshot") or {}
    bid = snap.get("bid")
    offer = snap.get("offer")
    status = snap.get("marketStatus", "UNKNOWN")

    if bid is None or offer is None:
        return None

    try:
        bid_f = float(bid)
        offer_f = float(offer)
    except (TypeError, ValueError):
        return None

    mid = (bid_f + offer_f) / 2.0
    spread = offer_f - bid_f
    spread_pct = (spread / mid) if mid > 0 else 0.0
    spread_bps = spread_pct * 10_000

    return {
        "ts_utc": datetime.now(timezone.utc).replace(tzinfo=None),
        "epic": epic,
        "asset_class": _asset_class(epic),
        "market_status": status,
        "bid": bid_f,
        "offer": offer_f,
        "mid": mid,
        "spread": spread,
        "spread_pct": spread_pct,
        "spread_bps": spread_bps,
    }


def _persist_batch(rows: list[dict]) -> Path | None:
    """Append rows to current monthly parquet partition. Returns target file."""
    if not rows:
        return None

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    target = OUTPUT_DIR / f"{now.year:04d}-{now.month:02d}.parquet"

    new_df = pl.DataFrame(rows)
    if target.exists():
        existing = pl.read_parquet(target)
        combined = pl.concat([existing, new_df], how="vertical_relaxed")
    else:
        combined = new_df

    combined.write_parquet(target, compression="zstd")
    return target


async def _poll_once(client: CapitalComClient, epics: list[str]) -> list[dict]:
    """One snapshot pass across all epics. Failures per-epic are logged but don't abort the pass."""
    rows: list[dict] = []
    for epic in epics:
        try:
            payload = await client.get_market_details(epic)
        except Exception as exc:
            logger.warning(f"[{epic}] get_market_details failed: {exc}")
            continue

        row = _extract_snapshot(payload, epic)
        if row is None:
            logger.warning(f"[{epic}] malformed snapshot — bid/offer missing")
            continue
        rows.append(row)
    return rows


def _summarize(rows: list[dict]) -> str:
    """One-line tradeable/closed summary for log."""
    if not rows:
        return "0 epics"
    tradeable = sum(1 for r in rows if r["market_status"] == "TRADEABLE")
    closed = len(rows) - tradeable
    return f"{len(rows)} epics ({tradeable} TRADEABLE, {closed} CLOSED)"


async def run_audit(
    epics: list[str],
    interval_seconds: int,
    duration_hours: float | None,
) -> None:
    """Main collection loop. Stops on duration_hours elapsed or SIGINT."""
    client = CapitalComClient()

    stop_event = asyncio.Event()

    def _handle_sigint(*_a):
        logger.info("SIGINT received — finishing current pass then exiting")
        stop_event.set()

    # Best-effort signal handler (works on POSIX; on Windows the Ctrl-C exception still works)
    try:
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGINT, _handle_sigint)
        loop.add_signal_handler(signal.SIGTERM, _handle_sigint)
    except (NotImplementedError, RuntimeError):
        signal.signal(signal.SIGINT, lambda *_a: _handle_sigint())

    deadline = None
    if duration_hours is not None:
        deadline = asyncio.get_event_loop().time() + duration_hours * 3600

    logger.info(
        f"Spread audit starting | epics={len(epics)} | interval={interval_seconds}s | "
        f"duration={'unbounded' if duration_hours is None else f'{duration_hours}h'} | "
        f"output={OUTPUT_DIR}"
    )

    pass_count = 0
    while not stop_event.is_set():
        if deadline is not None and asyncio.get_event_loop().time() >= deadline:
            logger.info("Duration deadline reached — stopping")
            break

        pass_count += 1
        t_start = datetime.now(timezone.utc)
        rows = await _poll_once(client, epics)
        target = _persist_batch(rows)
        elapsed = (datetime.now(timezone.utc) - t_start).total_seconds()

        logger.info(
            f"Pass #{pass_count} | {_summarize(rows)} | elapsed={elapsed:.1f}s | "
            f"file={target.name if target else 'n/a'}"
        )

        # Sleep until next tick (subtract elapsed; never go negative)
        sleep_s = max(1.0, float(interval_seconds) - elapsed)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=sleep_s)
        except asyncio.TimeoutError:
            pass  # normal — interval elapsed without shutdown

    # Cleanup
    try:
        await client.session_manager.close()
    except Exception:
        pass
    logger.info(f"Spread audit stopped after {pass_count} pass(es).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Capital.com spread audit collector")
    parser.add_argument(
        "--epics", type=str, default=None,
        help="Comma-separated list of epics. Default: all TRADABLE_ASSETS.",
    )
    parser.add_argument(
        "--interval", type=int, default=300,
        help="Polling interval in seconds (default 300 = 5 min)",
    )
    parser.add_argument(
        "--duration-hours", type=float, default=None,
        help="Stop after N hours (default: run until SIGINT)",
    )
    args = parser.parse_args()

    if args.epics:
        epics = [e.strip() for e in args.epics.split(",") if e.strip()]
    else:
        epics = list(TRADABLE_ASSETS)

    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <7}</level> | {message}",
    )
    log_file = OUTPUT_DIR / "spread_audit.log"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.add(log_file, level="INFO", rotation="10 MB", retention=5)

    try:
        asyncio.run(run_audit(epics, args.interval, args.duration_hours))
    except KeyboardInterrupt:
        logger.info("Interrupted by user.")


if __name__ == "__main__":
    main()
