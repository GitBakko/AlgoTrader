from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

_AB = Path(__file__).resolve().parents[1]  # scripts/ab
if str(_AB) not in sys.path:
    sys.path.insert(0, str(_AB))

from factory_stats import block_boot_ci, deflated_sr, metrics  # noqa: E402

MIN_TRADES = 100


def _daily_returns(df: pd.DataFrame) -> pd.Series:
    """Per-BUSINESS-day net returns-on-notional.

    Weekend-stamped closes (none expected on US stocks; defensive for future
    crypto hypotheses) roll forward to the next business day so no P&L is lost.
    No-trade weekdays count 0.0 (idle capital); weekends are EXCLUDED so the
    series length matches the ppy=252 annualization (calendar-day padding
    deflated Sharpe by ~sqrt(252/365)).
    """
    ret = df.set_index("closed_at")["ret"]
    dow = ret.index.dayofweek
    shift_days = np.where(dow == 5, 2, np.where(dow == 6, 1, 0))
    ret.index = ret.index + pd.to_timedelta(shift_days, unit="D")
    daily = ret.groupby(pd.Grouper(freq="D")).sum()
    bdays = pd.bdate_range(daily.index.min(), daily.index.max(), tz=daily.index.tz)
    return daily.reindex(bdays, fill_value=0.0)


def score(realized_rows: list[dict], trial_sharpes_ann: list[float] | None = None) -> dict:
    """Forward kill/promote verdict on a per-trade ledger.

    Aggregates trade net-returns-on-notional into a business-day series, then
    uses the same battery as the A/B factory (annualized Sharpe/t + stationary
    block-bootstrap CI + Deflated Sharpe). Verdict:
      - < MIN_TRADES                 -> INSUFFICIENT
      - CI not computable (few days) -> INSUFFICIENT (never promote blind)
      - CI90 includes 0 or Sharpe<=0 -> KILL
      - DSR > 0.95 (or no trial set) -> PROMOTE   else HOLD
    """
    if not realized_rows:
        return {"n_trades": 0, "verdict": "NO DATA"}
    df = pd.DataFrame(realized_rows)
    if "close_reason" in df.columns:
        df = df[df["close_reason"] != "PENDING_RECONCILE"]
    if df.empty:
        return {"n_trades": 0, "verdict": "NO DATA"}
    df["closed_at"] = pd.to_datetime(df["closed_at"], utc=True)
    notional = (df["size"] * df["entry"]).replace(0, pd.NA)
    df["ret"] = df["net_pnl"] / notional
    daily = _daily_returns(df)
    m = metrics(daily, 252)
    # adaptive block: factory default 21 needs >=105 days; at the N>=100-trade
    # gate the forward ledger spans ~45-60 business days, so scale the block
    # down (block*5 <= n) instead of silently returning a NaN CI.
    block = min(21, max(2, len(daily) // 5))
    lo, _mid, hi = block_boot_ci(daily, 252, block=block)
    n_trades = len(df)
    if n_trades < MIN_TRADES:
        verdict = f"INSUFFICIENT ({n_trades}/{MIN_TRADES} trades)"
    elif np.isnan(lo) or np.isnan(hi):
        # NaN comparisons are False: without this guard the CI gate was
        # silently bypassed and a positive-Sharpe series PROMOTED un-vetted.
        verdict = f"INSUFFICIENT (CI unavailable: only {len(daily)} business days)"
    elif (lo <= 0 <= hi) or m["sharpe"] <= 0:
        verdict = "KILL (CI90 includes 0 or non-positive Sharpe)"
    else:
        if trial_sharpes_ann:
            dsr = deflated_sr(daily, trial_sharpes_ann, 252)[0]
            verdict = "PROMOTE" if dsr > 0.95 else f"HOLD (DSR {dsr:.3f} < 0.95)"
        else:
            verdict = "PROMOTE (single-hypothesis; rerun with trial set for DSR)"
    return {"n_trades": n_trades, "n_days": len(daily), "metrics": m,
            "ci90": (lo, hi), "verdict": verdict}
