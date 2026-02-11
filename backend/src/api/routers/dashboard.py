"""
Dashboard API router.
Provides overview data, equity curve, and recent trade history.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query

from src.api.dependencies import get_execution_engine, get_risk_manager
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
    engine: ExecutionEngine = Depends(get_execution_engine),
    risk_mgr: RiskManager = Depends(get_risk_manager),
):
    """Get dashboard overview with key metrics."""
    positions = await engine.get_open_positions()
    state = risk_mgr.drawdown_monitor.state

    overview = DashboardOverview(
        equity=state.current_equity,
        daily_pnl=state.daily_pnl,
        total_pnl=state.current_equity - risk_mgr.initial_equity,
        open_positions_count=len(positions),
        circuit_breaker_active=state.circuit_breaker_active,
        trading_mode="paper" if engine.mode == ExecutionMode.PAPER else "live",
    )

    return success_response(overview.model_dump())


@router.get("/equity-curve")
async def get_equity_curve(
    days: int = Query(default=30, ge=1, le=365),
):
    """
    Get equity curve data points.
    MVP: returns placeholder data. Full implementation with DB in Phase 5.
    """
    # Placeholder: single point with current state
    now = datetime.now(timezone.utc).isoformat()
    points = [
        EquityCurvePoint(date=now, equity=10000.0, drawdown_pct=0.0).model_dump()
    ]

    return success_response(points)


@router.get("/recent-trades")
async def get_recent_trades(
    limit: int = Query(default=20, ge=1, le=100),
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """
    Get recent closed trades.
    MVP: returns trades from in-memory position tracker.
    """
    # Paper mode tracks positions in memory; closed ones are removed
    # For MVP, return empty list (full history requires DB)
    return success_response([])
