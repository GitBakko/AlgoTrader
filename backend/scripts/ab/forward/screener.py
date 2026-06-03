from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Callable
from zoneinfo import ZoneInfo

import pandas as pd
from loguru import logger

# (symbols, days) -> {symbol: DataFrame[Volume] with tz-aware UTC DatetimeIndex}
Fetch5m = Callable[[list[str], int], dict[str, "pd.DataFrame"]]

SESSION_OPEN_ET = time(9, 30)  # US regular cash open in ET wall-clock (DST-correct)


def _default_fetch_5m(symbols: list[str], days: int) -> dict[str, pd.DataFrame]:
    """Real fetch: yfinance 5-min bars, last `days` days, per symbol, UTC index."""
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    raw = yf.download(symbols, period=f"{days}d", interval="5m",
                      progress=False, auto_adjust=False, group_by="ticker")
    for s in symbols:
        try:
            df = raw[s] if len(symbols) > 1 else raw
            if df is None or df.empty or "Volume" not in df.columns:
                continue
            df = df[["Volume"]].copy()
            if df.index.tz is None:
                df.index = df.index.tz_localize("UTC")
            else:
                df.index = df.index.tz_convert("UTC")
            out[s] = df
        except Exception as e:  # noqa: BLE001 — degrade per-symbol, never abort the screen
            logger.warning(f"[screener] {s} fetch/parse failed: {e}")
    return out


@dataclass
class RvolScreener:
    fetch_5m: Fetch5m | None = None
    rvol_min: float = 1.5
    top_k: int = 5
    or_window_min: int = 30
    baseline_days: int = 20

    def _early_volume_by_day(self, df: pd.DataFrame) -> pd.Series:
        """Sum of Volume in [09:30, 09:30+or_window_min) ET, grouped by ET calendar date."""
        et_idx = df.index.tz_convert(ZoneInfo("America/New_York"))
        et_minutes = et_idx.hour * 60 + et_idx.minute
        open_min = SESSION_OPEN_ET.hour * 60 + SESSION_OPEN_ET.minute
        mask = (et_minutes >= open_min) & (et_minutes < open_min + self.or_window_min)
        early = df.loc[mask]
        if early.empty:
            return pd.Series(dtype="float64")
        # Group by ET calendar date (tz-naive date key)
        et_dates = pd.DatetimeIndex(et_idx[mask]).normalize().tz_localize(None)
        return early.groupby(et_dates)["Volume"].sum()

    def select(self, symbols: list[str], now: datetime) -> dict:
        data = (self.fetch_5m or _default_fetch_5m)(symbols, self.baseline_days)
        # today key = ET calendar date of now (tz-naive, matching groupby key above)
        today = pd.Timestamp(now.astimezone(ZoneInfo("America/New_York")).date())
        rvol: dict[str, float] = {}
        for s in symbols:
            df = data.get(s)
            if df is None or df.empty:
                continue
            early = self._early_volume_by_day(df)
            if today not in early.index:
                continue
            baseline = early[early.index < today].tail(self.baseline_days)
            base = float(baseline.mean()) if len(baseline) else 0.0
            if base <= 0:
                continue
            rvol[s] = float(early[today]) / base
        ranked = sorted((s for s, v in rvol.items() if v >= self.rvol_min),
                        key=lambda s: rvol[s], reverse=True)
        return {"rvol": rvol, "eligible": set(ranked[: self.top_k])}
