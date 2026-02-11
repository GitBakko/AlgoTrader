"""
Dashboard API router.
Provides overview data, equity curve, and recent trade history.
Dual-mode: uses DB when available, falls back to in-memory state.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request

from src.api.dependencies import (
    get_execution_engine,
    get_position_repo,
    get_risk_manager,
    get_trade_repo,
)
from src.api.schemas import (
    DashboardOverview,
    EquityCurvePoint,
    TradeResponse,
    success_response,
)
from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.risk.risk_manager import RiskManager

router = APIRouter()


@router.get("/overview")
async def get_overview(
    request: Request,
    engine: ExecutionEngine = Depends(get_execution_engine),
    risk_mgr: RiskManager = Depends(get_risk_manager),
    position_repo=Depends(get_position_repo),
    trade_repo=Depends(get_trade_repo),
):
    """Get dashboard overview with key metrics."""
    state = risk_mgr.drawdown_monitor.state

    # Count open positions
    if position_repo is not None:
        open_positions = await position_repo.get_open_positions()
        open_count = len(open_positions)
    else:
        positions = await engine.get_open_positions()
        open_count = len(positions)

    # Get trade stats from DB if available
    win_rate = 0.0
    if trade_repo is not None:
        now = datetime.now(timezone.utc)
        summary = await trade_repo.get_pnl_summary(
            now - timedelta(days=30), now
        )
        if summary["trade_count"] > 0:
            win_rate = summary.get("win_rate", 0.0)

    overview = DashboardOverview(
        equity=state.current_equity,
        daily_pnl=state.daily_pnl,
        total_pnl=state.current_equity - risk_mgr.initial_equity,
        open_positions_count=open_count,
        win_rate=win_rate,
        circuit_breaker_active=state.circuit_breaker_active,
        trading_mode="paper" if engine.mode == ExecutionMode.PAPER else "live",
    )

    data = overview.model_dump()

    # Add paper trading loop status
    paper_loop = getattr(request.app.state, "paper_loop", None)
    if paper_loop is not None:
        data["paper_trading"] = {
            "running": paper_loop.is_running,
            "iteration_count": paper_loop.iteration_count,
            "signal_count": paper_loop.signal_count,
            "trade_count": paper_loop.trade_count,
            "last_run": paper_loop.last_run.isoformat() if paper_loop.last_run else None,
            "last_signals": paper_loop.last_signals,
        }

    return success_response(data)


@router.get("/equity-curve")
async def get_equity_curve(
    days: int = Query(default=30, ge=1, le=365),
):
    """
    Get equity curve data points.
    Returns placeholder data (full equity curve tracking requires account snapshots).
    """
    now = datetime.now(timezone.utc).isoformat()
    points = [
        EquityCurvePoint(date=now, equity=10000.0, drawdown_pct=0.0).model_dump()
    ]

    return success_response(points)


@router.get("/recent-trades")
async def get_recent_trades(
    limit: int = Query(default=20, ge=1, le=100),
    trade_repo=Depends(get_trade_repo),
):
    """Get recent closed trades."""
    # Try DB first
    if trade_repo is not None:
        trades = await trade_repo.get_recent_trades(hours=168)
        result = [
            TradeResponse(
                deal_id=t.deal_reference or f"trade-{t.id}",
                epic=t.epic,
                direction=t.direction,
                size=float(t.size),
                entry_price=float(t.price),
                pnl=float(t.profit_loss) if t.profit_loss else None,
                timestamp=t.executed_at.isoformat() if t.executed_at else "",
            ).model_dump()
            for t in trades[:limit]
        ]
        return success_response(result)

    # Fallback: no trade history without DB
    return success_response([])
