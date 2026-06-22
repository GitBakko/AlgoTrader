"""Deeper TSMOM confirmation on LONG daily history (yfinance, years) with honest
significance (block-bootstrap Sharpe CI + Probabilistic Sharpe Ratio).

Daily TSMOM is structurally leak-resistant (single-timeframe, sign of PAST returns,
close-to-close via the shared backtester). The Tier-1 run was positive but
underpowered (~2.5y). Here we use max yfinance daily history and test whether the
edge is statistically real, not just a short-sample blip.

Run: .venv/Scripts/python.exe scripts/ab/deeper_tsmom.py
"""

from __future__ import annotations

import logging
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")
warnings.filterwarnings("ignore")
for _n in ("sqlalchemy.engine", "src", "yfinance", "urllib3", "peewee"):
    logging.getLogger(_n).setLevel(logging.ERROR)

import yfinance as yf  # noqa: E402
from scipy.stats import kurtosis, norm, skew  # noqa: E402

from scripts.ab.harness import DailyBacktester, normalize_book, oos_split_date  # noqa: E402
from src.backtest.costs import ASSET_SPREADS  # noqa: E402
from src.data.ticker_mapping import TickerMapper  # noqa: E402
from src.utils.constants import TRADABLE_ASSETS  # noqa: E402

START = "2012-01-01"   # avoid ancient (pre-modern-scale) data + worst glitches
RET_CLIP = 0.5         # winsorize daily glitches (early-crypto yfinance spikes)

VOL_WINDOW = 20
TARGET_VOL = 0.15
MAX_LEV = 3.0
CONFIGS = {                       # lookback sets (trading days) — primary first
    "blend_1_3_12m": [21, 63, 252],
    "12m_only": [252],
    "3_12m": [63, 252],
    "1_3_6m": [21, 63, 126],
}
N_TRIALS = 8                      # configs tried across this + earlier TSMOM run (DSR honesty)


def load_yf_daily(epics: list[str]) -> pd.DataFrame:
    series = {}
    for e in epics:
        yt = TickerMapper.to_yfinance(e)
        if not yt:
            continue
        try:
            df = yf.download(yt, period="max", interval="1d", auto_adjust=True,
                             progress=False, threads=False)
            if df is None or df.empty:
                print(f"  {e} ({yt}): empty"); continue
            close = df["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close.index = pd.to_datetime(close.index).tz_localize(None).normalize()
            series[e] = close.dropna()
            print(f"  {e:<9} ({yt:<8}) {len(series[e]):>5} days  {series[e].index.min().date()} -> {series[e].index.max().date()}")
        except Exception as ex:  # noqa: BLE001
            print(f"  {e} ({yt}): {ex!r}")
    px = pd.DataFrame(series).sort_index().ffill(limit=7)
    return px


def tsmom_weights(prices: pd.DataFrame, lookbacks: list[int]) -> pd.DataFrame:
    ret = prices.pct_change()
    sig = sum(np.sign(prices / prices.shift(lb) - 1.0) for lb in lookbacks) / len(lookbacks)
    rvol = ret.rolling(VOL_WINDOW).std() * np.sqrt(252)
    w = (sig * (TARGET_VOL / rvol).clip(upper=MAX_LEV)).clip(-MAX_LEV, MAX_LEV)
    return normalize_book(w)


def block_boot_ci(daily: pd.Series, n_boot=3000, block=21, seed=0):
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
        out[k] = (s.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    return np.percentile(out, [2.5, 50, 97.5])


def psr(daily: pd.Series, sr_bench_annual=0.0):
    a = daily.dropna().to_numpy()
    n = len(a)
    sd = a.std(ddof=1)
    if sd == 0:
        return 0.0
    sr = a.mean() / sd                       # daily SR
    sr_b = sr_bench_annual / np.sqrt(252)
    sk, ku = skew(a), kurtosis(a, fisher=False)
    denom = np.sqrt(max(1e-9, 1 - sk * sr + (ku - 1) / 4 * sr**2))
    z = (sr - sr_b) * np.sqrt(n - 1) / denom
    return float(norm.cdf(z))


def main():
    print("Downloading long daily history (yfinance)...")
    px = load_yf_daily(TRADABLE_ASSETS)
    px = px.dropna(how="all")
    px = px[px.index >= pd.Timestamp(START)]
    print(f"\npanel: {px.shape[1]} assets x {px.shape[0]} days  "
          f"{px.index.min().date()} -> {px.index.max().date()}")
    # Stable proportional cost: spread-in-bps anchored to CURRENT price, applied
    # across history (spreads track price level over time, the absolute value does not).
    cur = px.ffill().iloc[-1]
    cost_bps = {
        e: (ASSET_SPREADS.get(e, cur[e] * 0.0008) / cur[e]) * 0.5 * 1.10
        for e in px.columns
    }
    bt = DailyBacktester(px, cost_bps=cost_bps, ret_clip=RET_CLIP)
    oos = oos_split_date(px, 0.3)

    print(f"\n{'config':<14}{'FULL Sharpe':>12}{'boot 95% CI':>22}{'PSR>0':>8}{'OOS Sh':>8}{'maxDD':>8}")
    trial_sharpes = []
    primary_daily = None
    for name, lbs in CONFIGS.items():
        w = tsmom_weights(px, lbs)
        res = bt.run(w, oos)
        daily = res["daily"]
        ci = block_boot_ci(daily)
        p = psr(daily[daily.index >= daily.dropna().index[0]])
        full, oosm = res["full"], res["oos"]
        trial_sharpes.append(full.sharpe)
        if primary_daily is None:
            primary_daily = daily
        ci_s = f"[{ci[0]:+.2f}, {ci[2]:+.2f}]" if ci is not None else "n/a"
        print(f"{name:<14}{full.sharpe:>12.2f}{ci_s:>22}{p:>8.3f}{oosm.sharpe:>8.2f}{full.max_dd*100:>7.1f}%")

    # Deflated benchmark: expected max Sharpe from N independent trials
    sr_var = np.var(trial_sharpes, ddof=1) if len(trial_sharpes) > 1 else 0.25
    gamma = 0.5772
    z1 = norm.ppf(1 - 1.0 / N_TRIALS)
    z2 = norm.ppf(1 - 1.0 / (N_TRIALS * np.e))
    sr0 = np.sqrt(max(sr_var, 1e-6)) * ((1 - gamma) * z1 + gamma * z2)   # annualized deflated SR*
    dsr = psr(primary_daily, sr_bench_annual=sr0)
    print(f"\nDeflated benchmark SR* (N_trials={N_TRIALS}) = {sr0:.2f}  "
          f"-> Deflated PSR (primary vs SR*) = {dsr:.3f}")
    print("\nGO if: boot 95% CI lower bound > 0 AND Deflated PSR > 0.95.")
    print("(Costs use CURRENT measured spreads — slightly optimistic for old history;")
    print(" TSMOM turnover is low so impact is small.)")


if __name__ == "__main__":
    main()
