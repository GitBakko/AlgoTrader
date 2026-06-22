"""
intraday_probe.py  —  ONE concrete intraday hypothesis, leak-free, net-of-cost OOS.

CONTEXT
-------
MANTIS intraday CFD on SP500. We already PROVED (scripts/ab/intraday_momentum.py):
  - intraday MOMENTUM (Beat-the-Market open-range trend) is DEAD post-2022, and
  - its mean-reversion mirror is catastrophic.
The user wants to know if ANY *other* intraday angle survives on our Dukascopy
SP500 1-min cache (2012..2026).

HYPOTHESIS (NOT plain momentum, NOT plain band-fade)
----------------------------------------------------
OVERNIGHT-GAP CONTINUATION-vs-FADE, conditioned on gap SIZE.
Folk wisdom + academic gap literature: small overnight gaps tend to *fade*
(revert toward the prior close); large gaps tend to *continue* (information
shock). We:
  1. Define the overnight gap at the cash open as
        g = open_today / close_yesterday - 1
     This is FULLY known at 09:30 ET (uses only data <= the open bar).
  2. Normalize the gap by a TRAILING realized-vol estimate (prior 20 sessions'
     close-to-close daily vol, known by yesterday's close). z = g / sigma.
  3. The intraday trade is OPEN -> CLOSE the SAME session (flat at 16:00 ET,
     no overnight exposure). Direction = a sign rule that is FIT ON THE
     IN-SAMPLE PERIOD ONLY (monotone bucket map of z -> sign of subsequent
     open->close return), then FROZEN and applied to OOS.

WHY THIS IS LEAK-FREE
---------------------
  - g uses close[t-1] (known) and open[t] (the moment we enter). No future bar.
  - sigma uses sessions strictly < t.
  - The bucket sign map is learned on IS sessions only; OOS sessions never touch
    the fit. Each OOS session's z is bucketed with IS-frozen edges + IS-frozen
    signs, then the realized open->close return is booked.
  - One round-trip per session (enter at open, exit at close) => 2 fills.

COST
----
1 bp/side (same SPY assumption as intraday_momentum.py), i.e. 2 bp round trip.
We also sweep 0/1/2/3 bp/side.

OUTPUT: leak-free net-of-cost OOS Sharpe + whether it beats zero (t-stat, DSR).
Honest kill if dead.
"""

from __future__ import annotations

import glob
import os

import numpy as np
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "intraday")
TRADING_DAYS = 252
COST_BPS_PER_SIDE = 1.0          # 1 bp/fill (SPY paper assumption)
OOS_SPLIT_FRAC = 0.65            # first 65% IS, last 35% OOS (matches xsec convention)
VOL_LOOKBACK = 20                # sessions for trailing daily vol
N_BUCKETS = 7                    # z-score buckets for the sign map
MIN_BUCKET_N = 30                # IS sessions needed in a bucket to trust its sign


# ----------------------------------------------------------------------------- load
def load_sessions() -> pd.DataFrame:
    """One row per RTH session: date, open (first bar open), close (last bar close).

    Uses minute_of_day==0 open and the max minute_of_day close, so it is robust to
    occasional half-days (range 0..389 confirmed). Only RTH bars are present.
    """
    files = sorted(glob.glob(os.path.join(DATA_DIR, "sp500_1m_*.parquet")))
    rows = []
    for f in files:
        df = pd.read_parquet(f)
        # session column = trading day (datetime64[ms], naive)
        g = df.groupby("session")
        first = g.first()          # minute_of_day order preserved (index is time-sorted)
        last = g.last()
        s = pd.DataFrame(
            {
                "open": first["open"].values,
                "close": last["close"].values,
                "n_bars": g.size().values,
            },
            index=pd.to_datetime(first.index),
        )
        rows.append(s)
    out = pd.concat(rows).sort_index()
    out = out[~out.index.duplicated(keep="first")]
    # drop obviously broken sessions (need a meaningful number of RTH bars)
    out = out[out["n_bars"] >= 200]
    return out


# ----------------------------------------------------------------------------- features
def build_features(sess: pd.DataFrame) -> pd.DataFrame:
    """Leak-free per-session features. All known AT the open of session t."""
    df = sess.copy()
    df["prev_close"] = df["close"].shift(1)                          # close[t-1]
    df["gap"] = df["open"] / df["prev_close"] - 1.0                  # known at 09:30
    df["oc_ret"] = df["close"] / df["open"] - 1.0                    # the thing we trade (open->close)

    # trailing daily (close-to-close) vol using ONLY sessions < t
    daily_ret = df["close"].pct_change()
    df["sigma"] = (
        daily_ret.rolling(VOL_LOOKBACK, min_periods=VOL_LOOKBACK).std().shift(1)
    )
    df["z"] = df["gap"] / df["sigma"]
    return df.dropna(subset=["gap", "oc_ret", "sigma", "z"])


