"""Alternative-data alpha signals from the Sharadar SFA bundle that came with the
$79 but were never opened: SF2 (insider transactions) and SF3 (institutional 13F).
Both are mechanisms ORTHOGONAL to price/fundamental factors -> diversification.

Each signal builds a wide [month_end x ticker] score and is judged through the SAME
leak-safe pipeline as the equity factors (xsec_factors.backtest_factor / metrics / dsr).

PIT discipline (the leak traps for THESE datasets specifically):
- SF2 insider: use `filingdate` (when the Form 4 became public), NOT `transactiondate`
  (the trade can be disclosed up to 2 business days later; using transactiondate leaks).
- SF3 institutional: 13F is filed up to 45 days AFTER quarter-end. A `calendardate`
  quarter is only KNOWN ~45+ days later, so attach a 13F quarter to a month only if
  (month_end >= calendardate + ~45 days). We lag by one full quarter to be safe.

Run from backend/:  .venv/Scripts/python.exe scripts/ab/alt_signals.py insider
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))
load_dotenv(ROOT / ".env")
import nasdaqdatalink as ndl  # noqa: E402
ndl.ApiConfig.api_key = os.getenv("NASDAQ_DATA_LINK_API_KEY")

from xsec_factors import (  # noqa: E402
    CACHE, MIN_PRICE, load, price_panel, pit_fundamentals,
    sector_neutralize, backtest_factor, benchmark_universe, metrics, dsr,
    _block_bootstrap_sharpe, line,
)

MCAP_FLOOR = 2e9


# ---------------------------------------------------------------- SF2 insider
def fetch_sf2(year_from: int = 2003) -> pd.DataFrame:
    f = CACHE / "sf2_insider.parquet"
    if f.exists():
        return pd.read_parquet(f)
    cols = ["ticker", "filingdate", "transactiondate", "transactioncode",
            "transactionshares", "transactionvalue", "isofficer", "isdirector",
            "istenpercentowner", "ownername"]
    frames = []
    end = pd.Timestamp.today().year
    for y in range(year_from, end + 1):
        for attempt in range(3):
            try:
                df = ndl.get_table("SHARADAR/SF2",
                                   filingdate={"gte": f"{y}-01-01", "lte": f"{y}-12-31"},
                                   paginate=True, qopts={"columns": cols})
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  SF2 {y}: FAIL {e}"); df = pd.DataFrame()
                else:
                    time.sleep(2)
        if len(df):
            frames.append(df)
            print(f"  SF2 {y}: {len(df):,} rows", flush=True)
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(f)
    print(f"  SF2 total {len(out):,} rows -> {f.name}")
    return out


def insider_signal(P: pd.DataFrame, sf2: pd.DataFrame, window_m: int = 6) -> pd.DataFrame:
    """Insider net-buying score per (month_end, ticker): net BUY value (officers/
    directors, code 'P' purchase minus 'S' sale) over the trailing `window_m` months,
    scaled by marketcap proxy (rolling). PIT anchor = filingdate."""
    s = sf2.copy()
    s["filingdate"] = pd.to_datetime(s["filingdate"]).astype("datetime64[ns]")
    s = s[s["filingdate"].notna()]
    # purchases positive, sales negative; insiders that matter = officers/directors
    s = s[(s["isofficer"] == 1) | (s["isdirector"] == 1) | (s["istenpercentowner"] == 1)]
    sign = np.where(s["transactioncode"] == "P", 1.0,
                    np.where(s["transactioncode"] == "S", -1.0, 0.0))
    s["signed_val"] = sign * s["transactionvalue"].fillna(0.0)
    s["ym"] = s["filingdate"].values.astype("datetime64[M]")
    monthly = s.groupby(["ym", "ticker"])["signed_val"].sum().reset_index()
    wide = monthly.pivot_table(index="ym", columns="ticker", values="signed_val",
                               aggfunc="sum")
    wide.index = pd.to_datetime(wide.index)
    # align to P month-ends, trailing-sum over window (leak-safe: only past+current month)
    wide = wide.reindex(columns=P.columns)
    full = pd.DataFrame(index=P.index, columns=P.columns, dtype=float)
    w = wide.reindex(P.index, method=None).fillna(0.0)
    score = w.rolling(window_m, min_periods=1).sum()
    return score


def run_insider(mcap_floor: float = MCAP_FLOOR, oos_frac: float = 0.35):
    tk, sep, sf1 = load()
    P = price_panel(sep)
    fund = pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= MIN_PRICE) & (mcap >= mcap_floor)
    sector = tk.drop_duplicates("ticker").set_index("ticker")["sicsector"]
    print("fetching SF2 insider ...")
    sf2 = fetch_sf2()
    print(f"SF2: {len(sf2):,} rows, {sf2['ticker'].nunique():,} tickers")
    score = insider_signal(P, sf2)
    sn = sector_neutralize(score, sector)
    split = P.index[int(len(P) * (1 - oos_frac))]
    print(f"\n=== INSIDER net-buying signal (sector-neutral) OOS split={split.date()} ===")
    for tag, kw in [("L/S decile", {"top_frac": 0.1}),
                    ("long-only quintile", {"long_only": True, "top_frac": 0.2})]:
        r, to = backtest_factor(P, sn, mask, **kw)
        print(line(tag, metrics(r)) + f" turn={to:.2f}")
        o = metrics(r[r.index >= split])
        print(line("  OOS", o) + f"  DSR(N=3)={dsr(r,3):.3f}")
    r, _ = backtest_factor(P, sn, mask, long_only=True, top_frac=0.2)
    lo5, med, hi = _block_bootstrap_sharpe(r[r.index >= split])
    print(f"  bootstrap OOS Sharpe 90% CI=[{lo5:.2f},{hi:.2f}] med={med:.2f}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "insider"
    if cmd == "insider":
        run_insider()
