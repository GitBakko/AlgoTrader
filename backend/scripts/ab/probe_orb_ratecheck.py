"""Diagnostic: ORB entry-rate over recent history — why is N(orb) accruing so slowly?

Read-only (yfinance only; no broker, no loop). Reconstructs the live ORB pipeline
per ET trading day over the last ~60d of 5-min data:
  RVOL (early-30min vol / trailing-20d baseline) -> eligible (>=rvol_min, top_k)
  -> OR high/low from [09:30,10:00) -> did price break OR later in session?
and reports eligible-count + entry-count distributions and the projected days to
reach N=100, for the live 30-name universe AND a wider candidate universe (to
size the 'widen universe' lever without weakening the RVOL filter).

Run from backend/.  Usage: python scripts/ab/probe_orb_ratecheck.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts" / "ab"))

from forward_lab import ORB_UNIVERSE  # noqa: E402

_ET = ZoneInfo("America/New_York")
OPEN_MIN = 9 * 60 + 30        # 09:30 ET
OR_WINDOW = 30                # first 30 min
SESSION_END_MIN = 16 * 60     # 16:00 ET
RVOL_MIN = 1.5
TOP_K = 5
BASELINE_DAYS = 20

# Wider liquid US large/mid-cap candidate pool (superset of the live 30) to size
# the 'widen universe' lever. All are Capital.com-likely + yfinance symbols.
WIDER = sorted(set(ORB_UNIVERSE) | {
    "QCOM", "TXN", "AMAT", "MU", "LRCX", "ADI", "NXPI", "MRVL", "KLAC", "SNPS",
    "PYPL", "SQ", "SHOP", "UBER", "ABNB", "COIN", "PLTR", "SNOW", "NOW", "PANW",
    "BKNG", "GS", "MS", "C", "WFC", "AXP", "SCHW", "BLK", "SPGI", "CB",
    "LLY", "ABBV", "MRK", "TMO", "ABT", "DHR", "BMY", "AMGN", "GILD", "CVS",
    "CAT", "DE", "BA", "GE", "HON", "UPS", "LMT", "RTX", "MMM", "EMR",
    "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "WMB", "OXY", "VLO", "KMI",
    "TGT", "LOW", "NKE", "SBUX", "MCD", "BKNG", "CMG", "MAR", "GM", "F",
})


def _download(symbols: list[str], days: int = 60) -> dict[str, pd.DataFrame]:
    import yfinance as yf
    raw = yf.download(symbols, period=f"{days}d", interval="5m",
                      progress=False, auto_adjust=False, group_by="ticker")
    out: dict[str, pd.DataFrame] = {}
    for s in symbols:
        try:
            df = raw[s] if len(symbols) > 1 else raw
            if df is None or df.empty:
                continue
            df = df[["High", "Low", "Close", "Volume"]].copy().dropna()
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            out[s] = df
        except Exception:  # noqa: BLE001
            continue
    return out


def _et_minute(idx: pd.DatetimeIndex) -> pd.Series:
    et = idx.tz_convert(_ET)
    return pd.Series(et.hour * 60 + et.minute, index=idx), pd.DatetimeIndex(et).normalize().tz_localize(None)


def _per_day(df: pd.DataFrame):
    """Return dict date -> {early_vol, or_high, or_low, broke} reconstructing the ORB pipeline."""
    minute, et_date = _et_minute(df.index)
    df = df.assign(_min=minute.values, _date=et_date)
    res: dict = {}
    for d, g in df.groupby("_date"):
        early = g[(g["_min"] >= OPEN_MIN) & (g["_min"] < OPEN_MIN + OR_WINDOW)]
        if early.empty:
            continue
        later = g[(g["_min"] >= OPEN_MIN + OR_WINDOW) & (g["_min"] < SESSION_END_MIN)]
        or_hi, or_lo = float(early["High"].max()), float(early["Low"].min())
        broke = bool((later["High"] > or_hi).any() or (later["Low"] < or_lo).any()) if not later.empty else False
        res[d] = {"early_vol": float(early["Volume"].sum()), "or_high": or_hi,
                  "or_low": or_lo, "broke": broke}
    return res


def run(universe: list[str], label: str) -> None:
    data = _download(universe)
    perday = {s: _per_day(df) for s, df in data.items()}
    all_dates = sorted({d for s in perday for d in perday[s]})
    if len(all_dates) < BASELINE_DAYS + 2:
        print(f"[{label}] not enough history ({len(all_dates)} days) — skip")
        return
    eligible_counts, entry_counts = [], []
    judged_dates = all_dates[BASELINE_DAYS:]            # need baseline before judging
    for d in judged_dates:
        rvol: dict[str, float] = {}
        for s in universe:
            pd_s = perday.get(s, {})
            if d not in pd_s:
                continue
            prior = [pd_s[x]["early_vol"] for x in all_dates if x < d and x in pd_s][-BASELINE_DAYS:]
            if len(prior) < 5:
                continue
            base = sum(prior) / len(prior)
            if base <= 0:
                continue
            rvol[s] = pd_s[d]["early_vol"] / base
        eligible = sorted((s for s, v in rvol.items() if v >= RVOL_MIN),
                          key=lambda s: rvol[s], reverse=True)[:TOP_K]
        entries = sum(1 for s in eligible if perday[s][d]["broke"])
        eligible_counts.append(len(eligible))
        entry_counts.append(entries)
    n_days = len(judged_dates)
    avg_elig = sum(eligible_counts) / n_days
    avg_entry = sum(entry_counts) / n_days
    total_entries = sum(entry_counts)
    days_to_100 = (100 / avg_entry) if avg_entry > 0 else float("inf")
    weeks = days_to_100 / 5
    print(f"\n===== {label}: {len(data)}/{len(universe)} symbols, {n_days} judged trading days =====")
    print(f"  eligible/day:  avg={avg_elig:.2f}  min={min(eligible_counts)}  max={max(eligible_counts)}")
    print(f"  entries/day:   avg={avg_entry:.2f}  min={min(entry_counts)}  max={max(entry_counts)}  total={total_entries}")
    print(f"  breakout rate among eligible: {total_entries / max(1, sum(eligible_counts)) * 100:.0f}%")
    print(f"  >>> projected days to N=100: {days_to_100:.0f}  (~{weeks:.0f} weeks)")
    # distribution of entries/day
    from collections import Counter
    dist = Counter(entry_counts)
    print("  entries/day histogram: " + "  ".join(f"{k}:{dist[k]}" for k in sorted(dist)))


if __name__ == "__main__":
    run(list(ORB_UNIVERSE), "LIVE-30")
    run(WIDER, "WIDER")
