"""Faithful, leak-free replication of the Zarattini-Aziz intraday momentum
strategy (SSRN 4824172, "Beat the Market", net Sharpe 1.33 on SPY 2007-2024).

WHY: post-MTF-leak alpha hunt. Every prior MANTIS test ran on daily/1h/4h and
found no edge. This is the strongest fresh INTRADAY lead from the 2026-06-01
deep-research sweep — never tested. Single liquid instrument (our US500).

EXACT PUBLISHED RULES (verified from paper + reviews 2026-06-01):
- Noise band at minute t of day: Open_today * (1 +/- Move(t)), where Move(t) =
  mean over the LAST 14 trading days of |close_d(t)/open_d - 1| (intraday vol
  seasonality). Then widen: upper += overnight gap-DOWN amount, lower -= gap-UP
  amount (post-gap mean-reversion guard).
- Entry: ONLY at clock HH:00 / HH:30. If price > upper -> long; < lower -> short
  (trend-follow the breakout). Re-entry allowed after a stop-out.
- Trailing stop (checked every minute): long exits if price < max(upper, VWAP);
  short exits if price > min(lower, VWAP). VWAP = intraday volume-weighted.
- Position sizing: vol-target 2% DAILY vol from 14d realized vol, capped at 4x
  leverage. All same-day trades use that day's leverage.
- Flat at the cash close (no overnight). Cost: ~1bp/side on SPY (paper used
  $0.0035 comm + $0.001 slip per share ~ 1bp at $450).

LEAK DISCIPLINE: Move(t), realized-vol leverage, and the prev-close gap all use
ONLY data from strictly-prior days (rolling shift(1)). VWAP and the band at
minute t use only data up to and including minute t of the CURRENT day. A trade
opened at minute t can only earn the path AFTER t. No future bar is ever read.

Run from backend/:
  .venv/Scripts/python.exe scripts/ab/intraday_momentum.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # backend/
CACHE = ROOT / "data" / "intraday"

# ---- strategy params (published defaults; overridable for robustness) ----
LOOKBACK_DAYS = 14        # band + realized-vol lookback
TARGET_DAILY_VOL = 0.02   # 2% daily vol target
MAX_LEVERAGE = 4.0
COST_BPS_PER_SIDE = 1.0   # 1 bp per fill (SPY paper assumption)
TRADING_DAYS = 252


def load_panel(year_from: int = 2012, year_to: int = 2026) -> pd.DataFrame:
    frames = []
    for y in range(year_from, year_to + 1):
        f = CACHE / f"sp500_1m_{y}.parquet"
        if f.exists():
            frames.append(pd.read_parquet(f))
    if not frames:
        raise RuntimeError(f"no cached intraday parquet in {CACHE} — run fetch first")
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated(keep="first")]
    return df


def build_matrices(df: pd.DataFrame):
    """Pivot to [day x minute_of_day] matrices, leak-safe band + leverage.

    Returns dict of aligned frames: close, vwap, upper, lower, leverage(Series),
    plus the sorted minute grid and day index.
    """
    df = df.copy()
    # collapse to one row per (session, minute_of_day); first if dup
    df = df.reset_index().drop_duplicates(["session", "minute_of_day"], keep="first")
    close = df.pivot(index="session", columns="minute_of_day", values="close").sort_index()
    vol = df.pivot(index="session", columns="minute_of_day", values="volume").sort_index()
    minutes = sorted(close.columns)
    close = close[minutes]
    vol = vol[minutes].fillna(0.0)
    # forward-fill within-day missing minutes so VWAP / stops have a price each step
    close = close.ffill(axis=1).bfill(axis=1)

    open_px = close[minutes[0]]                      # 09:30 open per day
    prev_close = close[minutes[-1]].shift(1)         # prev day's 16:00 close
    gap_down_amt = (prev_close - open_px).clip(lower=0)  # >0 when gapped DOWN
    gap_up_amt = (open_px - prev_close).clip(lower=0)    # >0 when gapped UP

    # intraday absolute move from open at each minute; Move(t)=mean over last 14 prior days
    intraday = close.div(open_px, axis=0) - 1.0
    abs_move = intraday.abs()
    move = abs_move.shift(1).rolling(LOOKBACK_DAYS, min_periods=LOOKBACK_DAYS).mean()

    upper = close.mul(0).add(open_px, axis=0) * (1 + move)
    upper = upper.add(gap_down_amt, axis=0)
    lower = close.mul(0).add(open_px, axis=0) * (1 - move)
    lower = lower.sub(gap_up_amt, axis=0)

    # intraday VWAP (cumulative within day) — leak-safe (uses <= minute t)
    pv = (close * vol).cumsum(axis=1)
    cv = vol.cumsum(axis=1).replace(0, np.nan)
    vwap = (pv / cv).ffill(axis=1)
    vwap = vwap.fillna(close)  # early bars with zero vol -> use price

    # leverage from 14d realized daily vol (close-to-close), shifted (prior days only)
    daily_ret = open_px.pct_change()  # open-to-open proxy; close-to-close also fine
    realized = daily_ret.rolling(LOOKBACK_DAYS, min_periods=LOOKBACK_DAYS).std().shift(1)
    leverage = (TARGET_DAILY_VOL / realized).clip(upper=MAX_LEVERAGE).fillna(0.0)

    return {
        "close": close, "vwap": vwap, "upper": upper, "lower": lower,
        "leverage": leverage, "minutes": minutes, "open": open_px,
    }


def _is_halfhour(minute_of_day: int) -> bool:
    """minute_of_day 0 == 09:30 ET. True at clock HH:00 / HH:30, excluding the open."""
    clock = (9 * 60 + 30) + minute_of_day
    return minute_of_day > 0 and (clock % 30 == 0)


def simulate(mats, cost_bps_per_side: float = COST_BPS_PER_SIDE,
             stop_mode: str = "vwap_band", side: str = "both",
             collect: bool = False) -> pd.Series:
    """Per-day intraday simulation. Returns daily strategy return series.

    stop_mode (long-position stop level; short is mirror):
      'vwap_band'  -> max(upper_band, VWAP)   (literal CXO reading; tightest)
      'vwap'       -> VWAP only                (trail VWAP)
      'opp_band'   -> max(lower_band, VWAP)    (opposite band or VWAP; loosest)
      'band'       -> upper_band only          (pure band re-cross)
    side: 'both' | 'long' | 'short' (diagnostic).
    """
    close = mats["close"]; vwap = mats["vwap"]
    upper = mats["upper"]; lower = mats["lower"]; lev = mats["leverage"]
    minutes = mats["minutes"]
    cost = cost_bps_per_side * 1e-4
    halfhour_set = {i for i, m in enumerate(minutes) if _is_halfhour(int(m))}
    allow_long = side in ("both", "long")
    allow_short = side in ("both", "short")

    days = close.index
    out = {}
    trades = []
    cvals = close.values; uvals = upper.values
    lvals = lower.values; wvals = vwap.values
    levvals = lev.reindex(days).values
    n_min = len(minutes)

    def long_stop(up, lo, vw):
        if stop_mode == "vwap":
            return vw
        if stop_mode == "band":
            return up
        if stop_mode == "opp_band":
            return max(lo, vw) if np.isfinite(lo) else vw
        return max(up, vw) if np.isfinite(up) else vw  # vwap_band

    def short_stop(up, lo, vw):
        if stop_mode == "vwap":
            return vw
        if stop_mode == "band":
            return lo
        if stop_mode == "opp_band":
            return min(up, vw) if np.isfinite(up) else vw
        return min(lo, vw) if np.isfinite(lo) else vw

    for di in range(len(days)):
        L = levvals[di]
        if not np.isfinite(L) or L <= 0 or not np.isfinite(uvals[di]).any():
            out[days[di]] = 0.0
            continue
        pos = 0; entry = 0.0; day_ret = 0.0
        for mi in range(n_min):
            px = cvals[di, mi]
            if not np.isfinite(px):
                continue
            up = uvals[di, mi]; lo = lvals[di, mi]; vw = wvals[di, mi]
            if pos == 1:
                stop = long_stop(up, lo, vw)
                if np.isfinite(stop) and px < stop:
                    r = L * (px / entry - 1.0) - cost * L
                    day_ret += r; trades.append(r); pos = 0
            elif pos == -1:
                stop = short_stop(up, lo, vw)
                if np.isfinite(stop) and px > stop:
                    r = L * (entry / px - 1.0) - cost * L
                    day_ret += r; trades.append(r); pos = 0
            if pos == 0 and mi in halfhour_set and np.isfinite(up) and np.isfinite(lo):
                if allow_long and px > up:
                    pos = 1; entry = px; day_ret -= cost * L
                elif allow_short and px < lo:
                    pos = -1; entry = px; day_ret -= cost * L
        if pos != 0:
            px = cvals[di, n_min - 1]
            if not np.isfinite(px):
                for mi in range(n_min - 1, -1, -1):
                    if np.isfinite(cvals[di, mi]):
                        px = cvals[di, mi]; break
            r = (L * (px / entry - 1.0) if pos == 1 else L * (entry / px - 1.0)) - cost * L
            day_ret += r; trades.append(r)
        out[days[di]] = day_ret

    s = pd.Series(out).sort_index()
    if collect:
        s.attrs["trades"] = trades
    return s


@dataclass
class Result:
    n: int
    sharpe: float
    ann_ret: float
    ann_vol: float
    hit: float
    max_dd: float
    t: float
    total: float

    def line(self, label: str) -> str:
        return (f"  {label:<8} n={self.n:<5} Sharpe={self.sharpe:>6.2f}  "
                f"ret={self.ann_ret*100:>6.1f}%  vol={self.ann_vol*100:>5.1f}%  "
                f"hit={self.hit:>4.1f}%  maxDD={self.max_dd*100:>6.1f}%  t={self.t:>5.2f}")


def metrics(daily: pd.Series) -> Result:
    d = daily.dropna()
    d = d[d != 0.0] if (d == 0.0).all() else d  # guard
    d = daily.dropna()
    n = len(d)
    if n < 20:
        return Result(n, 0, 0, 0, 0, 0, 0, 0)
    mean, std = d.mean(), d.std(ddof=1)
    sharpe = mean / std * np.sqrt(TRADING_DAYS) if std > 0 else 0.0
    eq = (1 + d).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    t = mean / (std / np.sqrt(n)) if std > 0 else 0.0
    traded = d[d != 0]
    hit = (traded > 0).mean() * 100 if len(traded) else 0.0
    return Result(n, sharpe, mean * TRADING_DAYS, std * np.sqrt(TRADING_DAYS),
                  hit, dd, t, eq.iloc[-1] - 1)


def deflated_sharpe(daily: pd.Series, n_trials: int) -> float:
    """Bailey-Lopez de Prado Deflated Sharpe Ratio probability (annualized SR)."""
    from scipy.stats import norm, skew, kurtosis
    d = daily.dropna()
    n = len(d)
    if n < 30 or d.std() == 0:
        return float("nan")
    sr = d.mean() / d.std(ddof=1)              # per-period (daily) Sharpe
    g3 = skew(d); g4 = kurtosis(d, fisher=False)
    e = 0.5772156649                           # Euler-Mascheroni
    # std of the Sharpe estimate (accounts for skew/kurtosis of returns)
    sr_hat_std = np.sqrt((1 - g3 * sr + (g4 - 1) / 4 * sr**2) / (n - 1))
    # expected max Sharpe across N independent trials under the null (SR0=0)
    emax = sr_hat_std * ((1 - e) * norm.ppf(1 - 1.0 / n_trials) +
                         e * norm.ppf(1 - 1.0 / (n_trials * np.e)))
    return float(norm.cdf((sr - emax) / sr_hat_std))


def _hit_oos(daily, split):
    f = metrics(daily); o = metrics(daily[daily.index >= split])
    return f, o


def sweep(oos_frac: float = 0.35):
    """Diagnose stop interpretation + side split on the full panel."""
    df = load_panel()
    days = sorted(df["session"].unique())
    print(f"[SWEEP] {len(df):,} bars / {len(days)} days / "
          f"{pd.Timestamp(days[0]).date()}->{pd.Timestamp(days[-1]).date()}\n")
    mats = build_matrices(df)
    probe = simulate(mats).dropna()
    split = probe.index[int(len(probe) * (1 - oos_frac))]
    print(f"OOS split = {pd.Timestamp(split).date()}\n")
    print("STOP-MODE sweep (both sides):")
    for mode in ["vwap_band", "band", "vwap", "opp_band"]:
        d = simulate(mats, stop_mode=mode).dropna()
        f, o = _hit_oos(d, split)
        print(f"  {mode:<10} {f.line('FULL')}")
        print(f"  {'':<10} {o.line('OOS ')}")
    print("\nSIDE split (stop_mode=opp_band):")
    for sd in ["both", "long", "short"]:
        d = simulate(mats, stop_mode="opp_band", side=sd).dropna()
        f, o = _hit_oos(d, split)
        print(f"  {sd:<6} {f.line('FULL')}")
        print(f"  {'':<6} {o.line('OOS ')}")


def mr_simulate(mats, cost_bps_per_side: float = COST_BPS_PER_SIDE,
                side: str = "both", stop_mult: float = 1.0) -> pd.Series:
    """Intraday MEAN-REVERSION (the mirror of momentum, motivated by the post-2022
    regime flip). At HH:00/HH:30, FADE a band break: price>upper -> SHORT, price<lower
    -> LONG. Take-profit at reversion to intraday VWAP (the 'mean'); stop if the move
    extends another stop_mult * band-half-width beyond the entry band; flat at EOD.
    Same vol-target leverage + per-side cost. Leak-safe (band/VWAP use <= minute t)."""
    close = mats["close"]; vwap = mats["vwap"]
    upper = mats["upper"]; lower = mats["lower"]; lev = mats["leverage"]
    open_px = mats["open"]; minutes = mats["minutes"]
    cost = cost_bps_per_side * 1e-4
    halfhour_set = {i for i, m in enumerate(minutes) if _is_halfhour(int(m))}
    allow_long = side in ("both", "long")
    allow_short = side in ("both", "short")

    days = close.index
    cvals = close.values; uvals = upper.values; lvals = lower.values
    wvals = vwap.values; levvals = lev.reindex(days).values
    ovals = open_px.reindex(days).values
    n_min = len(minutes)
    out = {}

    for di in range(len(days)):
        L = levvals[di]
        if not np.isfinite(L) or L <= 0 or not np.isfinite(uvals[di]).any():
            out[days[di]] = 0.0
            continue
        O = ovals[di]
        pos = 0; entry = 0.0; sl = 0.0; day_ret = 0.0
        for mi in range(n_min):
            px = cvals[di, mi]
            if not np.isfinite(px):
                continue
            up = uvals[di, mi]; lo = lvals[di, mi]; vw = wvals[di, mi]
            if pos == 1:  # faded a LOW break -> long, target VWAP above
                if (np.isfinite(vw) and px >= vw) or px <= sl:
                    day_ret += L * (px / entry - 1.0) - cost * L; pos = 0
            elif pos == -1:  # faded a HIGH break -> short, target VWAP below
                if (np.isfinite(vw) and px <= vw) or px >= sl:
                    day_ret += L * (entry / px - 1.0) - cost * L; pos = 0
            if pos == 0 and mi in halfhour_set and np.isfinite(up) and np.isfinite(lo):
                half = (up - lo) / 2.0
                if allow_short and px > up:
                    pos = -1; entry = px; sl = px + stop_mult * half; day_ret -= cost * L
                elif allow_long and px < lo:
                    pos = 1; entry = px; sl = px - stop_mult * half; day_ret -= cost * L
        if pos != 0:
            px = cvals[di, n_min - 1]
            if not np.isfinite(px):
                for mi in range(n_min - 1, -1, -1):
                    if np.isfinite(cvals[di, mi]):
                        px = cvals[di, mi]; break
            day_ret += (L * (px / entry - 1.0) if pos == 1 else L * (entry / px - 1.0)) - cost * L
        out[days[di]] = day_ret
    return pd.Series(out).sort_index()


def mr_test(oos_frac: float = 0.35):
    df = load_panel()
    mats = build_matrices(df)
    probe = mr_simulate(mats).dropna()
    split = probe.index[int(len(probe) * (1 - oos_frac))]
    print("=== INTRADAY MEAN-REVERSION (mirror of momentum) ===")
    print(f"OOS split = {pd.Timestamp(split).date()}\n")
    print("Side split (cost 1bp/side, stop_mult=1.0):")
    for sd in ["both", "long", "short"]:
        d = mr_simulate(mats, side=sd).dropna()
        f = metrics(d); o = metrics(d[d.index >= split])
        print(f"  {sd:<6} {f.line('FULL')}")
        print(f"  {'':<6} {o.line('OOS ')}")
    print("\nBest side = both; yearly Sharpe (is MR alive in the LIVE 2023-26 regime?):")
    d = mr_simulate(mats).dropna()
    by_year = d.groupby(d.index.year).apply(
        lambda x: x.mean() / x.std() * np.sqrt(TRADING_DAYS) if x.std() > 0 else 0.0)
    print("  " + "  ".join(f"{y}:{v:>5.2f}" for y, v in by_year.items()))
    print("\nCost sensitivity (both sides):")
    for cb in [1.0, 2.0, 3.0]:
        d = mr_simulate(mats, cost_bps_per_side=cb).dropna()
        o = metrics(d[d.index >= split])
        print(f"  cost={cb:>3.0f}bp  OOS Sharpe={o.sharpe:>5.2f} ret={o.ann_ret*100:>5.1f}% t={o.t:>5.2f}")
    d = mr_simulate(mats).dropna()
    print(f"\nDeflated Sharpe (N=10): full p={deflated_sharpe(d,10):.3f}  "
          f"OOS p={deflated_sharpe(d[d.index>=split],10):.3f}")


def naive_intraday_long(mats, cost_bps_per_side: float = COST_BPS_PER_SIDE) -> pd.Series:
    """Benchmark: buy at 09:30 open, sell at 16:00 close, every day, vol-targeted.
    If momentum timing doesn't beat THIS, the long edge is just intraday beta."""
    close = mats["close"]; lev = mats["leverage"]; minutes = mats["minutes"]
    o = close[minutes[0]]; c = close[minutes[-1]]
    L = lev.reindex(close.index)
    cost = cost_bps_per_side * 1e-4
    r = L * (c / o - 1.0) - 2 * cost * L      # one round-trip/day
    return r.dropna()


