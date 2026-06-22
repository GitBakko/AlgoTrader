"""Tier-2 (NEW hypothesis space): crypto perp FUNDING carry, leak-free.

Funding rate is the carry: a long perp PAYS funding when funding>0, a short RECEIVES it.
So funding is signed alpha (revenue for the correct side), NOT a flat cost. We test a
cross-sectional book: each day SHORT the highest trailing-funding coins (crowded longs,
+receive funding) and LONG the lowest/most-negative (crowded shorts, +receive funding),
dollar-neutral, from PAST funding only (leak-free; P&L uses weights.shift(1)).

Two worlds reported side by side:
  WITH funding  -> Binance perps (you actually receive/pay funding)   [migration target]
  PRICE-ONLY    -> Capital.com CFD (you do NOT receive funding)       [current venue]
The gap between them prices the alpha rationale of the Binance migration.

Data: Binance public futures API (no key). Daily close (klines 1d) + daily funding
(sum of the 3x 8h funding rates per day). Net of taker fee + half-spread per turnover.

Run: .venv/Scripts/python.exe scripts/ab/test_crypto_funding.py
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from scipy.stats import kurtosis, norm, skew  # noqa: E402

from scripts.ab.harness import normalize_book, oos_split_date  # noqa: E402

FAPI = "https://fapi.binance.com/fapi/v1"
# broad liquid perp universe (cross-sectional needs breadth; thin/short ones auto-dropped)
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT",
           "DOGEUSDT", "SOLUSDT", "LINKUSDT", "DOTUSDT", "AVAXUSDT", "MATICUSDT",
           "ATOMUSDT", "UNIUSDT", "FILUSDT", "ETCUSDT", "XLMUSDT", "TRXUSDT",
           "EOSUSDT", "THETAUSDT", "AAVEUSDT", "ALGOUSDT", "NEARUSDT", "SANDUSDT",
           "MANAUSDT", "AXSUSDT", "FTMUSDT", "EGLDUSDT", "ICPUSDT", "XTZUSDT"]
# half cost per unit turnover = taker fee 0.04% + half-spread (round-trip ~= 2x)
COST = {"BTCUSDT": 4.5e-4, "ETHUSDT": 4.5e-4, "BNBUSDT": 5e-4, "XRPUSDT": 5.5e-4,
        "LTCUSDT": 5.5e-4, "ADAUSDT": 5.5e-4, "DOGEUSDT": 6e-4, "SOLUSDT": 5.5e-4,
        "LINKUSDT": 6e-4, "DOTUSDT": 6e-4, "AVAXUSDT": 6e-4}
TOP_K = 4
START = "2021-01-01"   # broad liquidity across the alt set from ~2021
N_TRIALS = 8           # funding windows x worlds x universe choice -> DSR honesty
TRADING_DAYS = 365     # crypto trades 24/7


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def fetch_klines_daily(sym: str) -> pd.Series:
    out = {}
    start = 0
    while True:
        url = f"{FAPI}/klines?symbol={sym}&interval=1d&limit=1500&startTime={start}"
        rows = _get(url)
        if not rows:
            break
        for k in rows:
            out[pd.Timestamp(k[0], unit="ms").normalize()] = float(k[4])  # close
        if len(rows) < 1500:
            break
        start = rows[-1][0] + 86_400_000
        time.sleep(0.1)
    return pd.Series(out).sort_index()


def fetch_funding_daily(sym: str) -> pd.Series:
    """Sum of 8h funding rates per day (= daily funding paid by a long)."""
    recs = []
    start = 1_546_300_800_000  # 2019-01-01; startTime=0 makes Binance return only recent 200
    while True:
        url = f"{FAPI}/fundingRate?symbol={sym}&limit=1000&startTime={start}"
        rows = _get(url)
        if not rows:
            break
        for r in rows:
            recs.append((pd.Timestamp(r["fundingTime"], unit="ms").normalize(),
                         float(r["fundingRate"])))
        if len(rows) < 1000:
            break
        start = rows[-1]["fundingTime"] + 1
        time.sleep(0.1)
    if not recs:
        return pd.Series(dtype=float)
    s = pd.DataFrame(recs, columns=["date", "f"]).groupby("date")["f"].sum()
    return s.sort_index()


def xsec_book(score: pd.DataFrame, top_k: int) -> pd.DataFrame:
    w = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    for dt, row in score.iterrows():
        r = row.dropna()
        if len(r) < 2 * top_k:
            continue
        ranked = r.sort_values()
        w.loc[dt, ranked.index[:top_k]] = 1.0    # lowest funding -> LONG
        w.loc[dt, ranked.index[-top_k:]] = -1.0  # highest funding -> SHORT (receive)
    return normalize_book(w)


def block_boot_ci(daily, n_boot=3000, block=14, seed=0):
    a = daily.dropna().to_numpy()
    n = len(a)
    if n < block * 5:
        return None
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    out = np.empty(n_boot)
    for k in range(n_boot):
        starts = rng.integers(0, n, size=nb)
        idx = (starts[:, None] + np.arange(block)).ravel()[:n] % n
        s = a[idx]
        sd = s.std(ddof=1)
        out[k] = (s.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0
    return np.percentile(out, [2.5, 50, 97.5])


def psr(daily, sr_bench_annual=0.0):
    a = daily.dropna().to_numpy()
    n = len(a)
    sd = a.std(ddof=1)
    if sd == 0:
        return 0.0
    sr = a.mean() / sd
    sr_b = sr_bench_annual / np.sqrt(TRADING_DAYS)
    sk, ku = skew(a), kurtosis(a, fisher=False)
    denom = np.sqrt(max(1e-9, 1 - sk * sr + (ku - 1) / 4 * sr**2))
    z = (sr - sr_b) * np.sqrt(n - 1) / denom
    return float(norm.cdf(z))


def metrics(daily: pd.Series, oos_start):
    def m(d):
        d = d.dropna()
        n = len(d)
        if n < 5:
            return (n, 0.0, 0.0, 0.0)
        mean, sd = d.mean(), d.std(ddof=1)
        sh = mean / sd * np.sqrt(TRADING_DAYS) if sd > 0 else 0.0
        t = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
        eq = (1 + d).cumprod()
        dd = (eq / eq.cummax() - 1).min()
        return (n, sh, t, dd)
    full = m(daily)
    oos = m(daily[daily.index >= oos_start])
    return full, oos


def main():
    print("Downloading Binance perp daily close + funding (no key)...")
    px, fund = {}, {}
    for s in SYMBOLS:
        try:
            p = fetch_klines_daily(s)
            f = fetch_funding_daily(s)
            if len(p) < 200 or len(f) < 200:
                print(f"  {s:<9} thin (px {len(p)}, fund {len(f)}) - skip")
                continue
            px[s], fund[s] = p, f
            print(f"  {s:<9} px {len(p):>4} ({p.index.min().date()}->{p.index.max().date()})  "
                  f"fund {len(f):>4}  mean {f.mean()*1e4:+.2f}bp/day")
        except Exception as e:  # noqa: BLE001
            print(f"  {s:<9} FAIL {type(e).__name__}: {str(e)[:60]}")
    if len(px) < 2 * TOP_K:
        print("not enough symbols"); return

    price = pd.DataFrame(px).sort_index().ffill(limit=3)
    price = price[price.index >= pd.Timestamp(START)]
    fmat = pd.DataFrame(fund).reindex(price.index).fillna(0.0)
    ret = price.pct_change().clip(-0.4, 0.4)
    cost_frac = pd.Series({s: COST.get(s, 6e-4) for s in price.columns})
    oos = oos_split_date(price, 0.35)
    print(f"\npanel: {price.shape[1]} coins x {price.shape[0]} days  "
          f"{price.index.min().date()} -> {price.index.max().date()}   OOS from {oos.date()}")

    def run(w: pd.DataFrame, capture_funding: bool) -> pd.Series:
        w = w.reindex(index=price.index, columns=price.columns).fillna(0.0)
        gross = w.shift(1) * ret
        cost = (w - w.shift(1)).abs() * cost_frac
        net = gross - cost
        if capture_funding:
            net = net + (-w.shift(1) * fmat)   # short of +funding earns funding
        return net.sum(axis=1)

    books = {
        "fund_xs_7d": xsec_book(fmat.rolling(7).mean().shift(1), TOP_K),
        "fund_xs_30d": xsec_book(fmat.rolling(30).mean().shift(1), TOP_K),
    }
    print(f"\n{'signal':<13}{'world':<13}{'FULL Sh':>9}{'boot 95% CI':>18}"
          f"{'PSR>0':>8}{'OOS Sh':>8}{'OOS t':>7}{'maxDD':>8}")
    trial_sh, primary = [], None
    for name, w in books.items():
        for cap, lbl in [(True, "Binance+fund"), (False, "CFD price-only")]:
            daily = run(w, cap)
            ci = block_boot_ci(daily)
            (fn, fsh, ft, fdd), (on, osh, ot, odd) = metrics(daily, oos)
            trial_sh.append(fsh)
            if cap and primary is None:
                primary = daily
            ci_s = f"[{ci[0]:+.2f},{ci[2]:+.2f}]" if ci is not None else "n/a"
            print(f"{name:<13}{lbl:<13}{fsh:>9.2f}{ci_s:>18}{psr(daily):>8.3f}"
                  f"{osh:>8.2f}{ot:>7.2f}{fdd*100:>7.1f}%")

    sr_var = np.var(trial_sh, ddof=1) if len(trial_sh) > 1 else 0.25
    g = 0.5772
    z1 = norm.ppf(1 - 1.0 / N_TRIALS)
    z2 = norm.ppf(1 - 1.0 / (N_TRIALS * np.e))
    sr0 = np.sqrt(max(sr_var, 1e-6)) * ((1 - g) * z1 + g * z2)
    dsr = psr(primary, sr_bench_annual=sr0)
    print(f"\nDeflated benchmark SR* (N_trials={N_TRIALS}) = {sr0:.2f}  "
          f"-> Deflated PSR (Binance+fund 7d vs SR*) = {dsr:.3f}")
    print("\nGO if: OOS Sharpe > 0 AND boot 95% CI lower > 0 AND Deflated PSR > 0.95.")
    print("Read the Binance+fund vs CFD price-only gap = the funding-capture alpha")
    print("you forfeit by staying on Capital.com CFD.")


if __name__ == "__main__":
    main()
