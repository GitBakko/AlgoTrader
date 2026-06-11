"""Shared leak-free evaluation battery for the documented-rule tests (VIX gate, vol-managed,
COT). Annualized Sharpe/t/maxDD, Probabilistic & Deflated Sharpe (Bailey-Lopez de Prado),
stationary-block bootstrap CI. Period-agnostic (pass periods_per_year: 252 daily, 52 weekly,
12 monthly)."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import kurtosis, norm, skew


def metrics(r: pd.Series, ppy: int) -> dict:
    d = r.dropna()
    n = len(d)
    if n < 5:
        return dict(n=n, sharpe=0.0, ann=0.0, t=0.0, dd=0.0, hit=0.0)
    mean, sd = d.mean(), d.std(ddof=1)
    sharpe = mean / sd * np.sqrt(ppy) if sd > 0 else 0.0
    eq = (1 + d).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    t = mean / (sd / np.sqrt(n)) if sd > 0 else 0.0
    return dict(n=n, sharpe=sharpe, ann=mean * ppy, t=t, dd=dd, hit=(d > 0).mean() * 100)


def cagr(r: pd.Series, ppy: int) -> float:
    d = r.dropna()
    if len(d) < 2:
        return 0.0
    return (1 + d).prod() ** (ppy / len(d)) - 1


def psr(r: pd.Series, sr_bench_ann: float, ppy: int) -> float:
    """Probabilistic Sharpe vs an annualized benchmark SR (skew/kurt aware)."""
    a = r.dropna().to_numpy()
    n = len(a)
    sd = a.std(ddof=1)
    if n < 24 or sd == 0:
        return float("nan")
    sr = a.mean() / sd                      # per-period
    sr_b = sr_bench_ann / np.sqrt(ppy)
    sk, ku = skew(a), kurtosis(a, fisher=False)
    denom = np.sqrt(max(1e-9, 1 - sk * sr + (ku - 1) / 4 * sr**2))
    return float(norm.cdf((sr - sr_b) * np.sqrt(n - 1) / denom))


def deflated_sr(r: pd.Series, trial_sharpes_ann: list[float], ppy: int) -> tuple[float, float]:
    """Deflated PSR: benchmark SR* from the variance of the trial Sharpes (multiple testing)."""
    N = max(2, len(trial_sharpes_ann))
    sr_var = np.var(trial_sharpes_ann, ddof=1) if N > 1 else 0.25
    g = 0.5772156649
    z1 = norm.ppf(1 - 1.0 / N)
    z2 = norm.ppf(1 - 1.0 / (N * np.e))
    sr0_ann = np.sqrt(max(sr_var, 1e-6)) * ((1 - g) * z1 + g * z2)
    return psr(r, sr0_ann, ppy), sr0_ann


def block_boot_ci(r: pd.Series, ppy: int, block: int = 21, n_boot: int = 3000, seed: int = 0):
    a = r.dropna().to_numpy()
    n = len(a)
    if n < block * 5:
        return (np.nan, np.nan, np.nan)
    rng = np.random.default_rng(seed)
    nb = int(np.ceil(n / block))
    out = np.empty(n_boot)
    for k in range(n_boot):
        starts = rng.integers(0, n, size=nb)
        idx = (starts[:, None] + np.arange(block)).ravel()[:n] % n
        s = a[idx]
        sd = s.std(ddof=1)
        out[k] = (s.mean() / sd * np.sqrt(ppy)) if sd > 0 else 0.0
    return tuple(np.percentile(out, [5, 50, 95]))


def line(label: str, m: dict, extra: str = "") -> str:
    return (f"  {label:<22} n={m['n']:<5} Sh={m['sharpe']:>6.2f}  ann={m['ann']*100:>6.1f}%  "
            f"t={m['t']:>5.2f}  maxDD={m['dd']*100:>6.1f}%  hit={m['hit']:>4.1f}%{extra}")
