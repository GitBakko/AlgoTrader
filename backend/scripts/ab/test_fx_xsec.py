"""Tier-2 (NEW hypothesis space): FX cross-sectional momentum + value, leak-free.

Tier-1 rejected directional ML / pairs / TSMOM on our 18 CFD assets. This opens the
FIRST untested avenue from the data-API analysis: a WIDER universe enabling REAL
cross-sectional. 13 liquid currencies vs USD (yfinance daily, ~2004-2026, free).

Cross-sectional, dollar-neutral, leak-free by construction (weights from PAST data,
DailyBacktester applies weights.shift(1)). Long top-k / short bottom-k each day.
Signals: 12-1m momentum, 5y reversal (value / PPP proxy), and their z-combo.
Carry (the classic FX edge) is NOT here yet -> needs rate differentials (FRED); it is
added in Phase 1b only if these price signals show life. Financing forced to 0 so this
isolates the PRICE signal (a flat default swap would wrongly tax both legs of an L/S book).

Run: .venv/Scripts/python.exe scripts/ab/test_fx_xsec.py
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
for _n in ("yfinance", "urllib3"):
    logging.getLogger(_n).setLevel(logging.ERROR)

import yfinance as yf  # noqa: E402
from scipy.stats import kurtosis, norm, skew  # noqa: E402

from scripts.ab.harness import DailyBacktester, normalize_book, oos_split_date  # noqa: E402

START = "2004-01-01"
RET_CLIP = 0.2          # daily FX moves rarely exceed this; kills EM inversion glitches
TOP_K = 3               # long top-3, short bottom-3 currencies
N_TRIALS = 6            # mom, value, combo (+ headroom for carry variants) -> DSR honesty

# currency vs USD. DIRECT pairs are already XXXUSD; INVERT pairs are USDxxx so 1/price.
DIRECT = {"EUR": "EURUSD=X", "GBP": "GBPUSD=X", "AUD": "AUDUSD=X", "NZD": "NZDUSD=X"}
INVERT = {"JPY": "USDJPY=X", "CAD": "USDCAD=X", "CHF": "USDCHF=X",
          "MXN": "USDMXN=X", "ZAR": "USDZAR=X", "SEK": "USDSEK=X",
          "NOK": "USDNOK=X", "SGD": "USDSGD=X", "TRY": "USDTRY=X"}
# half-spread fraction per unit turnover (retail FX; EM wider). Round-trip ~= 2x.
COST = {"EUR": 5e-5, "GBP": 6e-5, "AUD": 7e-5, "NZD": 1e-4, "JPY": 6e-5,
        "CAD": 7e-5, "CHF": 7e-5, "MXN": 4e-4, "ZAR": 6e-4, "SEK": 2e-4,
        "NOK": 2e-4, "SGD": 1.5e-4, "TRY": 1.5e-3}


def _dl(t: str) -> pd.Series:
    d = yf.download(t, period="max", interval="1d", auto_adjust=True,
                    progress=False, threads=False)
    c = d["Close"]
    if isinstance(c, pd.DataFrame):
        c = c.iloc[:, 0]
    c.index = pd.to_datetime(c.index).tz_localize(None).normalize()
    return c.dropna()


def load_ccy_vs_usd() -> pd.DataFrame:
    series: dict[str, pd.Series] = {}
    for ccy, t in DIRECT.items():
        series[ccy] = _dl(t)
    for ccy, t in INVERT.items():
        series[ccy] = 1.0 / _dl(t)
    px = pd.DataFrame(series).sort_index().ffill(limit=5)
    return px[px.index >= pd.Timestamp(START)]


def xsec_book(score: pd.DataFrame, top_k: int) -> pd.DataFrame:
    """Long top_k / short bottom_k per row by score; dollar-neutral, sum|w| == 1."""
    w = pd.DataFrame(0.0, index=score.index, columns=score.columns)
    for dt, row in score.iterrows():
        r = row.dropna()
        if len(r) < 2 * top_k:
            continue
        ranked = r.sort_values()
        w.loc[dt, ranked.index[:top_k]] = -1.0   # cheapest/weakest -> short
        w.loc[dt, ranked.index[-top_k:]] = 1.0   # richest/strongest -> long
    return normalize_book(w)


def momentum_score(px: pd.DataFrame) -> pd.DataFrame:
    return px.shift(21) / px.shift(252) - 1.0      # 12-1m, skip last month


def value_score(px: pd.DataFrame) -> pd.DataFrame:
    return -(px / px.shift(1260) - 1.0)            # 5y reversal: biggest losers = cheap


def zcombo(px: pd.DataFrame) -> pd.DataFrame:
    m, v = momentum_score(px), value_score(px)
    zm = m.sub(m.mean(axis=1), axis=0).div(m.std(axis=1), axis=0)
    zv = v.sub(v.mean(axis=1), axis=0).div(v.std(axis=1), axis=0)
    return (zm + zv) / 2.0


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
    sr = a.mean() / sd
    sr_b = sr_bench_annual / np.sqrt(252)
    sk, ku = skew(a), kurtosis(a, fisher=False)
    denom = np.sqrt(max(1e-9, 1 - sk * sr + (ku - 1) / 4 * sr**2))
    z = (sr - sr_b) * np.sqrt(n - 1) / denom
    return float(norm.cdf(z))


def main():
    print("Downloading FX (yfinance, currency vs USD)...")
    px = load_ccy_vs_usd()
    print(f"panel: {px.shape[1]} ccys x {px.shape[0]} days  "
          f"{px.index.min().date()} -> {px.index.max().date()}")
    bt = DailyBacktester(px, cost_bps={c: COST[c] for c in px.columns},
                         ret_clip=RET_CLIP, swap_bps={c: 0.0 for c in px.columns})
    oos = oos_split_date(px, 0.3)

    books = {
        "momentum_12_1": xsec_book(momentum_score(px), TOP_K),
        "value_5y_rev": xsec_book(value_score(px), TOP_K),
        "combo_z": xsec_book(zcombo(px), TOP_K),
    }
    print(f"\n{'signal':<16}{'FULL Sh':>9}{'boot 95% CI':>20}{'PSR>0':>8}"
          f"{'OOS Sh':>8}{'OOS t':>7}{'maxDD':>8}{'turn':>7}")
    trial_sharpes, daily_by_name = [], {}
    for name, w in books.items():
        res = bt.run(w, oos)
        daily = res["daily"]
        daily_by_name[name] = daily
        ci = block_boot_ci(daily)
        full, oosm = res["full"], res["oos"]
        trial_sharpes.append(full.sharpe)
        ci_s = f"[{ci[0]:+.2f},{ci[2]:+.2f}]" if ci is not None else "n/a"
        print(f"{name:<16}{full.sharpe:>9.2f}{ci_s:>20}{psr(daily):>8.3f}"
              f"{oosm.sharpe:>8.2f}{oosm.t_stat:>7.2f}{full.max_dd*100:>7.1f}%"
              f"{full.avg_turnover:>7.2f}")

    # Deflated benchmark vs the deployable strategy (the z-combo).
    sr_var = np.var(trial_sharpes, ddof=1) if len(trial_sharpes) > 1 else 0.25
    gamma = 0.5772
    z1 = norm.ppf(1 - 1.0 / N_TRIALS)
    z2 = norm.ppf(1 - 1.0 / (N_TRIALS * np.e))
    sr0 = np.sqrt(max(sr_var, 1e-6)) * ((1 - gamma) * z1 + gamma * z2)
    dsr = psr(daily_by_name["combo_z"], sr_bench_annual=sr0)
    print(f"\nDeflated benchmark SR* (N_trials={N_TRIALS}) = {sr0:.2f}  "
          f"-> Deflated PSR (combo vs SR*) = {dsr:.3f}")
    print("\nGO if: OOS Sharpe > 0 AND boot 95% CI lower > 0 AND Deflated PSR > 0.95.")
    print("(dollar-neutral long top-3 / short bottom-3 of 13 ccys vs USD; financing=0")
    print(" isolates price signal; carry tested in Phase 1b only if this shows life.)")


if __name__ == "__main__":
    main()