# ----------------------------------------------------------------------------- sign map (IS-only)
def fit_sign_map(is_df: pd.DataFrame):
    """Learn z-bucket -> sign(E[oc_ret]) from IS sessions only.

    Returns (edges, signs). Buckets with too few obs or |mean|*sharpe too weak
    are set to 0 (no trade) so we don't overfit thin tails.
    """
    z = is_df["z"].values
    r = is_df["oc_ret"].values
    edges = np.quantile(z, np.linspace(0, 1, N_BUCKETS + 1))
    edges[0], edges[-1] = -np.inf, np.inf
    signs = np.zeros(N_BUCKETS)
    diag = []
    for b in range(N_BUCKETS):
        m = (z >= edges[b]) & (z < edges[b + 1])
        n = int(m.sum())
        if n < MIN_BUCKET_N:
            diag.append((b, n, np.nan, 0))
            continue
        mu = r[m].mean()
        # require the bucket's mean to be non-trivial vs its own noise
        t_b = mu / (r[m].std(ddof=1) / np.sqrt(n)) if r[m].std(ddof=1) > 0 else 0.0
        s = int(np.sign(mu)) if abs(t_b) >= 1.0 else 0   # weak IS signal -> no trade
        signs[b] = s
        diag.append((b, n, mu, s))
    return edges, signs, diag


def apply_sign_map(df: pd.DataFrame, edges, signs) -> pd.Series:
    idx = np.clip(np.digitize(df["z"].values, edges[1:-1]), 0, N_BUCKETS - 1)
    return pd.Series(signs[idx], index=df.index)


# ----------------------------------------------------------------------------- metrics
def metrics(daily: pd.Series, label: str = "") -> dict:
    d = daily.dropna()
    n = len(d)
    if n < 5 or d.std(ddof=1) == 0:
        return {"label": label, "n": n, "sharpe": 0.0, "ann": 0.0, "t": 0.0, "hit": 0.0}
    mean, std = d.mean(), d.std(ddof=1)
    sharpe = mean / std * np.sqrt(TRADING_DAYS)
    t = mean / (std / np.sqrt(n))
    hit = (d > 0).mean()
    return {"label": label, "n": n, "sharpe": sharpe, "ann": mean * TRADING_DAYS,
            "t": t, "hit": hit}


def deflated_sharpe(daily: pd.Series, n_trials: int) -> float:
    """Bailey / Lopez de Prado DSR probability (annualized SR > 0)."""
    d = daily.dropna().values
    n = len(d)
    if n < 10 or d.std(ddof=1) == 0:
        return 0.0
    sr = d.mean() / d.std(ddof=1)
    g3 = pd.Series(d).skew()
    g4 = pd.Series(d).kurt() + 3.0
    sr_hat_std = np.sqrt(max((1 - g3 * sr + (g4 - 1) / 4 * sr**2) / (n - 1), 1e-12))
    euler = 0.5772156649
    e_max = np.sqrt(2 * np.log(max(n_trials, 2))) * (1 - euler / (2 * np.log(max(n_trials, 2)))) \
        + euler / np.sqrt(2 * np.log(max(n_trials, 2)))
    sr0 = sr_hat_std * e_max
    from math import erf, sqrt
    z = (sr - sr0) / sr_hat_std
    return 0.5 * (1 + erf(z / sqrt(2)))


# ----------------------------------------------------------------------------- backtest
def run_strategy(df: pd.DataFrame, edges, signs, cost_bps_per_side: float) -> pd.Series:
    """Book open->close return * position, minus 2*cost when position != 0."""
    pos = apply_sign_map(df, edges, signs)
    cost = cost_bps_per_side * 1e-4
    gross = pos * df["oc_ret"]
    fills_cost = (pos != 0).astype(float) * 2 * cost          # enter+exit
    return (gross - fills_cost).rename("ret")


