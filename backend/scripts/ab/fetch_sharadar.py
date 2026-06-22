"""Fetch Sharadar (Nasdaq Data Link) into a local parquet cache for cross-sectional
equity factor research. Personal-Use licence: cache is LOCAL + gitignored, NEVER
committed, NEVER surfaced in the MANTIS UI (see docs/SEP_tc.md).

Design for monthly-rebalanced factor backtests (keeps the pull tractable):
- TICKERS  : full universe metadata (sector/industry for neutralisation) -> 1 call.
- SEP      : MONTH-END price snapshots (not full daily) -> ~12/yr calls. Month-end
             closeadj is all a monthly-rebalance momentum/return panel needs.
- SF1      : as-reported fundamentals (ARQ) full history -> bulk export. Carries
             `datekey` (filing-public date) for strict point-in-time joins.

Leak rule baked in downstream: on rebalance date D use only SF1 rows with datekey<=D
and prices known at D; forward return is D->D+1month.

Run from backend/:  .venv/Scripts/python.exe scripts/ab/fetch_sharadar.py
Resumable: skips parquet files already on disk.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]  # backend/
load_dotenv(ROOT / ".env")
import nasdaqdatalink as ndl  # noqa: E402
ndl.ApiConfig.api_key = os.getenv("NASDAQ_DATA_LINK_API_KEY")
assert ndl.ApiConfig.api_key, "NASDAQ_DATA_LINK_API_KEY missing"

CACHE = ROOT / "data" / "sharadar"
CACHE.mkdir(parents=True, exist_ok=True)

START_YEAR = 1999  # SEP begins ~1998; SF1 ~25yr. 1999+ gives dotcom/GFC/COVID regimes.


def fetch_tickers() -> pd.DataFrame:
    f = CACHE / "tickers.parquet"
    if f.exists():
        return pd.read_parquet(f)
    print("TICKERS: fetching universe metadata ...", flush=True)
    df = ndl.get_table("SHARADAR/TICKERS", table="SEP", paginate=True)
    df.to_parquet(f)
    print(f"  {len(df):,} tickers ({(df['isdelisted']=='Y').sum():,} delisted) -> {f.name}")
    return df


def month_end_dates(start_year: int) -> list[str]:
    end = pd.Timestamp.today().normalize()
    rng = pd.date_range(f"{start_year}-01-01", end, freq="BME")  # business month-end
    return [d.strftime("%Y-%m-%d") for d in rng]


def fetch_sep_monthly() -> pd.DataFrame:
    f = CACHE / "sep_monthly.parquet"
    if f.exists():
        return pd.read_parquet(f)
    dates = month_end_dates(START_YEAR)
    print(f"SEP: fetching {len(dates)} month-end snapshots {dates[0]}..{dates[-1]} ...", flush=True)
    frames = []
    for i, d in enumerate(dates):
        for attempt in range(3):
            try:
                snap = ndl.get_table("SHARADAR/SEP", date=d, paginate=True,
                                     qopts={"columns": ["ticker", "date", "closeadj", "volume"]})
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  {d}: FAILED {e}"); snap = pd.DataFrame()
                else:
                    time.sleep(2)
        if len(snap):
            frames.append(snap)
        if (i + 1) % 24 == 0:
            print(f"  ...{i+1}/{len(dates)} ({d}: {len(snap)} names)", flush=True)
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(f)
    print(f"  {len(df):,} rows / {df['ticker'].nunique():,} tickers -> {f.name}")
    return df


SF1_COLS = [
    "ticker", "dimension", "datekey", "calendardate", "reportperiod",
    "marketcap", "pe", "pb", "ps", "evebitda", "evebit", "fcf", "fcfps", "divyield",
    "roe", "roa", "roic", "ros", "grossmargin", "netmargin", "ebitdamargin",
    "de", "currentratio", "assetturnover", "payoutratio",
    "revenue", "netinc", "eps", "ebitda", "ebit", "gp", "cor", "opinc", "sgna", "rnd",
    "assets", "assetsavg", "equity", "equityavg", "debt", "debtusd", "workingcapital",
    "ncfo", "ncff", "ncfi", "capex", "ncfcommon", "ncfdebt", "sbcomp",
    "sharesbas", "shareswa", "shareswadil", "bvps", "dps", "retearn",
    "receivables", "inventory", "ppnenet", "intangibles", "invcap",
]


def quarter_end_dates(start_year: int) -> list[str]:
    end = pd.Timestamp.today().normalize()
    rng = pd.date_range(f"{start_year}-01-01", end, freq="QE")
    return [d.strftime("%Y-%m-%d") for d in rng]


def fetch_sf1() -> pd.DataFrame:
    f = CACHE / "sf1_arq.parquet"
    if f.exists():
        return pd.read_parquet(f)
    qs = quarter_end_dates(START_YEAR)
    print(f"SF1: fetching {len(qs)} quarter-end cross-sections (ARQ) "
          f"{qs[0]}..{qs[-1]} ...", flush=True)
    frames = []
    for i, q in enumerate(qs):
        for attempt in range(3):
            try:
                snap = ndl.get_table("SHARADAR/SF1", calendardate=q, dimension="ARQ",
                                     paginate=True, qopts={"columns": SF1_COLS})
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  {q}: FAILED {e}"); snap = pd.DataFrame()
                else:
                    time.sleep(2)
        if len(snap):
            frames.append(snap)
        if (i + 1) % 20 == 0:
            print(f"  ...{i+1}/{len(qs)} ({q}: {len(snap)} cos)", flush=True)
    df = pd.concat(frames, ignore_index=True)
    df.to_parquet(f)
    print(f"  {len(df):,} rows / {df['ticker'].nunique():,} tickers -> {f.name}")
    return df


if __name__ == "__main__":
    tk = fetch_tickers()
    sep = fetch_sep_monthly()
    sf1 = fetch_sf1()
    print("\n=== CACHE READY ===")
    print(f"  tickers     : {len(tk):,}")
    print(f"  sep_monthly : {len(sep):,} rows, {sep['ticker'].nunique():,} tickers, "
          f"{sep['date'].min()} -> {sep['date'].max()}")
    print(f"  sf1_arq     : {len(sf1):,} rows, {sf1['ticker'].nunique():,} tickers")