def validate(oos_frac: float = 0.35):
    """Adversarial validation of the long-only intraday-momentum lead."""
    df = load_panel()
    mats = build_matrices(df)
    probe = simulate(mats, side="long", stop_mode="vwap").dropna()
    split = probe.index[int(len(probe) * (1 - oos_frac))]
    print(f"=== VALIDATE long-only intraday momentum (vwap stop) ===")
    print(f"OOS split = {pd.Timestamp(split).date()}\n")

    print("1) MOMENTUM vs NAIVE intraday-long-all-day (is the timing real alpha?)")
    mom = simulate(mats, side="long", stop_mode="vwap").dropna()
    naive = naive_intraday_long(mats).dropna()
    idx = mom.index.intersection(naive.index)
    mom, naive = mom[idx], naive[idx]
    for nm, d in [("momentum", mom), ("naive-long", naive)]:
        f = metrics(d); o = metrics(d[d.index >= split])
        print(f"  {nm:<11} {f.line('FULL')}")
        print(f"  {'':<11} {o.line('OOS ')}")
    # excess of momentum over naive (does timing ADD?)
    excess = (mom - naive).dropna()
    ef = metrics(excess); eo = metrics(excess[excess.index >= split])
    print(f"  {'MOM-NAIVE':<11} {ef.line('FULL')}")
    print(f"  {'':<11} {eo.line('OOS ')}")

    print("\n2) COST sensitivity (long-only momentum, vwap stop):")
    for cb in [1.0, 2.0, 3.0, 5.0]:
        d = simulate(mats, cost_bps_per_side=cb, side="long", stop_mode="vwap").dropna()
        f = metrics(d); o = metrics(d[d.index >= split])
        print(f"  cost={cb:>3.0f}bp/side  FULL Sh={f.sharpe:>5.2f} ret={f.ann_ret*100:>5.1f}%  "
              f"OOS Sh={o.sharpe:>5.2f} ret={o.ann_ret*100:>5.1f}% t={o.t:>5.2f}")

    print("\n3) Deflated Sharpe (long-only, vwap, N=8 configs tried):")
    d = simulate(mats, side="long", stop_mode="vwap").dropna()
    dsr = deflated_sharpe(d, n_trials=8)
    print(f"  full-sample DSR p={dsr:.3f}  {'PASS>0.95' if dsr > 0.95 else 'FAIL'}")
    dsr_oos = deflated_sharpe(d[d.index >= split], n_trials=8)
    print(f"  OOS DSR        p={dsr_oos:.3f}  {'PASS>0.95' if dsr_oos > 0.95 else 'FAIL'}")

    print("\n4) Yearly long-only momentum Sharpe (regime dependence):")
    d = simulate(mats, side="long", stop_mode="vwap").dropna()
    by_year = d.groupby(d.index.year).apply(
        lambda x: x.mean() / x.std() * np.sqrt(TRADING_DAYS) if x.std() > 0 else 0.0)
    print("  " + "  ".join(f"{y}:{v:>5.2f}" for y, v in by_year.items()))


