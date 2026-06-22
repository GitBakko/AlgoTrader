"""Tier-2 decisive crypto test: DELTA-NEUTRAL funding (basis) harvest, leak-free.

The directional funding cross-section (test_crypto_funding.py) had a real OOS signal but
a -63% drawdown (naked-short squeezing alts). The structurally sound form removes the
price direction: hold LONG SPOT + SHORT PERP (delta-neutral) to collect funding with ~0
net price exposure. Symmetric: when trailing funding is negative, flip (long perp / short
spot) to still receive. Risk reduces to BASIS noise (spot vs perp divergence) + fees.

Per coin, perp leg weight w (decided from PAST funding, earns t->t+1 via shift):
  pnl = w*perp_ret + (-w)*spot_ret + (-w)*funding  =  w*(perp_ret - spot_ret) - w*funding
To harvest funding>0 we go short perp (w=-1) -> +funding, +(spot_ret-perp_ret) basis term.
Costs: BOTH legs each rebalance (perp taker ~4bp + spot taker ~10bp). Low turnover since
the funding sign is persistent. Spot + funding from Binance public API (no key).

Run: .venv/Scripts/python.exe scripts/ab/test_crypto_basis.py
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
SAPI = "https://api.binance.com/api/v3"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT",
           "DOGEUSDT", "SOLUSDT", "LINKUSDT", "DOTUSDT", "AVAXUSDT", "MATICUSDT",
           "ATOMUSDT", "UNIUSDT", "FILUSDT", "ETCUSDT", "XLMUSDT", "TRXUSDT",
           "EOSUSDT", "THETAUSDT", "AAVEUSDT", "ALGOUSDT", "NEARUSDT", "SANDUSDT",
           "MANAUSDT", "AXSUSDT", "FTMUSDT", "EGLDUSDT", "ICPUSDT", "XTZUSDT"]
PERP_FEE = 4e-4         # taker per side
SPOT_FEE = 1e-3         # taker per side (spot dearer)
COST_PER_TURN = PERP_FEE + SPOT_FEE   # both legs per unit perp-weight turnover
FUND_SIGN_WIN = 3       # days trailing funding to decide harvest direction
START = "2021-01-01"
N_TRIALS = 8
TRADING_DAYS = 365


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _klines(base, sym, lim) -> pd.Series:
    out, start = {}, 0
    while True:
        rows = _get(f"{base}/klines?symbol={sym}&interval=1d&limit={lim}&startTime={start}")
        if not rows:
            break
        for k in rows:
            out[pd.Timestamp(k[0], unit="ms").normalize()] = float(k[4])
        if len(rows) < lim:
            break
        start = rows[-1][0] + 86_400_000
        time.sleep(0.05)
    return pd.Series(out).sort_index()


def fetch_funding_daily(sym) -> pd.Series:
    recs, start = [], 1_546_300_800_000
    while True:
        rows = _get(f"{FAPI}/fundingRate?symbol={sym}&limit=1000&startTime={start}")
        if not rows:
            break
        for r in rows:
            recs.append((pd.Timestamp(r["fundingTime"], unit="ms").normalize(),
                         float(r["fundingRate"])))
        if len(rows) < 1000:
            break
        start = rows[-1]["fundingTime"] + 1
        time.sleep(0.05)
    if not recs:
        return pd.Series(dtype=float)
    return pd.DataFrame(recs, columns=["d", "f"]).groupby("d")["f"].sum().sort_index()


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


def metrics(daily, oos_start):
    def m(d):
        d = d.dropna()
        n = len(d)
        if n < 5:
            return (n, 0.0, 0.0, 0.0, 0.0)
        mean, sd = d.mean(), d.std(ddof=1)
        sh = mean / sd * np.sqrt(TRADING_DAYS) if sd > 0 else 0.0
        t = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
        eq = (1 + d).cumprod()
        dd = (eq / eq.cummax() - 1).min()
        return (n, sh, t, dd, mean * TRADING_DAYS)
    return m(daily), m(daily[daily.index >= oos_start])


def main():
    print("Downloading Binance perp+spot daily close + funding (no key)...")
    perp, spot, fund = {}, {}, {}
    for s in SYMBOLS:
        try:
            p = _klines(FAPI, s, 1500)
            sp = _klines(SAPI, s, 1000)
            f = fetch_funding_daily(s)
            if min(len(p), len(sp), len(f)) < 300:
                print(f"  {s:<9} thin (perp {len(p)}, spot {len(sp)}, fund {len(f)}) - skip")
                continue
            perp[s], spot[s], fund[s] = p, sp, f
        except Exception as e:  # noqa: BLE001
            print(f"  {s:<9} FAIL {type(e).__name__}: {str(e)[:50]}")
    print(f"loaded {len(perp)} coins")
    if len(perp) < 4:
        print("not enough"); return

    pp = pd.DataFrame(perp).sort_index().ffill(limit=3)
    pp = pp[pp.index >= pd.Timestamp(START)]
    sps = pd.DataFrame(spot).reindex(pp.index).ffill(limit=3)
    fmat = pd.DataFrame(fund).reindex(pp.index).fillna(0.0)
    perp_ret = pp.pct_change().clip(-0.4, 0.4)
    spot_ret = sps.pct_change().clip(-0.4, 0.4)
    oos = oos_split_date(pp, 0.35)
    print(f"panel: {pp.shape[1]} coins x {pp.shape[0]} days  "
          f"{pp.index.min().date()} -> {pp.index.max().date()}   OOS from {oos.date()}")

    # perp leg weight: harvest funding -> short perp when trailing funding>0 (w<0).
    sgn = np.sign(fmat.rolling(FUND_SIGN_WIN).mean())
    w_harvest = normalize_book(-sgn)                 # delta-neutral, symmetric harvest
    avail = (pp.notna() & sps.notna())
    w_static = normalize_book(-np.sign(pp * 0 + 1) * avail.astype(float))  # always short perp

    def run(w):
        w = w.reindex(index=pp.index, columns=pp.columns).fillna(0.0)
        basis = w.shift(1) * (perp_ret - spot_ret)          # delta-neutral leg P&L
        fnd = (-w.shift(1)) * fmat                           # funding received/paid
        cost = (w - w.shift(1)).abs() * COST_PER_TURN
        return (basis + fnd - cost).sum(axis=1)

    books = {"basis_harvest_sym": w_harvest, "basis_short_perp_static": w_static}
    print(f"\n{'strategy':<24}{'FULL Sh':>9}{'ann%':>7}{'boot 95% CI':>18}"
          f"{'PSR>0':>8}{'OOS Sh':>8}{'OOS t':>7}{'maxDD':>8}")
    trial_sh, primary = [], None
    for name, w in books.items():
        daily = run(w)
        ci = block_boot_ci(daily)
        (fn, fsh, ft, fdd, fan), (on, osh, ot, odd, oan) = metrics(daily, oos)
        trial_sh.append(fsh)
        if primary is None:
            primary = daily
        ci_s = f"[{ci[0]:+.2f},{ci[2]:+.2f}]" if ci is not None else "n/a"
        print(f"{name:<24}{fsh:>9.2f}{fan*100:>7.1f}{ci_s:>18}{psr(daily):>8.3f}"
              f"{osh:>8.2f}{ot:>7.2f}{fdd*100:>7.1f}%")

    sr_var = np.var(trial_sh, ddof=1) if len(trial_sh) > 1 else 0.25
    g = 0.5772
    z1 = norm.ppf(1 - 1.0 / N_TRIALS)
    z2 = norm.ppf(1 - 1.0 / (N_TRIALS * np.e))
    sr0 = np.sqrt(max(sr_var, 1e-6)) * ((1 - g) * z1 + g * z2)
    print(f"\nDeflated benchmark SR* (N_trials={N_TRIALS}) = {sr0:.2f}  "
          f"-> Deflated PSR (harvest vs SR*) = {psr(primary, sr_bench_annual=sr0):.3f}")
    print("\nGO if: OOS Sharpe > 0 AND boot 95% CI lower > 0 AND Deflated PSR > 0.95.")
    print("Delta-neutral -> compare maxDD vs the -63% of the directional version.")


if __name__ == "__main__":
    main()
