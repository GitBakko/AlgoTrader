"""Leak-free 13F institutional-accumulation signal on Sharadar SF3.

SIGNAL THESIS: when institutions ACCUMULATE a stock (rising holder count and/or
rising aggregate share-units quarter-over-quarter), that "smart money" inflow may
predict cross-sectional outperformance. We test it the same leak-disciplined way
as every other Sharadar factor.

DATA (SF3): one row per (investorname, ticker, securitytype, calendardate). HUGE.
A full per-CALENDARDATE cross-section pull blows the get_table row cap
(LimitExceededError — AAPL alone has 6.4k holder rows in a single quarter), so we
CANNOT pull a whole quarter at once. Instead we iterate PER TICKER over the union
of names that ever had marketcap>=2e9 (join via SF1) AND appear in the price panel
(~4.75k tradeable large-caps). One get_table(ticker=...) call returns that ticker's
full holder history across all quarters and paginates cleanly. We keep only
securitytype=='SHR' (real share holdings, not PUT/CLL/DBT option/debt lines) and
AGGREGATE on the fly to per-(ticker,quarter):
  - inst_value   = sum(value)            total institutional $ held
  - inst_units   = sum(units)            total institutional share-units held
  - n_holders    = nunique(investorname) number of distinct 13F filers holding it
Cached resumably to data/sharadar/sf3_agg.parquet (checkpoint every N tickers).

PIT LAG (CRITICAL): 13F is filed up to 45 days AFTER quarter-end. A quarter's data
is only KNOWN ~45+ days later. To be SAFE we lag a FULL QUARTER: a quarter with
calendardate Q is attached to a month-end D only if D >= Q + ~1 quarter (we use
Q + 100 calendar days, which exceeds the 45-day filing deadline by a wide margin
and lands the signal in the month AFTER all filers must have reported). This means
e.g. the 2020-03-31 quarter (filed by ~2020-05-15) becomes usable from 2020-07-31
month-end onward. The QoQ change at quarter Q compares Q vs Q-1, both known by then.

SCORE: cross-sectional QoQ accumulation:
  d_holders = n_holders(Q) / n_holders(Q-1) - 1     (holder-breadth change)
  d_units   = inst_units(Q) / inst_units(Q-1) - 1   (share-accumulation change)
  accum     = z(d_holders) + z(d_units)             (combined accumulation)
Each attached to month-ends with the PIT lag, forward-filled within the quarter,
sector-neutralized, then backtested via the leak-safe harness (long-only top
quintile AND L/S decile).

Run from backend/:
  .venv/Scripts/python.exe scripts/ab/inst_13f.py            # fetch (resumable) + backtest
  .venv/Scripts/python.exe scripts/ab/inst_13f.py backtest   # backtest only (cache must exist)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "sharadar"
SF3_AGG = CACHE / "sf3_agg.parquet"

MCAP_FLOOR_FETCH = 2e9   # only aggregate names >=$2B that quarter (tractable + tradeable)
PIT_LAG_DAYS = 100       # >45d filing deadline; ~1 full quarter lag, very safe

import xsec_factors as xf  # noqa: E402  (same dir on sys.path when run from scripts/ab)


# ------------------------------------------------------------------ fetch
def fetch_universe(sf1: pd.DataFrame, sep: pd.DataFrame) -> list[str]:
    """Union of tickers that EVER had marketcap>=floor AND appear in the price panel
    (tradeable). This bounds the per-ticker SF3 fetch to ~4.75k large-caps."""
    big = set(sf1[sf1["marketcap"] >= MCAP_FLOOR_FETCH]["ticker"].dropna().unique())
    tradeable = set(sep["ticker"].dropna().unique())
    return sorted(big & tradeable)


def fetch_sf3_agg(sf1: pd.DataFrame, sep: pd.DataFrame) -> pd.DataFrame:
    """Per-(ticker,quarter) institutional aggregate. Iterates PER TICKER (one
    get_table call per name returns its full holder history). securitytype=='SHR'
    only. Resumable: skips tickers already in the cache. Checkpoints to disk."""
    import nasdaqdatalink as ndl
    from dotenv import load_dotenv

    load_dotenv(CACHE.parents[1] / ".env")  # backend/.env
    load_dotenv(".env")
    ndl.ApiConfig.api_key = os.getenv("NASDAQ_DATA_LINK_API_KEY")

    universe = fetch_universe(sf1, sep)
    done: set[str] = set()
    if SF3_AGG.exists():
        prev = pd.read_parquet(SF3_AGG)
        prev["calendardate"] = pd.to_datetime(prev["calendardate"])
        done = set(prev["ticker"].unique())
        print(f"resume: {len(done)} tickers already cached "
              f"({len(prev)} ticker-quarter rows)")
    else:
        prev = pd.DataFrame()

    todo = [t for t in universe if t not in done]
    print(f"fetching {len(todo)} tickers (of {len(universe)} large-cap universe) from SF3 ...")
    rows = []
    t_start = time.time()
    for i, tkr in enumerate(todo):
        for attempt in range(4):
            try:
                df = ndl.get_table(
                    "SHARADAR/SF3", ticker=tkr,
                    qopts={"columns": ["ticker", "calendardate", "investorname",
                                       "securitytype", "units", "value"]},
                    paginate=True)
                break
            except Exception as e:  # noqa: BLE001
                if attempt == 3:
                    print(f"  {tkr} FAILED after retries: {e}")
                    df = pd.DataFrame()
                    break
                time.sleep(2 * (attempt + 1))
        if df is None or len(df) == 0:
            # record an empty marker so resume doesn't re-fetch a genuinely empty name
            rows.append(pd.DataFrame([{"ticker": tkr, "calendardate": pd.NaT,
                                       "inst_value": np.nan, "inst_units": np.nan,
                                       "n_holders": 0}]))
            continue
        df = df[df["securitytype"] == "SHR"]                 # real share holdings only
        df = df[df["units"].fillna(0) > 0]
        if len(df) == 0:
            rows.append(pd.DataFrame([{"ticker": tkr, "calendardate": pd.NaT,
                                       "inst_value": np.nan, "inst_units": np.nan,
                                       "n_holders": 0}]))
            continue
        df["calendardate"] = pd.to_datetime(df["calendardate"])
        agg = (df.groupby(["ticker", "calendardate"])
                 .agg(inst_value=("value", "sum"),
                      inst_units=("units", "sum"),
                      n_holders=("investorname", "nunique"))
                 .reset_index())
        rows.append(agg)
        if (i + 1) % 25 == 0 or i == len(todo) - 1:
            rate = (i + 1) / (time.time() - t_start)
            eta = (len(todo) - i - 1) / rate / 60 if rate > 0 else 0
            print(f"  [{i+1}/{len(todo)}] {tkr}: {len(agg)} quarters  "
                  f"({rate:.1f} tkr/s, ETA {eta:.0f}m)")
            cur = pd.concat([prev] + rows, ignore_index=True)
            cur.to_parquet(SF3_AGG, index=False)

    final = pd.concat([prev] + rows, ignore_index=True) if rows else prev
    final = final.dropna(subset=["calendardate"])            # drop empty markers for stats
    final = final.drop_duplicates(["ticker", "calendardate"]).reset_index(drop=True)
    # re-attach empty markers so resume is complete
    allrows = pd.concat([prev] + rows, ignore_index=True).drop_duplicates(["ticker", "calendardate"])
    allrows.to_parquet(SF3_AGG, index=False)
    print(f"cache written: {SF3_AGG}  ({len(final)} non-empty ticker-quarter rows, "
          f"{final['ticker'].nunique()} tickers, {final['calendardate'].nunique()} quarters)")
    return final


# ------------------------------------------------------------------ signal
def build_score(agg: pd.DataFrame, P: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Build leak-safe score_wide[month_end x ticker] from per-quarter aggregates.

    QoQ change computed within ticker on quarter order (uses only Q and Q-1).
    Attached to month-end D iff D >= calendardate + PIT_LAG_DAYS (filing-public lag).
    Forward-filled across month-ends within the quarter's validity window.
    """
    a = agg.copy()
    a["calendardate"] = pd.to_datetime(a["calendardate"])
    a = a.sort_values(["ticker", "calendardate"])
    g = a.groupby("ticker", group_keys=False)
    a["d_holders"] = g["n_holders"].apply(lambda s: s / s.shift(1) - 1.0)
    a["d_units"] = g["inst_units"].apply(lambda s: s / s.shift(1) - 1.0)
    # availability date = quarter-end + PIT lag (when the signal becomes KNOWN)
    a["avail"] = a["calendardate"] + pd.Timedelta(days=PIT_LAG_DAYS)

    dates = P.index
    tickers = P.columns

    def to_wide(col: str) -> pd.DataFrame:
        """For each month-end D, take the LATEST quarter whose avail<=D (asof-backward)."""
        sub = a[["ticker", "avail", col]].dropna(subset=[col]).sort_values("avail")
        wide = pd.DataFrame(index=dates, columns=tickers, dtype=float)
        for tk_, grp in sub.groupby("ticker"):
            if tk_ not in wide.columns:
                continue
            grp = grp.sort_values("avail")
            # asof: for each month-end, value of the most recent avail<=date
            idx = np.searchsorted(grp["avail"].values, dates.values, side="right") - 1
            vals = np.where(idx >= 0, grp[col].values[idx.clip(min=0)], np.nan)
            wide[tk_] = vals
        return wide

    dh = to_wide("d_holders")
    du = to_wide("d_units")

    z = xf._z
    accum = xf._combine(z(dh), z(du))
    return {
        "d_holders": z(dh),
        "d_units": z(du),
        "accum": accum,
    }