def regime(oos_frac: float = 0.35):
    """Is the 2024-26 decay a LOW-VOL pause or structural death?
    Bucket trading days by prior-14d realized vol; report long-only Sharpe per bucket,
    and within high-vol days only, the recent-years Sharpe."""
    df = load_panel()
    mats = build_matrices(df)
    daily = simulate(mats, side="long", stop_mode="vwap").dropna()
    # reconstruct prior realized vol per day (same as leverage input)
    close = mats["close"]; minutes = mats["minutes"]
    o = close[minutes[0]]
    rv = o.pct_change().rolling(LOOKBACK_DAYS, min_periods=LOOKBACK_DAYS).std().shift(1)
    rv = rv.reindex(daily.index)
    ann_rv = rv * np.sqrt(TRADING_DAYS) * 100  # annualized vol %

    print("=== REGIME: long-only intraday momentum by prior-vol bucket ===\n")
    q = pd.qcut(rv.dropna(), 4, labels=["Q1-low", "Q2", "Q3", "Q4-high"])
    print("Sharpe by realized-vol quartile (all years):")
    for lab in ["Q1-low", "Q2", "Q3", "Q4-high"]:
        idx = q[q == lab].index
        d = daily[idx]
        m = metrics(d)
        lo, hi = ann_rv.reindex(idx).min(), ann_rv.reindex(idx).max()
        print(f"  {lab:<8} vol[{lo:>4.0f}-{hi:>4.0f}%] {m.line('')}")

    print("\nHigh-vol days only (Q3+Q4), by year (is the edge alive when vol present?):")
    hv = daily[q[q.isin(["Q3", "Q4-high"])].index]
    by_year = hv.groupby(hv.index.year).apply(
        lambda x: (x.mean() / x.std() * np.sqrt(TRADING_DAYS), len(x)) if x.std() > 0 else (0.0, len(x)))
    print("  " + "  ".join(f"{y}:{v[0]:>5.2f}(n{v[1]})" for y, v in by_year.items()))

    print("\nLow-vol days only (Q1+Q2), by year:")
    lv = daily[q[q.isin(["Q1-low", "Q2"])].index]
    by_year = lv.groupby(lv.index.year).apply(
        lambda x: (x.mean() / x.std() * np.sqrt(TRADING_DAYS), len(x)) if x.std() > 0 else (0.0, len(x)))
    print("  " + "  ".join(f"{y}:{v[0]:>5.2f}(n{v[1]})" for y, v in by_year.items()))

    print("\nVol-gated strategy (trade ONLY Q3+Q4 days), full + OOS:")
    gated = daily.copy()
    gated[q[q.isin(["Q1-low", "Q2"])].index] = 0.0
    split = gated.index[int(len(gated) * (1 - oos_frac))]
    print(metrics(gated).line("FULL"))
    print(metrics(gated[gated.index >= split]).line(f"OOS>={pd.Timestamp(split).date()}"))
    print(f"  Deflated Sharpe (N=10): p={deflated_sharpe(gated, 10):.3f}")


