"""Tier-2 final crypto test: RISK-MANAGED directional funding-positioning signal.

The raw directional funding cross-section (short crowded-long / high-funding coins) had a
genuinely significant OOS edge (t~3) but a -63% drawdown: it carried net market beta
(short hot high-beta alts) and was unscaled. Standard risk management:
  1. BETA-NEUTRALIZE to the equal-weight crypto index (kills the short-squeeze beta).
  2. VOL-TARGET to a constant portfolio vol (caps the tail).
Question: does the OOS edge SURVIVE with a tradeable drawdown? Leak-free throughout
(weights from past funding + past betas/vols; P&L via shift(1)). Funding captured =
Binance perps (migration target). Reuses the downloaders from test_crypto_funding.

Run: .venv/Scripts/python.exe scripts/ab/test_crypto_funding_rm.py
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

from scripts.ab.harness import normalize_book, oos_split_date  # noqa: E402
from scripts.ab.test_crypto_funding import (  # noqa: E402
    COST, SYMBOLS, fetch_funding_daily, fetch_klines_daily,
)

TOP_K = 4
START = "2021-01-01"
FUND_WIN = 7
BETA_WIN = 60
VOL_WIN = 30
TARGET_VOL_ANN = 0.25
N_TRIALS = 10
TRADING_DAYS = 365


def xsec_book(score, top_k):
    w = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    for dt, row in score.iterrows():
        r = row.dropna()
        if len(r) < 2 * top_k:
            continue
        ranked = r.sort_values()
        w.loc[dt, ranked.index[:top_k]] = 1.0
        w.loc[dt, ranked.index[-top_k:]] = -1.0
    return normalize_book(w)


def beta_neutralize(w, beta):
    b = beta.reindex_like(w).fillna(1.0)
    lam = (w * b).sum(axis=1) / (b * b).sum(axis=1).replace(0, np.nan)
    wn = w - b.mul(lam, axis=0)
    return normalize_book(wn.fillna(0.0))


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
            return (0.0, 0.0, 0.0, 0.0)
        mean, sd = d.mean(), d.std(ddof=1)
        sh = mean / sd * np.sqrt(TRADING_DAYS) if sd > 0 else 0.0
        t = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
        eq = (1 + d).cumprod()
        dd = (eq / eq.cummax() - 1).min()
        return (sh, t, dd, mean * TRADING_DAYS)
    return m(daily), m(daily[daily.index >= oos_start])


def main():
    print("Downloading Binance perp daily close + funding...")
    px, fund = {}, {}
    for s in SYMBOLS:
        try:
            p, f = fetch_klines_daily(s), fetch_funding_daily(s)
            if min(len(p), len(f)) < 300:
                continue
            px[s], fund[s] = p, f
        except Exception:  # noqa: BLE001
            pass
    print(f"loaded {len(px)} coins")
    price = pd.DataFrame(px).sort_index().ffill(limit=3)
    price = price[price.index >= pd.Timestamp(START)]
    fmat = pd.DataFrame(fund).reindex(price.index).fillna(0.0)
    ret = price.pct_change().clip(-0.4, 0.4)
    cost_frac = pd.Series({s: COST.get(s, 6e-4) for s in price.columns})
    oos = oos_split_date(price, 0.35)
    print(f"panel: {price.shape[1]} coins x {price.shape[0]} days  "
          f"{price.index.min().date()} -> {price.index.max().date()}   OOS from {oos.date()}")

    mkt = ret.mean(axis=1)
    beta = (ret.rolling(BETA_WIN).corr(mkt)
            .mul(ret.rolling(BETA_WIN).std().div(mkt.rolling(BETA_WIN).std(), axis=0)))
    raw = xsec_book(fmat.rolling(FUND_WIN).mean().shift(1), TOP_K)
    w_bn = beta_neutralize(raw, beta.shift(1))

    def pnl(w, capture=True, stop=None):
        w = w.reindex(index=price.index, columns=price.columns).fillna(0.0)
        gross = w.shift(1) * ret
        if stop is not None:   # model per-coin daily stop: cap loss at -stop*|weight|
            gross = gross.clip(lower=-(stop * w.shift(1).abs()))
        net = gross - (w - w.shift(1)).abs() * cost_frac
        if capture:
            net = net + (-w.shift(1) * fmat)
        return net.sum(axis=1)

    # vol-target the beta-neutral book: scale by target/trailing-realized (lagged)
    base = pnl(w_bn, True)
    tgt_d = TARGET_VOL_ANN / np.sqrt(TRADING_DAYS)
    scale = (tgt_d / base.rolling(VOL_WIN).std()).shift(1).clip(0, 3).fillna(0.0)
    w_vt = w_bn.mul(scale, axis=0)

    books = {
        "raw_dollar_neutral": (raw, True, None),
        "beta_neutral": (w_bn, True, None),
        "beta_neutral_voltgt": (w_vt, True, None),
        "bn_voltgt_stop20": (w_vt, True, 0.20),
        "bn_voltgt_stop20_CFD": (w_vt, False, 0.20),
    }
    print(f"\n{'variant':<26}{'FULL Sh':>9}{'ann%':>7}{'boot 95% CI':>18}"
          f"{'OOS Sh':>8}{'OOS t':>7}{'OOSann%':>8}{'maxDD':>8}")
    trial_sh, primary = [], None
    for name, (w, cap, stop) in books.items():
        daily = pnl(w, cap, stop)
        ci = block_boot_ci(daily)
        (fsh, ft, fdd, fan), (osh, ot, odd, oan) = metrics(daily, oos)
        trial_sh.append(fsh)
        if name == "beta_neutral_voltgt":
            primary = daily
        ci_s = f"[{ci[0]:+.2f},{ci[2]:+.2f}]" if ci is not None else "n/a"
        print(f"{name:<26}{fsh:>9.2f}{fan*100:>7.1f}{ci_s:>18}"
              f"{osh:>8.2f}{ot:>7.2f}{oan*100:>8.1f}{fdd*100:>7.1f}%")

    sr_var = np.var(trial_sh, ddof=1) if len(trial_sh) > 1 else 0.25
    g = 0.5772
    z1 = norm.ppf(1 - 1.0 / N_TRIALS)
    z2 = norm.ppf(1 - 1.0 / (N_TRIALS * np.e))
    sr0 = np.sqrt(max(sr_var, 1e-6)) * ((1 - g) * z1 + g * z2)
    print(f"\nDeflated benchmark SR* (N_trials={N_TRIALS}) = {sr0:.2f}  "
          f"-> Deflated PSR (beta_neutral_voltgt vs SR*) = {psr(primary, sr_bench_annual=sr0):.3f}")
    print("\nGO if: OOS Sharpe>0 AND boot CI lower>0 AND Deflated PSR>0.95 AND maxDD tradeable.")
    print("Watch: does beta-neutral+vol-target cut the -63% DD while keeping the OOS edge?")


if __name__ == "__main__":
    main()
