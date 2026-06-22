"""Fetch multi-year 1-minute S&P 500 (cash-index CFD) bars from Dukascopy (FREE).

Backtest-history source for the intraday-momentum lead (Zarattini SSRN 4824172).
Capital.com can execute MINUTE_5 forward/live but lacks the multi-year intraday
depth a 17yr OOS test needs — Dukascopy fills that gap, no key required.

Data notes:
- Dukascopy S&P500 index CFD trades ~23h/day (UTC), with a daily settlement gap.
- We KEEP only the US regular cash session (09:30-16:00 ET) because the strategy
  is anchored to the cash open. DST handled via America/New_York tz conversion.
- Bars are BID side (the strategy is direction-symmetric; spread cost is modeled
  separately in the backtester, not embedded in the price).

Cache: backend/data/intraday/sp500_1m_<YEAR>.parquet  (resumable: skips existing).
Run from backend/:  .venv/Scripts/python.exe scripts/ab/fetch_dukascopy_intraday.py 2012 2026
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

import dukascopy_python as dk
from dukascopy_python.instruments import INSTRUMENT_IDX_AMERICA_E_SANDP_500 as SP500

ROOT = Path(__file__).resolve().parents[2]  # backend/
CACHE = ROOT / "data" / "intraday"
CACHE.mkdir(parents=True, exist_ok=True)

SESSION_START = (9, 30)  # ET cash open
SESSION_END = (16, 0)    # ET cash close


def _restrict_to_cash_session(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only 09:30-16:00 America/New_York bars; add ET-local columns."""
    if df.empty:
        return df
    et = df.index.tz_convert("America/New_York")
    mins = et.hour * 60 + et.minute
    start = SESSION_START[0] * 60 + SESSION_START[1]
    end = SESSION_END[0] * 60 + SESSION_END[1]
    # cash session bars: 09:30 .. 15:59 (16:00 close handled as last tradable);
    # keep [09:30, 16:00) so the 16:00 stamp itself (post-close print) is dropped.
    mask = (mins >= start) & (mins < end) & (et.dayofweek < 5)
    out = df.loc[mask].copy()
    out["et"] = et[mask]
    out["session"] = out["et"].dt.normalize().dt.tz_localize(None)  # the trading day
    out["minute_of_day"] = mins[mask] - start  # 0 at 09:30, 389 at 15:59
    return out


def fetch_year(year: int) -> pd.DataFrame:
    cache_file = CACHE / f"sp500_1m_{year}.parquet"
    if cache_file.exists():
        return pd.read_parquet(cache_file)
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1) if year < datetime.now().year else datetime.now()
    print(f"  fetching {year} ({start.date()} -> {end.date()}) ...", flush=True)
    raw = dk.fetch(SP500, dk.INTERVAL_MIN_1, dk.OFFER_SIDE_BID, start, end)
    if raw is None or raw.empty:
        print(f"  {year}: EMPTY", flush=True)
        return pd.DataFrame()
    sess = _restrict_to_cash_session(raw)
    sess.to_parquet(cache_file)
    n_days = sess["session"].nunique() if not sess.empty else 0
    print(f"  {year}: {len(sess):,} session bars over {n_days} trading days "
          f"-> {cache_file.name}", flush=True)
    return sess


def load_all(year_from: int, year_to: int) -> pd.DataFrame:
    frames = []
    for y in range(year_from, year_to + 1):
        df = fetch_year(y)
        if not df.empty:
            frames.append(df)
    if not frames:
        raise RuntimeError("no intraday data fetched")
    alldf = pd.concat(frames).sort_index()
    return alldf


if __name__ == "__main__":
    yf = int(sys.argv[1]) if len(sys.argv) > 1 else 2012
    yt = int(sys.argv[2]) if len(sys.argv) > 2 else datetime.now().year
    print(f"Fetching SP500 1m cash-session bars {yf}..{yt}")
    df = load_all(yf, yt)
    days = df["session"].nunique()
    print(f"\nTOTAL: {len(df):,} bars / {days} trading days / "
          f"{df.index.min()} -> {df.index.max()}")
    print(f"avg bars/day: {len(df)/max(days,1):.0f} (expect ~390 for full cash session)")
