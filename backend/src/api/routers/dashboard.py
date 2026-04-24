"""
Dashboard API router.
Provides overview data, equity curve, and recent trade history.
Dual-mode: uses DB when available, falls back to in-memory state.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger

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
from src.risk.risk_manager import RiskManager
from src.utils.config import get_settings

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

    # Count open positions (graceful DB fallback)
    open_count = 0
    try:
        if position_repo is not None:
            open_positions = await position_repo.get_open_positions()
            open_count = len(open_positions)
        else:
            positions = await engine.get_open_positions()
            open_count = len(positions)
    except Exception as e:
        logger.debug(f"DB position query failed, using in-memory: {e}")
        positions = await engine.get_open_positions()
        open_count = len(positions)

    # Get trade stats from DB if available (graceful fallback)
    win_rate = 0.0
    if trade_repo is not None:
        try:
            now = datetime.now(UTC)
            summary = await trade_repo.get_pnl_summary(now - timedelta(days=30), now)
            if summary["trade_count"] > 0:
                win_rate = summary.get("win_rate", 0.0)
        except Exception as e:
            logger.debug(f"DB trade summary query failed: {e}")

    # Compute realized P&L from closed positions (not equity delta)
    realized_pnl = 0.0
    if position_repo is not None:
        try:
            closed = await position_repo.get_closed_in_period(
                datetime(2020, 1, 1, tzinfo=UTC),
                datetime.now(UTC),
            )
            realized_pnl = sum(float(p.profit_loss) for p in closed if p.profit_loss is not None)
        except Exception as e:
            logger.debug(f"DB realized P&L query failed: {e}")

    # Fallback: in-memory trade history from paper loop
    if realized_pnl == 0.0:
        paper_loop = getattr(request.app.state, "paper_loop", None)
        if paper_loop is not None:
            realized_pnl = sum(h.get("pnl", 0) for h in paper_loop._trade_history)

    # Today's realized P&L (closed trades only, not equity delta)
    today_realized_pnl = 0.0
    if position_repo is not None:
        try:
            today_start = datetime.now(UTC).replace(
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            closed_today = await position_repo.get_closed_in_period(
                today_start,
                datetime.now(UTC),
            )
            today_realized_pnl = sum(
                float(p.profit_loss) for p in closed_today if p.profit_loss is not None
            )
        except Exception as e:
            logger.debug(f"DB today realized P&L query failed: {e}")

    # Live unrealized P&L from open positions (broker authoritative)
    live_unrealized = 0.0
    try:
        open_positions_upl = await engine.get_open_positions()
        for p in open_positions_upl or []:
            # p can be dict (tracker) or Position model — handle both.
            upl = p.get("upl") if isinstance(p, dict) else getattr(p, "upl", None)
            if upl is not None:
                live_unrealized += float(upl)
    except Exception as e:
        logger.debug(f"Live UPL aggregation failed: {e}")

    # Fetch account currency from broker (one-shot, cached per request)
    currency = "USD"
    try:
        broker_client = getattr(request.app.state, "broker_client", None)
        if broker_client is not None:
            accounts = await broker_client.get_accounts()
            if accounts:
                currency = accounts[0].currency or "USD"
    except Exception as e:
        logger.debug(f"Account currency fetch failed: {e}")

    live_daily_pnl = round(today_realized_pnl + live_unrealized, 2)

    overview = DashboardOverview(
        equity=state.current_equity,
        daily_pnl=state.daily_pnl,
        today_realized_pnl=round(today_realized_pnl, 2),
        total_pnl=round(realized_pnl, 2),
        open_positions_count=open_count,
        win_rate=win_rate,
        circuit_breaker_active=state.circuit_breaker_active,
        trading_mode=engine.mode.value.lower(),
    )

    data = overview.model_dump()
    data["live_daily_pnl"] = live_daily_pnl
    data["live_unrealized_pnl"] = round(live_unrealized, 2)
    data["currency"] = currency

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
    position_repo=Depends(get_position_repo),
    risk_mgr: RiskManager = Depends(get_risk_manager),
):
    """
    Get equity curve data points from closed positions.
    Appends a live "now" point from the broker/drawdown monitor equity
    so the curve always ends at the real current equity value.
    """
    if position_repo is not None:
        try:
            date_from = datetime.now(UTC) - timedelta(days=days)
            stats = await position_repo.get_performance_stats(date_from=date_from)
            curve = stats.get("equity_curve", [])
            if curve:
                initial = get_settings().initial_capital
                points = [
                    EquityCurvePoint(
                        date=pt["date"],
                        equity=initial + pt["value"],
                        drawdown_pct=pt.get("drawdown_pct", 0.0),
                        daily_pnl=pt.get("daily_pnl", 0.0),
                        trade_count=pt.get("trade_count", 0),
                        win_count=pt.get("win_count", 0),
                        cumulative_trades=pt.get("cumulative_trades", 0),
                        cumulative_win_rate=pt.get("cumulative_win_rate", 0.0),
                    ).model_dump()
                    for pt in curve
                ]

                # Append live equity point so curve matches the dashboard badge
                live_equity = risk_mgr.drawdown_monitor.state.current_equity
                if live_equity and live_equity > 0:
                    today = datetime.now(UTC).strftime("%Y-%m-%d")
                    last_pt = points[-1]
                    if last_pt["date"] == today:
                        # Replace today's point with live equity
                        last_pt["equity"] = round(live_equity, 2)
                    else:
                        # Add a new point for today
                        points.append(
                            EquityCurvePoint(
                                date=today,
                                equity=round(live_equity, 2),
                                drawdown_pct=round(
                                    risk_mgr.drawdown_monitor.state.current_drawdown_pct * 100,
                                    2,
                                ),
                            ).model_dump()
                        )

                return success_response(points)
        except Exception as e:
            logger.debug(f"Equity curve from DB failed: {e}")

    # Fallback: single placeholder point
    now = datetime.now(UTC).isoformat()
    points = [
        EquityCurvePoint(
            date=now, equity=get_settings().initial_capital, drawdown_pct=0.0
        ).model_dump()
    ]

    return success_response(points)


@router.get("/recent-trades")
async def get_recent_trades(
    limit: int = Query(default=20, ge=1, le=100),
    trade_repo=Depends(get_trade_repo),
):
    """Get recent closed trades."""
    # Try DB first (graceful fallback)
    if trade_repo is not None:
        try:
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
        except Exception as e:
            logger.debug(f"DB recent trades query failed: {e}")

    # Fallback: no trade history without DB
    return success_response([])
