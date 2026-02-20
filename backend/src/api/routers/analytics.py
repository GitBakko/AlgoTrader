"""
Analytics router — portfolio correlation matrix and advanced analytics.
"""

from pathlib import Path

import numpy as np
import polars as pl
from fastapi import APIRouter, Query

router = APIRouter()

EPICS = [
    "XAUUSD", "BTCUSD", "US500", "WTIUSD", "EURUSD", "NVDA", "TSLA",
    "XAGUSD", "DE40", "SOLUSD", "ETHUSD", "BNBUSD", "DOGUSD", "DASHUSD",
    "ICPUSD", "NATGAS", "COPPER", "PLATINUM", "GBPUSD", "USDJPY", "NAS100",
]


@router.get("/correlation-matrix")
async def get_correlation_matrix(
    days: int = Query(default=90, ge=7, le=365),
    timeframe: str = Query(default="1h"),
):
    """Compute pairwise return correlations across all traded assets."""
    returns_dict: dict[str, np.ndarray] = {}
    data_dir = Path("data/historical")

    for epic in EPICS:
        pattern = f"{epic}_{timeframe}_*.parquet"
        files = sorted(data_dir.glob(pattern))
        if not files:
            continue
        try:
            df = pl.read_parquet(files[-1])
        except Exception:
            continue
        if "close" not in df.columns or len(df) < 10:
            continue
        closes = df["close"].to_numpy().astype(np.float64)
        # Log returns
        rets = np.diff(np.log(np.maximum(closes, 1e-10)))
        # Trim to requested period
        periods_per_day = 24 if timeframe == "1h" else 6 if timeframe == "4h" else 1
        n_periods = days * periods_per_day
        rets = rets[-n_periods:]
        if len(rets) >= 10:
            returns_dict[epic] = rets

    if not returns_dict:
        return {"success": True, "data": {"epics": [], "matrix": []}}

    # Align to common length
    common_len = min(len(v) for v in returns_dict.values())
    if common_len < 10:
        return {"success": True, "data": {"epics": [], "matrix": []}}

    aligned_epics = sorted(returns_dict.keys())
    n = len(aligned_epics)
    matrix = np.eye(n)

    for i in range(n):
        r1 = returns_dict[aligned_epics[i]][-common_len:]
        for j in range(i + 1, n):
            r2 = returns_dict[aligned_epics[j]][-common_len:]
            corr = float(np.corrcoef(r1, r2)[0, 1])
            matrix[i][j] = corr
            matrix[j][i] = corr

    return {
        "success": True,
        "data": {
            "epics": aligned_epics,
            "matrix": np.round(matrix, 3).tolist(),
            "period_days": days,
            "data_points": common_len,
        },
    }
