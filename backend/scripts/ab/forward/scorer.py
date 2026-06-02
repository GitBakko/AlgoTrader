from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

_AB = Path(__file__).resolve().parents[1]  # scripts/ab
if str(_AB) not in sys.path:
    sys.path.insert(0, str(_AB))

from factory_stats import block_boot_ci, deflated_sr, metrics  # noqa: E402

MIN_TRADES = 100


def score(realized_rows: list[dict], trial_sharpes_ann: list[float] | None = None) -> dict:
    """Forward kill/promote verdict on a per-trade ledger.

    Aggregates trade net-returns-on-notional into a daily series, then uses the
    same battery as the A/B factory (annualized Sharpe/t + stationary block-bootstrap
    CI + Deflated Sharpe). Verdict:
      - < MIN_TRADES                 -> INSUFFICIENT
      - CI90 includes 0 or Sharpe<=0 -> KILL
      - DSR > 0.95 (or no trial set) -> PROMOTE   else HOLD
    """
    if not realized_rows:
        return {"n_trades": 0, "verdict": "NO DATA"}
    df = pd.DataFrame(realized_rows)
    df["closed_at"] = pd.to_datetime(df["closed_at"], utc=True)
    notional = (df["size"] * df["entry"]).replace(0, pd.NA)
    df["ret"] = df["net_pnl"] / notional
    daily = (df.set_index("closed_at")["ret"]
               .groupby(pd.Grouper(freq="D")).sum().dropna())
    m = metrics(daily, 252)
    lo, _mid, hi = block_boot_ci(daily, 252)
    n_trades = len(df)
    if n_trades < MIN_TRADES:
        verdict = f"INSUFFICIENT ({n_trades}/{MIN_TRADES} trades)"
    elif (lo <= 0 <= hi) or m["sharpe"] <= 0:
        verdict = "KILL (CI90 includes 0 or non-positive Sharpe)"
    else:
        if trial_sharpes_ann:
            dsr = deflated_sr(daily, trial_sharpes_ann, 252)[0]
            verdict = "PROMOTE" if dsr > 0.95 else f"HOLD (DSR {dsr:.3f} < 0.95)"
        else:
            verdict = "PROMOTE (single-hypothesis; rerun with trial set for DSR)"
    return {"n_trades": n_trades, "metrics": m, "ci90": (lo, hi), "verdict": verdict}
