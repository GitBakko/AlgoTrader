"""
Analytics router — portfolio correlation matrix and advanced analytics.
"""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db_session
from src.database.models import Position
from src.monitoring.metrics import MetricsCollector

router = APIRouter()

# QW5 2026-05-15: live WR tracker constants.
_OOS_THRESHOLDS_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data"
    / "config"
    / "optimal_thresholds.json"
)
_MIN_TRADES_FOR_WR = 5
_OVERFIT_DELTA_THRESHOLD = -0.15

EPICS = [
    "XAUUSD",
    "BTCUSD",
    "US500",
    "WTIUSD",
    "EURUSD",
    "NVDA",
    "TSLA",
    "XAGUSD",
    "DE40",
    "SOLUSD",
    "ETHUSD",
    "BNBUSD",
    "DOGUSD",
    "DASHUSD",
    "ICPUSD",
    "NATGAS",
    "COPPER",
    "PLATINUM",
    "GBPUSD",
    "USDJPY",
    "NAS100",
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
        epic_dir = data_dir / epic / timeframe
        if not epic_dir.exists():
            continue
        files = sorted(epic_dir.glob("*.parquet"))
        if not files:
            continue
        try:
            # Read recent parquet files (last ~4 months covers 90 days)
            recent_files = files[-4:] if len(files) > 4 else files
            dfs = []
            for f in recent_files:
                chunk = pl.read_parquet(f)
                # Normalize timestamp timezone to avoid schema mismatch on concat
                if "timestamp" in chunk.columns:
                    ts_col = chunk["timestamp"]
                    if ts_col.dtype == pl.Datetime("us", "UTC"):
                        chunk = chunk.with_columns(ts_col.dt.replace_time_zone(None))
                dfs.append(chunk)
            df = pl.concat(dfs) if len(dfs) > 1 else dfs[0]
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


@router.get("/correlation-regime")
async def get_correlation_regime(request: Request):
    """Get current correlation regime from trading loop."""
    loop = getattr(request.app.state, "paper_loop", None)
    if loop is None:
        return {
            "success": True,
            "data": {"regime": "unknown", "reason": "trading loop not running"},
        }
    return {"success": True, "data": {"regime": loop._correlation_regime}}


@router.get("/regime/status")
async def get_regime_status(request: Request):
    """Get current regime gate status from trading loop."""
    loop = getattr(request.app.state, "paper_loop", None)
    if loop is None:
        return {
            "success": True,
            "data": {"enabled": False, "reason": "trading loop not running"},
        }
    gate = getattr(loop, "_regime_gate", None)
    if gate is None:
        return {
            "success": True,
            "data": {"enabled": False, "reason": "regime gate not initialized"},
        }
    return {"success": True, "data": {"enabled": True, **gate.get_stats()}}


def _load_oos_win_rates() -> dict[str, float]:
    """Load per-epic OOS win-rate expectations from optimal_thresholds.json.

    Returns {} on any failure so the endpoint still works without the JSON.
    """
    try:
        with open(_OOS_THRESHOLDS_PATH) as fh:
            data = json.load(fh)
        return {
            epic: float(info["win_rate"])
            for epic, info in data.get("per_asset", {}).items()
            if info.get("win_rate") is not None
        }
    except Exception:
        return {}


@router.get("/live-wr")
async def get_live_win_rate(
    window_days: int = Query(default=21, ge=1, le=365),
    session: AsyncSession | None = Depends(get_db_session),
) -> dict[str, Any]:
    """Per-instrument live win-rate over the last `window_days` (QW5).

    Compares the realized close outcomes against the OOS win-rate baked into
    optimal_thresholds.json. Flags any epic whose live WR is more than
    15 pp below the OOS expectation (likely walk-forward overfit).
    """
    if session is None:
        return {
            "success": True,
            "data": {
                "window_days": window_days,
                "generated_at": datetime.now(UTC).isoformat(),
                "instruments": {},
                "overfit_flags": [],
                "warning": "no DB session available",
            },
        }

    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=window_days)
    stmt = (
        select(Position.epic, Position.close_reason)
        .where(Position.status == "CLOSED")
        .where(Position.closed_at.is_not(None))
        .where(Position.closed_at >= cutoff)
    )
    rows = (await session.execute(stmt)).all()

    by_epic: dict[str, dict[str, int]] = {}
    for epic, reason in rows:
        bucket = by_epic.setdefault(epic, {"trades": 0, "wins": 0})
        bucket["trades"] += 1
        if reason == "TP":
            bucket["wins"] += 1

    oos_wr = _load_oos_win_rates()
    instruments: dict[str, dict[str, Any]] = {}
    overfit_flags: list[str] = []

    for epic, counts in by_epic.items():
        if counts["trades"] < _MIN_TRADES_FOR_WR:
            continue
        live_wr = counts["wins"] / counts["trades"]
        epic_oos = oos_wr.get(epic)
        delta = (live_wr - epic_oos) if epic_oos is not None else None
        instruments[epic] = {
            "trades": counts["trades"],
            "wins": counts["wins"],
            "wr": round(live_wr, 4),
            "oos_wr": round(epic_oos, 4) if epic_oos is not None else None,
            "oos_delta": round(delta, 4) if delta is not None else None,
        }
        MetricsCollector.update_live_wr(epic=epic, live_wr=live_wr, oos_delta=delta)
        if delta is not None and delta < _OVERFIT_DELTA_THRESHOLD:
            overfit_flags.append(
                f"{epic}: live {live_wr:.3f} vs OOS {epic_oos:.3f} "
                f"(delta {delta:+.3f}) — overfit suspect"
            )

    return {
        "success": True,
        "data": {
            "window_days": window_days,
            "generated_at": datetime.now(UTC).isoformat(),
            "min_trades_threshold": _MIN_TRADES_FOR_WR,
            "overfit_delta_threshold": _OVERFIT_DELTA_THRESHOLD,
            "instruments": instruments,
            "overfit_flags": overfit_flags,
        },
    }
