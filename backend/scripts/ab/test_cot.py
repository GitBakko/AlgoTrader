"""Candidate #3: COT COMMERCIAL-HEDGER POSITIONING on gold/WTI/natgas (leak-free A/B).

Hypothesis (Dreesmann 2023; Basu 2006): commercial hedgers are the "smart money". When their
net position hits an extreme in its trailing 3yr range (COT_Index), price tends to follow:
extreme commercial NET-LONG (index>80) = bullish, extreme NET-SHORT (index<20) = bearish.

Leak discipline: COT is as-of Tuesday, PUBLISHED Friday. We compute COT_Index from the
commercial net (Tuesday) and only act the FOLLOWING week (shift), so the signal was public.
Weekly bars, net of CFD cost. Per-commodity + equal-weight pool. OOS=last 35%. Deflated Sharpe
+ bootstrap. GO if pooled OOS Sharpe>0, bootCI lower>0, DSR>0.95, vs buy&hold.

Run: .venv/Scripts/python.exe scripts/ab/test_cot.py
"""

from __future__ import annotations

import io
import sys
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "ab"))
sys.stdout.reconfigure(encoding="utf-8")

from factory_stats import block_boot_ci, deflated_sr, line, metrics  # noqa: E402

CACHE = ROOT / "data" / "cot"
CACHE.mkdir(parents=True, exist_ok=True)
PPY = 52
COST = 5e-4
OOS_FRAC = 0.35
LOOKBACK = 156  # weeks (3yr)

MARKETS = {
    "gold": ("GOLD - COMMODITY EXCHANGE INC.", "GC=F"),
    "wti": ("CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE", "CL=F"),
    "natgas": ("NATURAL GAS - NEW YORK MERCANTILE EXCHANGE", "NG=F"),
}


def fetch_cot() -> pd.DataFrame:
    pq = CACHE / "cot_commercial.parquet"
    if pq.exists():
        return pd.read_parquet(pq)
    rows = []
    names = {v[0] for v in MARKETS.values()}
    for year in range(2000, 2027):
        try:
            url = f"https://www.cftc.gov/files/dea/history/deacot{year}.zip"
            raw = urllib.request.urlopen(
                urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
            z = zipfile.ZipFile(io.BytesIO(raw))
            df = pd.read_csv(z.open(z.namelist()[0]), low_memory=False)
            df.columns = [c.strip() for c in df.columns]
            mkt_col = "Market and Exchange Names"
            # prefer the ISO 'YYYY-MM-DD' date column; parse as date string (NOT epoch ns)
            date_col = (next((c for c in df.columns if "YYYY-MM-DD" in c), None)
                        or next(c for c in df.columns if "Date" in c))
            sub = df[df[mkt_col].isin(names)].copy()
            sub["date"] = pd.to_datetime(sub[date_col].astype(str), errors="coerce")
            sub = sub.dropna(subset=["date"])
            for _, r in sub.iterrows():
                rows.append((r["date"], r[mkt_col],
                             float(r["Commercial Positions-Long (All)"]),
                             float(r["Commercial Positions-Short (All)"]),
                             float(r["Open Interest (All)"])))
            print(f"  {year}: {len(sub)} rows", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  {year}: FAIL {type(e).__name__} {str(e)[:50]}", flush=True)
    out = pd.DataFrame(rows, columns=["date", "market", "comm_long", "comm_short", "oi"])
    out.to_parquet(pq, index=False)
    return out


def main():
    print("Fetching CFTC COT (cached)...")
    cot = fetch_cot()
    name2key = {v[0]: k for k, v in MARKETS.items()}
    cot["key"] = cot["market"].map(name2key)
    cot["net"] = cot["comm_long"] - cot["comm_short"]

    pooled = {}
    bh_pooled = {}
    trial_sh = []
    print(f"\n{'commodity':<10} per-commodity weekly L/S (contrarian on commercial extremes)")
    for key, (mname, ticker) in MARKETS.items():
        c = cot[cot["key"] == key].sort_values("date").set_index("date")["net"]
        c = c[~c.index.duplicated()]
        # COT_Index over trailing LOOKBACK weeks (leak-free: uses only past)
        lo = c.rolling(LOOKBACK, min_periods=52).min()
        hi = c.rolling(LOOKBACK, min_periods=52).max()
        idx = (c - lo) / (hi - lo).replace(0, np.nan) * 100
        # signal: long if commercials extreme net-long, short if extreme net-short
        sig = pd.Series(0.0, index=idx.index)
        sig[idx > 80] = 1.0
        sig[idx < 20] = -1.0
        # prices -> weekly (Fri) returns; COT(Tue) known by Fri -> act next week (shift)
        px = yf.download(ticker, start="1999-06-01", progress=False, auto_adjust=False)["Close"]
        px = (px[px.columns[0]] if isinstance(px, pd.DataFrame) else px).dropna()
        px.index = pd.to_datetime(px.index)
        wpx = px.resample("W-FRI").last()
        wret = wpx.pct_change()
        # align weekly: reindex signal onto weekly price dates (ffill the weekly COT), shift 1wk
        sig_w = sig.reindex(wret.index, method="ffill").shift(1)
        r = (sig_w * wret - sig_w.diff().abs().fillna(0) * COST).dropna()
        pooled[key] = r
        bh_pooled[key] = wret.reindex(r.index)
        m = metrics(r, PPY)
        trial_sh.append(m["sharpe"])
        print(line(key, m, f"  trades/yr~{int(sig_w.diff().abs().sum()/ (len(r)/PPY))}"))

    # equal-weight pool of the 3 contrarian books
    pool = pd.concat(pooled, axis=1).mean(axis=1).dropna()
    bh = pd.concat(bh_pooled, axis=1).mean(axis=1).reindex(pool.index)
    oos = pool.index[int(len(pool) * (1 - OOS_FRAC))]
    print(f"\nPOOL (eq-wt gold+wti+natgas), {len(pool)} weeks, OOS from {oos.date()}")
    mf = metrics(pool, PPY); mo = metrics(pool[pool.index >= oos], PPY)
    ci = block_boot_ci(pool[pool.index >= oos], PPY, block=8)
    print(line("pool FULL", mf)); print(line("pool OOS", mo, f"  bootCI[{ci[0]:+.2f},{ci[2]:+.2f}]"))
    print(line("buy&hold-pool OOS", metrics(bh[bh.index >= oos], PPY)))
    dsr, sr0 = deflated_sr(pool, trial_sh + [mf["sharpe"]], PPY)
    print(f"\nDeflated SR* (N={len(trial_sh)+1}) = {sr0:.2f} -> Deflated PSR (pool) = {dsr:.3f}")
    print("GO if pool OOS Sharpe>0 AND bootCI lower>0 AND DSR>0.95 AND beats buy&hold.")


if __name__ == "__main__":
    main()
