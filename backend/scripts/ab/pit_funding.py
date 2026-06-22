"""SURVIVORSHIP TEST: directional funding cross-section on a point-in-time universe.

The validated-raw lead (OOS Sharpe ~2.2-2.4) was measured on 30 coins that SURVIVE to
today. Killer #1: is the edge real or a survivor artifact? This reruns the SAME signal
(short high trailing funding / long low, dollar-neutral, leak-free) on the
survivorship-free universe from fetch_crypto_perp_universe.py — every perp that ever
traded, alive on a date iff it has data there (dead coins live during their life, drop
after delisting). A realistic per-date liquidity floor (trailing USDT volume) keeps the
book tradable.

Compares SURVIVOR-30 vs PIT-FULL on identical engine. Reports full+OOS Sharpe, t, maxDD,
Deflated PSR (honest trial count), block-bootstrap CI.

  GO signal: OOS Sharpe survives on PIT-FULL with CI lower > 0.  (DD + DSR handled next.)
  KILL signal: PIT-FULL OOS collapses toward 0 -> the edge was survivorship.

Run: .venv/Scripts/python.exe scripts/ab/pit_funding.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from scipy.stats import kurtosis, norm, skew  # noqa: E402

from scripts.ab.harness import normalize_book  # noqa: E402

CACHE = ROOT / "data" / "crypto_perp"
TRADING_DAYS = 365
START = "2021-01-01"          # match the validated baseline window
FUND_WIN = 7                  # VALIDATED param — not swept
MIN_AGE = 21                  # days listed before tradable (drop listing-day noise)
RET_CLIP = 0.40               # conservative daily return cap (collapses/squeezes)
COST = 6e-4                   # taker + half-spread per unit turnover

# the original survivor set (test_crypto_funding.py) — today's survivors
SURVIVOR_30 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT",
               "DOGEUSDT", "SOLUSDT", "LINKUSDT", "DOTUSDT", "AVAXUSDT", "MATICUSDT",
               "ATOMUSDT", "UNIUSDT", "FILUSDT", "ETCUSDT", "XLMUSDT", "TRXUSDT",
               "EOSUSDT", "THETAUSDT", "AAVEUSDT", "ALGOUSDT", "NEARUSDT", "SANDUSDT",
               "MANAUSDT", "AXSUSDT", "FTMUSDT", "EGLDUSDT", "ICPUSDT", "XTZUSDT"]


def load_panels():
    k = pd.read_parquet(CACHE / "klines_daily.parquet")
    f = pd.read_parquet(CACHE / "funding_daily.parquet")
    k["date"] = pd.to_datetime(k["date"])
    f["date"] = pd.to_datetime(f["date"])
    price = k.pivot_table(index="date", columns="symbol", values="close").sort_index()
    qvol = k.pivot_table(index="date", columns="symbol", values="qvol").sort_index()
    fund = f.pivot_table(index="date", columns="symbol", values="funding").sort_index()
    idx = price.index
    fund = fund.reindex(idx)
    qvol = qvol.reindex(idx)
    return price, qvol, fund


def pit_mask(price, qvol, liq_usd, min_age=MIN_AGE):
    """Boolean [date x sym]: tradable iff alive (price+listed), aged, and liquid."""
    alive = price.notna()
    # age: count of prior valid prices >= min_age
    aged = alive.cumsum() >= min_age
    liq = qvol.rolling(14, min_periods=7).median().shift(1) >= liq_usd
    return alive & aged & liq.reindex_like(alive).fillna(False)


def xsec_book(score, mask, top_frac):
    """Short highest trailing funding, long lowest, within the tradable mask."""
    w = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    sc = score.where(mask)
    for dt, row in sc.iterrows():
        r = row.dropna()
        k = int(len(r) * top_frac)
        if k < 2 or len(r) < 2 * k:
            continue
        ranked = r.sort_values()
        w.loc[dt, ranked.index[:k]] = 1.0     # lowest funding -> LONG
        w.loc[dt, ranked.index[-k:]] = -1.0    # highest funding -> SHORT (receive)
    return normalize_book(w)


def backtest(price, fund, w, capture_funding=True, cost=COST):
    ret = price.pct_change().clip(-RET_CLIP, RET_CLIP)
    w = w.reindex(index=price.index, columns=price.columns).fillna(0.0)
    gross = w.shift(1) * ret
    turn = (w - w.shift(1)).abs()
    net = gross - turn * cost
    if capture_funding:
        net = net + (-w.shift(1) * fund.reindex_like(w).fillna(0.0))
    return net.sum(axis=1), turn.sum(axis=1)


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
    return float(norm.cdf((sr - sr_b) * np.sqrt(n - 1) / denom))


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


def deflated_sr(primary, trial_sharpes, n_trials):
    sr_var = np.var(trial_sharpes, ddof=1) if len(trial_sharpes) > 1 else 0.25
    g = 0.5772
    z1 = norm.ppf(1 - 1.0 / n_trials)
    z2 = norm.ppf(1 - 1.0 / (n_trials * np.e))
    sr0 = np.sqrt(max(sr_var, 1e-6)) * ((1 - g) * z1 + g * z2)
    return psr(primary, sr_bench_annual=sr0), sr0


def main():
    price, qvol, fund = load_panels()
    price = price[price.index >= pd.Timestamp(START)]
    qvol = qvol.reindex(price.index)
    fund = fund.reindex(price.index)
    n_obs = len(price.index)
    oos = price.index[int(n_obs * 0.65)]
    print(f"cache: {price.shape[1]} symbols x {n_obs} days  "
          f"{price.index.min().date()} -> {price.index.max().date()}  OOS from {oos.date()}")

    score = fund.rolling(FUND_WIN).mean().shift(1)

    configs = []
    # SURVIVOR-30 baseline (reproduce the ~2.2-2.4 OOS anchor)
    surv_cols = [s for s in SURVIVOR_30 if s in price.columns]
    surv_mask = price[surv_cols].notna() & (price[surv_cols].notna().cumsum() >= MIN_AGE)
    surv_mask = surv_mask.reindex(columns=price.columns, fill_value=False)
    configs.append(("SURVIVOR-30 +fund", surv_mask, 0.14, True))
    configs.append(("SURVIVOR-30 CFD", surv_mask, 0.14, False))
    # PIT-FULL at liquidity floors x operating points
    for liq, tag in [(3e6, "liq3M"), (10e6, "liq10M")]:
        m = pit_mask(price, qvol, liq)
        avg_n = m.sum(axis=1).mean()
        configs.append((f"PIT {tag} dec", m, 0.10, True, avg_n))
        configs.append((f"PIT {tag} qnt", m, 0.20, True, avg_n))
    # CFD price-only world on the champion liq floor (current venue, no funding capture)
    m3 = pit_mask(price, qvol, 3e6)
    configs.append(("PIT liq3M dec CFD", m3, 0.10, False))

    print(f"\n{'config':<20}{'avgN':>6}{'FULL Sh':>9}{'boot95 CI':>17}"
          f"{'PSR':>6}{'OOS Sh':>8}{'OOS t':>7}{'OOSann':>8}{'maxDD':>8}")
    trial_sh, primary = [], None
    rows = []
    for cfg in configs:
        name, mask, frac, cap = cfg[0], cfg[1], cfg[2], cfg[3]
        avg_n = cfg[4] if len(cfg) > 4 else mask.sum(axis=1).mean()
        w = xsec_book(score, mask, frac)
        daily, turn = backtest(price, fund, w, capture_funding=cap)
        ci = block_boot_ci(daily)
        (fn, fsh, ft, fdd, fan), (on, osh, ot, odd, oan) = metrics(daily, oos)
        trial_sh.append(fsh)
        if name == "PIT liq3M dec" and primary is None:
            primary = daily
        ci_s = f"[{ci[0]:+.2f},{ci[2]:+.2f}]" if ci is not None else "n/a"
        print(f"{name:<20}{avg_n:>6.0f}{fsh:>9.2f}{ci_s:>17}{psr(daily):>6.2f}"
              f"{osh:>8.2f}{ot:>7.2f}{oan*100:>7.0f}%{fdd*100:>7.0f}%")
        rows.append((name, daily, osh))
    if primary is None:
        primary = rows[1][1]
    dsr, sr0 = deflated_sr(primary, trial_sh, n_trials=max(8, len(configs)))
    print(f"\nDeflated SR* (N_trials={max(8,len(configs))}) = {sr0:.2f}  "
          f"-> Deflated PSR (PIT liq3M dec) = {dsr:.3f}")
    print("\nKILL if PIT-FULL OOS Sharpe collapses vs SURVIVOR-30 (edge was survivorship).")
    print("PROMOTE if PIT-FULL OOS Sharpe holds with boot CI lower > 0 (real edge);")
    print("then tackle the -54% DD (killer #2) + DSR>0.95 (killer #3).")


if __name__ == "__main__":
    main()