# ------------------------------------------------------------------ report
def report_factor(name, P, score, mask, split, n_trials):
    # L/S decile
    rls, to_ls = xf.backtest_factor(P, score, mask, long_only=False)
    # long-only top quintile (deployable)
    rlo, to_lo = xf.backtest_factor(P, score, mask, long_only=True, top_frac=0.2)
    out = []
    for tag, r, to in [("L/S decile", rls, to_ls), ("LO quintile", rlo, to_lo)]:
        full = xf.metrics(r)
        oos = xf.metrics(r[r.index >= split])
        p = xf.dsr(r, n_trials)
        lo5, med, hi95 = xf._block_bootstrap_sharpe(r[r.index >= split])
        out.append(dict(name=name, mode=tag, turn=to,
                        full_sharpe=full["sharpe"], full_t=full["t"], full_dd=full["dd"],
                        full_hit=full["hit"], full_n=full["n"],
                        oos_sharpe=oos["sharpe"], oos_t=oos["t"], oos_dd=oos["dd"],
                        oos_hit=oos["hit"], oos_n=oos["n"],
                        dsr=p, boot_lo=lo5, boot_med=med, boot_hi=hi95))
    return out


def backtest(mcap_floor: float = 2e9, oos_frac: float = 0.35):
    if not SF3_AGG.exists():
        print("ERROR: sf3_agg.parquet missing — run fetch first.")
        return
    tk, sep, sf1 = xf.load()
    P = xf.price_panel(sep)
    agg = pd.read_parquet(SF3_AGG)
    agg["calendardate"] = pd.to_datetime(agg["calendardate"])
    agg = agg.dropna(subset=["calendardate"])            # drop empty-ticker markers
    agg = agg[agg["n_holders"] > 0]
    print(f"price panel: {P.shape[0]} month-ends x {P.shape[1]} tickers "
          f"({P.index.min().date()} -> {P.index.max().date()})")
    print(f"SF3 agg: {len(agg)} ticker-quarter rows, {agg['calendardate'].nunique()} quarters "
          f"({pd.to_datetime(agg['calendardate']).min().date()} -> "
          f"{pd.to_datetime(agg['calendardate']).max().date()})")
    print(f"PIT LAG used: quarter-end + {PIT_LAG_DAYS} days (>45d 13F deadline, ~1 quarter)")

    fund = xf.pit_fundamentals(sep[["date", "ticker"]].drop_duplicates(), sf1)
    mcap = fund.pivot_table(index="date", columns="ticker", values="marketcap",
                            aggfunc="last").reindex(index=P.index, columns=P.columns)
    mask = (P >= xf.MIN_PRICE) & (mcap >= mcap_floor)
    print(f"tradable mask (>=${mcap_floor/1e9:.0f}B): avg {mask.sum(axis=1).mean():.0f} names/mo")

    scores = build_score(agg, P)
    sector = tk.drop_duplicates("ticker").set_index("ticker")["sicsector"]
    split = P.index[int(len(P) * (1 - oos_frac))]
    # coverage diagnostic
    cov = (~scores["accum"].where(mask).isna()).sum(axis=1)
    cov = cov[cov > 0]
    print(f"accum signal coverage: avg {cov.mean():.0f} names/mo over "
          f"{cov.index.min().date()} -> {cov.index.max().date()} ({len(cov)} months)")
    print(f"OOS split = {split.date()}\n")

    n_trials = 3  # d_holders, d_units, accum
    rows = []
    for nm in ["d_holders", "d_units", "accum"]:
        sn = xf.sector_neutralize(scores[nm], sector)
        rows += report_factor(nm, P, sn, mask, split, n_trials)

    hdr = (f"{'factor':<11}{'mode':<13}{'FULL Sh':>8}{'t':>6}{'maxDD':>8}{'hit':>6}"
           f"{'  OOS Sh':>8}{'t':>6}{'maxDD':>8}{'hit':>6}{'  DSR':>7}{'  bootCI90':>16}")
    print(hdr)
    print("-" * len(hdr))
    for r in rows:
        print(f"{r['name']:<11}{r['mode']:<13}"
              f"{r['full_sharpe']:>8.2f}{r['full_t']:>6.2f}{r['full_dd']*100:>7.1f}%{r['full_hit']:>5.0f}%"
              f"{r['oos_sharpe']:>8.2f}{r['oos_t']:>6.2f}{r['oos_dd']*100:>7.1f}%{r['oos_hit']:>5.0f}%"
              f"{r['dsr']:>7.3f}  [{r['boot_lo']:>5.2f},{r['boot_hi']:>5.2f}]")
    return rows


def main():
    tk, sep, sf1 = xf.load()
    fetch_sf3_agg(sf1, sep)
    print()
    backtest()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "backtest":
        backtest()
    else:
        main()
