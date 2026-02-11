"""
Backtest API router.
Run backtests and retrieve results.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Path, Request

from src.api.schemas import (
    BacktestRunRequest,
    BacktestRunResponse,
    error_response,
    success_response,
)

router = APIRouter()

MAX_BACKTEST_RUNS = 100


@router.post("/run")
async def run_backtest(
    request: Request,
    body: BacktestRunRequest,
):
    """
    Start a new backtest run.
    MVP: stores results in-memory. Full implementation uses BacktestEngine.
    """
    run_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()

    # MVP: create placeholder run (actual BacktestEngine integration in Phase 5)
    run = BacktestRunResponse(
        id=run_id,
        epic=body.epic,
        status="completed",
        total_return_pct=0.0,
        sharpe_ratio=0.0,
        max_drawdown_pct=0.0,
        total_trades=0,
        win_rate=0.0,
        created_at=now,
    )

    # Store in app state
    runs: dict = request.app.state.backtest_runs
    runs[run_id] = {
        "summary": run.model_dump(),
        "config": body.model_dump(),
        "equity_curve": [],
        "trades": [],
        "metrics": {
            "total_return_pct": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "calmar_ratio": 0.0,
            "max_drawdown_pct": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
        },
    }

    # Evict oldest runs if over limit
    if len(runs) > MAX_BACKTEST_RUNS:
        oldest = sorted(runs, key=lambda k: runs[k]["summary"].get("created_at", ""))
        for key in oldest[: len(runs) - MAX_BACKTEST_RUNS]:
            del runs[key]

    return success_response(run.model_dump())


@router.get("/runs")
async def list_backtest_runs(request: Request):
    """List all backtest runs."""
    runs: dict = request.app.state.backtest_runs
    summaries = [run["summary"] for run in runs.values()]

    # Most recent first
    summaries.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return success_response(summaries)


@router.get("/runs/{run_id}")
async def get_backtest_run(
    request: Request,
    run_id: str = Path(...),
):
    """Get detailed backtest results including equity curve and trades."""
    runs: dict = request.app.state.backtest_runs
    run = runs.get(run_id)

    if run is None:
        return error_response(f"Backtest run {run_id} not found", 404)

    return success_response(run)