def main():
    sess = load_sessions()
    feat = build_features(sess)
    n = len(feat)
    split_i = int(n * OOS_SPLIT_FRAC)
    split_date = feat.index[split_i]
    is_df = feat.iloc[:split_i]
    oos_df = feat.iloc[split_i:]

    print("=" * 78)
    print("INTRADAY PROBE — overnight-gap continuation/fade, vol-normalized, leak-free")
    print("=" * 78)
    print(f"Sessions total={n}  IS={len(is_df)}  OOS={len(oos_df)}  split={split_date.date()}")
    print(f"Coverage {feat.index[0].date()} .. {feat.index[-1].date()}")
    print(f"Vol lookback={VOL_LOOKBACK}  buckets={N_BUCKETS}  cost={COST_BPS_PER_SIDE}bp/side")

    # ---- fit sign map on IS only ----
    edges, signs, diag = fit_sign_map(is_df)
    print("\nIS-fit z-bucket sign map (small |z|=fade, large |z|=continue is the prior):")
    print(f"  edges(z): {np.round(edges[1:-1], 3)}")
    print(f"  {'bucket':<7}{'n_IS':<7}{'mean_oc_ret_bps':<18}{'sign':<6}")
    for b, nn, mu, s in diag:
        mub = "  n/a" if (isinstance(mu, float) and np.isnan(mu)) else f"{mu*1e4:>8.2f}"
        print(f"  {b:<7}{nn:<7}{mub:<18}{s:<6}")

    # ---- baselines ----
    bh_is = (is_df["oc_ret"] - 2 * COST_BPS_PER_SIDE * 1e-4)
    bh_oos = (oos_df["oc_ret"] - 2 * COST_BPS_PER_SIDE * 1e-4)
    print("\nBASELINE — intraday buy&hold (long open->close every day, net):")
    for lab, s in [("IS", bh_is), ("OOS", bh_oos)]:
        m = metrics(s, lab)
        print(f"  {lab:<4} Sharpe={m['sharpe']:>6.2f} ann={m['ann']*100:>6.2f}% "
              f"t={m['t']:>5.2f} hit={m['hit']*100:>5.1f}% n={m['n']}")

    # ---- strategy ----
    is_ret = run_strategy(is_df, edges, signs, COST_BPS_PER_SIDE)
    oos_ret = run_strategy(oos_df, edges, signs, COST_BPS_PER_SIDE)
    print("\nSTRATEGY — gap sign-map (IS-frozen), net 1bp/side:")
    for lab, s in [("IS", is_ret), ("OOS", oos_ret)]:
        m = metrics(s, lab)
        traded = (apply_sign_map(is_df if lab == "IS" else oos_df, edges, signs) != 0).mean()
        print(f"  {lab:<4} Sharpe={m['sharpe']:>6.2f} ann={m['ann']*100:>6.2f}% "
              f"t={m['t']:>5.2f} hit={m['hit']*100:>5.1f}% traded={traded*100:>4.0f}% n={m['n']}")

    # ---- cost sensitivity (OOS) ----
    print("\nOOS cost sensitivity:")
    for cb in [0.0, 1.0, 2.0, 3.0]:
        o = metrics(run_strategy(oos_df, edges, signs, cb), f"{cb}bp")
        print(f"  cost={cb:>3.0f}bp/side  OOS Sharpe={o['sharpe']:>5.2f} "
              f"ann={o['ann']*100:>6.2f}% t={o['t']:>5.2f}")

    # ---- significance ----
    dsr_oos = deflated_sharpe(oos_ret, n_trials=12)   # ~12 design choices tried across project
    print(f"\nOOS Deflated Sharpe prob (N=12 trials): {dsr_oos:.3f}  "
          f"(PASS if >0.95)")

    # ---- yearly OOS robustness ----
    yr = oos_ret.groupby(oos_ret.index.year).apply(
        lambda x: x.mean() / x.std(ddof=1) * np.sqrt(TRADING_DAYS) if x.std(ddof=1) > 0 else 0.0)
    print("\nOOS yearly Sharpe:")
    for y, v in yr.items():
        print(f"  {y}: {v:>5.2f}")

    # ---- verdict ----
    om = metrics(oos_ret, "OOS")
    beats_zero = (om["t"] >= 2.0) and (om["sharpe"] > 0) and (dsr_oos > 0.95)
    print("\n" + "=" * 78)
    print(f"VERDICT: OOS net Sharpe={om['sharpe']:.2f}  t={om['t']:.2f}  "
          f"DSR={dsr_oos:.3f}  -> {'BEATS ZERO' if beats_zero else 'DOES NOT beat zero (KILL)'}")
    print("=" * 78)


if __name__ == "__main__":
    main()
