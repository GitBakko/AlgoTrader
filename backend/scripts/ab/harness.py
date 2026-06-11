"""Leak-free A/B backtest harness — shared evaluation core.

All Tier-1 alpha candidates feed a per-asset DAILY target-weight matrix into the
same DailyBacktester so results are apples-to-apples, net of cost, OOS.

Leak discipline (hard rules, learned the hard way 2026-05-28):
- A weight w[t] is DECIDED from data up to and including day t; it earns the
  return realized t -> t+1. The backtester applies weights.shift(1) * returns,
  so a signal that only uses past/current data can never look ahead.
- Costs: half the full bid-ask spread per unit of turnover (so a full
  open+close round-trip pays one full spread). Overnight swap charged per day
  on the held |weight|.
- Metrics are reported on the OOS slice (date >= oos_start) separately from
  in-sample, and Sharpe is annualized from the daily strategy-return series.

Run scripts from backend/.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]  # backend/
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.backtest.costs import ASSET_SPREADS, OVERNIGHT_RATES  # noqa: E402
from src.data.storage import ParquetStorageManager  # noqa: E402

SLIP = 0.10  # extra slippage as fraction of spread
TRADING_DAYS = 252
_DEFAULT_SWAP = 1.5e-5


def load_daily_prices(epics: list[str]) -> pd.DataFrame:
    """Wide DataFrame [date x epic] of daily close. Dates = union, NaN where missing."""
    st = ParquetStorageManager()
    series = {}
    for e in epics:
        df = st.read_candles(e, "1d")
        if df.is_empty():
            continue
        pdf = df.select(["timestamp", "close"]).to_pandas()
        pdf["date"] = pd.to_datetime(pdf["timestamp"]).dt.normalize()
        s = pdf.dropna(subset=["close"]).groupby("date")["close"].last()
        series[e] = s
    if not series:
        raise RuntimeError("no daily price data loaded")
    px = pd.DataFrame(series).sort_index()
    # Different calendars (24/7 crypto vs weekday stocks/FX/commodities) are unioned
    # onto one index; forward-fill bridges non-trading gaps so per-asset rolling
    # signals don't blow up to NaN. Non-trading days then carry a 0 return (price
    # unchanged), which is correct. Leading NaN (pre-listing) stays NaN -> weight 0.
    px = px.ffill(limit=7)
    return px


def half_spread_frac(epic: str, price: pd.Series) -> pd.Series:
    """Per-unit-turnover cost fraction = (full_spread/price)/2 * (1+slip)."""
    sp = ASSET_SPREADS.get(epic)
    if sp is None:
        sp_series = price * 0.0008  # proportional fallback for unlisted (see costs.py)
    else:
        sp_series = pd.Series(sp, index=price.index)
    with np.errstate(divide="ignore", invalid="ignore"):
        frac = (sp_series / price) * 0.5 * (1 + SLIP)
    return frac.replace([np.inf, -np.inf], np.nan).fillna(0.0)


def swap_abs(epic: str) -> float:
    r = OVERNIGHT_RATES.get(epic, {"long": -_DEFAULT_SWAP})["long"]
    return abs(r)


@dataclass
class Metrics:
    n_days: int
    sharpe: float
    ann_return: float
    ann_vol: float
    hit_pct: float
    max_dd: float
    t_stat: float
    avg_turnover: float
    total_return: float

    def line(self, label: str) -> str:
        return (
            f"  {label:<10} n={self.n_days:<5} Sharpe={self.sharpe:>6.2f}  "
            f"ret={self.ann_return*100:>6.1f}%  vol={self.ann_vol*100:>5.1f}%  "
            f"hit={self.hit_pct:>4.1f}%  maxDD={self.max_dd*100:>6.1f}%  "
            f"t={self.t_stat:>5.2f}  turn={self.avg_turnover:.2f}"
        )


def _metrics(daily: pd.Series, turnover: pd.Series) -> Metrics:
    d = daily.dropna()
    n = len(d)
    if n < 5:
        return Metrics(n, 0, 0, 0, 0, 0, 0, 0, 0)
    mean, std = d.mean(), d.std(ddof=1)
    sharpe = (mean / std * np.sqrt(TRADING_DAYS)) if std > 0 else 0.0
    eq = (1 + d).cumprod()
    dd = (eq / eq.cummax() - 1).min()
    t = (mean / (std / np.sqrt(n))) if std > 0 else 0.0
    return Metrics(
        n_days=n,
        sharpe=sharpe,
        ann_return=mean * TRADING_DAYS,
        ann_vol=std * np.sqrt(TRADING_DAYS),
        hit_pct=(d > 0).mean() * 100,
        max_dd=dd,
        t_stat=t,
        avg_turnover=float(turnover.reindex(d.index).fillna(0).mean()),
        total_return=eq.iloc[-1] - 1,
    )


class DailyBacktester:
    """Evaluate a per-asset daily target-weight matrix, net of cost, OOS."""

    def __init__(
        self,
        prices: pd.DataFrame,
        cost_bps: dict[str, float] | None = None,
        ret_clip: float | None = None,
        swap_bps: dict[str, float] | None = None,
    ):
        """cost_bps: optional per-epic CONSTANT fractional cost per unit turnover
        (use for long history where absolute spread/historical-price explodes, e.g.
        BTC at $300 vs a current $55 spread). ret_clip: winsorize daily returns to
        +/- ret_clip to kill data glitches (e.g. early-crypto yfinance spikes).
        swap_bps: optional per-epic CONSTANT daily financing fraction on held |weight|
        (overrides OVERNIGHT_RATES). Set 0 to isolate price signal from carry, e.g. a
        FX long/short book where flat-default swap would wrongly charge both legs."""
        self.prices = prices
        self.swap_bps = swap_bps
        rets = prices.pct_change()
        if ret_clip is not None:
            rets = rets.clip(-ret_clip, ret_clip)
        self.returns = rets
        if cost_bps is not None:
            self.cost_frac = pd.DataFrame(
                {e: pd.Series(float(cost_bps.get(e, 0.0)), index=prices.index)
                 for e in prices.columns}
            )
        else:
            self.cost_frac = pd.DataFrame(
                {e: half_spread_frac(e, prices[e]) for e in prices.columns}
            )

    def run(self, weights: pd.DataFrame, oos_start: str | pd.Timestamp) -> dict:
        """weights: [date x epic] target weights (decided at close of `date`).

        Returns dict with full + OOS Metrics and the net daily series.
        """
        w = weights.reindex(index=self.prices.index, columns=self.prices.columns).fillna(0.0)
        ret = self.returns
        gross = (w.shift(1) * ret)
        turnover_pa = (w - w.shift(1)).abs()
        cost = turnover_pa * self.cost_frac
        if self.swap_bps is not None:
            swap = pd.Series({e: float(self.swap_bps.get(e, 0.0)) for e in w.columns})
        else:
            swap = pd.Series({e: swap_abs(e) for e in w.columns})
        fin = w.shift(1).abs() * swap  # per day held
        net = gross - cost - fin
        port = net.sum(axis=1)
        turn = turnover_pa.sum(axis=1)

        oos_start = pd.Timestamp(oos_start).normalize()
        full = _metrics(port, turn)
        oos = _metrics(port[port.index >= oos_start], turn[turn.index >= oos_start])
        return {"full": full, "oos": oos, "daily": port, "turnover": turn}


def normalize_book(weights: pd.DataFrame, gross: float = 1.0) -> pd.DataFrame:
    """Scale each row so sum|w| == gross (leverage 1 book). Rows of all-zero stay zero."""
    s = weights.abs().sum(axis=1).replace(0, np.nan)
    return weights.div(s, axis=0).mul(gross).fillna(0.0)


def oos_split_date(prices: pd.DataFrame, oos_frac: float = 0.4) -> pd.Timestamp:
    idx = prices.dropna(how="all").index
    return idx[int(len(idx) * (1 - oos_frac))]