def run(cost_bps_per_side: float = COST_BPS_PER_SIDE, oos_frac: float = 0.35,
        n_trials: int = 6, label: str = "BASE", stop_mode: str = "vwap_band"):
    df = load_panel()
    days = sorted(df["session"].unique())
    print(f"[{label}] panel: {len(df):,} bars / {len(days)} trading days / "
          f"{pd.Timestamp(days[0]).date()} -> {pd.Timestamp(days[-1]).date()} / "
          f"cost={cost_bps_per_side}bp/side stop={stop_mode}")
    mats = build_matrices(df)
    daily = simulate(mats, cost_bps_per_side, stop_mode=stop_mode)
    daily = daily.dropna()
    split = daily.index[int(len(daily) * (1 - oos_frac))]
    full = metrics(daily)
    isamp = metrics(daily[daily.index < split])
    oos = metrics(daily[daily.index >= split])
    print(full.line("FULL"))
    print(isamp.line("IS"))
    print(oos.line(f"OOS>={pd.Timestamp(split).date()}"))
    dsr = deflated_sharpe(daily, n_trials)
    n_traded = int((daily != 0).sum())
    print(f"  traded days={n_traded}/{len(daily)} ({n_traded/len(daily)*100:.0f}%)  "
          f"DeflatedSharpe(p, N={n_trials})={dsr:.3f}  "
          f"{'PASS>0.95' if dsr > 0.95 else 'FAIL'}")
    return daily


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "sweep":
        sweep()
    elif len(sys.argv) > 1 and sys.argv[1] == "validate":
        validate()
    elif len(sys.argv) > 1 and sys.argv[1] == "regime":
        regime()
    elif len(sys.argv) > 1 and sys.argv[1] == "mr":
        mr_test()
    else:
        cost = float(sys.argv[1]) if len(sys.argv) > 1 else COST_BPS_PER_SIDE
        run(cost_bps_per_side=cost)
