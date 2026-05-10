"""
Positions API router.
Manages open positions: list, close, modify stop-loss/take-profit.
Dual-mode: uses DB when available, falls back to in-memory engine.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, Path, Query

from src.api.dependencies import get_execution_engine, get_position_repo
from src.api.schemas import (
    ClosedPositionResponse,
    ModifyStopsRequest,
    PositionResponse,
    error_response,
    success_response,
)
from src.execution.execution_engine import ExecutionEngine

router = APIRouter()


def _position_from_db(p) -> dict:
    """Convert a DB Position model to PositionResponse dict."""
    return PositionResponse(
        deal_id=p.deal_id,
        epic=p.epic,
        direction=p.direction,
        size=float(p.size),
        entry_price=float(p.entry_price),
        stop_loss=float(p.stop_loss) if p.stop_loss else None,
        take_profit=float(p.take_profit) if p.take_profit else None,
        current_pnl=float(p.profit_loss) if p.profit_loss else 0.0,
        opened_at=p.opened_at.isoformat() if p.opened_at else None,
    ).model_dump()


def _position_from_engine(p: dict) -> dict:
    """Convert an in-memory engine position dict to PositionResponse dict."""
    return PositionResponse(
        deal_id=p.get("deal_id", ""),
        epic=p.get("epic", ""),
        direction=p.get("direction", ""),
        size=p.get("size", 0.0),
        entry_price=p.get("level", 0.0),
        stop_loss=p.get("stop_level"),
        take_profit=p.get("profit_level"),
        opened_at=p.get("opened_at"),
    ).model_dump()


def _closed_position_from_db(p) -> dict:
    """Convert a DB Position (closed) to ClosedPositionResponse dict."""
    duration = None
    if p.opened_at and p.closed_at:
        duration = max(0, int((p.closed_at - p.opened_at).total_seconds() / 60))
    return ClosedPositionResponse(
        deal_id=p.deal_id,
        epic=p.epic,
        direction=p.direction,
        size=float(p.size),
        entry_price=float(p.entry_price),
        exit_price=float(p.current_price) if p.current_price else None,
        profit_loss=float(p.profit_loss) if p.profit_loss else None,
        stop_loss=float(p.stop_loss) if p.stop_loss else None,
        take_profit=float(p.take_profit) if p.take_profit else None,
        close_reason=p.close_reason,
        opened_at=p.opened_at.isoformat() if p.opened_at else None,
        closed_at=p.closed_at.isoformat() if p.closed_at else None,
        duration_minutes=duration,
    ).model_dump()


@router.get("/closed")
async def list_closed_positions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    close_reason: str | None = Query(default=None),
    epic: str | None = Query(default=None),
    position_repo=Depends(get_position_repo),
):
    """List closed positions with filters, pagination, and aggregates."""
    if position_repo is None:
        return success_response(
            {
                "positions": [],
                "total": 0,
                "page": 1,
                "page_size": page_size,
                "aggregates": {},
            }
        )

    from_dt = datetime.fromisoformat(date_from) if date_from else None
    to_dt = datetime.fromisoformat(date_to) if date_to else None

    offset = (page - 1) * page_size
    positions, total = await position_repo.get_closed_positions(
        limit=page_size,
        offset=offset,
        date_from=from_dt,
        date_to=to_dt,
        close_reason=close_reason,
        epic=epic,
    )

    # H4-API fix: aggregate via SQL (single SUM/COUNT round-trip) instead
    # of pulling up to 10000 rows per page-load. Old path was a DoS vector
    # against Postgres on every dashboard refresh.
    from sqlalchemy import case, func, select  # noqa: PLC0415
    from src.database.models import Position  # noqa: PLC0415

    agg_stmt = (
        select(
            func.coalesce(func.sum(Position.profit_loss), 0).label("total_pnl"),
            func.coalesce(
                func.sum(case((Position.profit_loss > 0, 1), else_=0)), 0
            ).label("win_count"),
            func.coalesce(
                func.sum(case((Position.profit_loss <= 0, 1), else_=0)), 0
            ).label("loss_count"),
            func.coalesce(
                func.avg(case((Position.profit_loss > 0, Position.profit_loss))), 0
            ).label("avg_win"),
            func.coalesce(
                func.avg(case((Position.profit_loss <= 0, Position.profit_loss))), 0
            ).label("avg_loss"),
            func.count(Position.id).label("counted"),
        )
        .where(Position.status == "CLOSED")
        .where(Position.close_reason != "UNRECONCILED")
        .where(Position.profit_loss.is_not(None))
    )
    if from_dt:
        naive_from = from_dt.replace(tzinfo=None) if from_dt.tzinfo else from_dt
        agg_stmt = agg_stmt.where(Position.closed_at >= naive_from)
    if to_dt:
        naive_to = to_dt.replace(tzinfo=None) if to_dt.tzinfo else to_dt
        agg_stmt = agg_stmt.where(Position.closed_at <= naive_to)
    if close_reason:
        agg_stmt = agg_stmt.where(Position.close_reason == close_reason)
    if epic:
        agg_stmt = agg_stmt.where(Position.epic == epic)

    agg_row = (await position_repo.session.execute(agg_stmt)).one()
    counted = int(agg_row.counted or 0)
    win_count = int(agg_row.win_count or 0)
    loss_count = int(agg_row.loss_count or 0)
    win_rate = round(win_count / counted, 4) if counted else 0

    return success_response(
        {
            "positions": [_closed_position_from_db(p) for p in positions],
            "total": total,
            "page": page,
            "page_size": page_size,
            "aggregates": {
                "total_pnl": round(float(agg_row.total_pnl or 0), 2),
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": win_rate,
                "avg_win": round(float(agg_row.avg_win or 0), 2),
                "avg_loss": round(float(agg_row.avg_loss or 0), 2),
            },
        }
    )


@router.get("/")
async def list_positions(
    epic: str | None = None,
    engine: ExecutionEngine = Depends(get_execution_engine),
    position_repo=Depends(get_position_repo),
):
    """List all open positions, optionally filtered by epic."""
    # Try DB first
    if position_repo is not None:
        if epic:
            positions = await position_repo.get_by_epic(epic, status="OPEN")
        else:
            positions = await position_repo.get_open_positions()
        return success_response([_position_from_db(p) for p in positions])

    # Fallback: in-memory engine
    positions = await engine.get_open_positions(epic)
    return success_response([_position_from_engine(p) for p in positions])


@router.get("/{deal_id}")
async def get_position(
    deal_id: str = Path(...),
    engine: ExecutionEngine = Depends(get_execution_engine),
    position_repo=Depends(get_position_repo),
):
    """Get a single position by deal ID."""
    # Try DB first
    if position_repo is not None:
        position = await position_repo.get_by_deal_id(deal_id)
        if position is None:
            return error_response(f"Position {deal_id} not found", 404)
        return success_response(_position_from_db(position))

    # Fallback: in-memory engine
    positions = await engine.get_open_positions()
    position = next((p for p in positions if p.get("deal_id") == deal_id), None)

    if position is None:
        return error_response(f"Position {deal_id} not found", 404)

    return success_response(_position_from_engine(position))


@router.post("/close/{deal_id}")
async def close_position(
    deal_id: str = Path(...),
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Close an open position."""
    result = await engine.close_position(deal_id, reason="API close request")

    if not result.success:
        return error_response(result.error or "Failed to close position")

    return success_response(
        {
            "deal_id": result.deal_id,
            "success": True,
            "execution_time_ms": result.execution_time_ms,
        }
    )


@router.put("/{deal_id}/stops")
async def modify_stops(
    deal_id: str = Path(...),
    body: ModifyStopsRequest = ...,
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Modify stop-loss and/or take-profit for a position."""
    if body.stop_loss is None and body.take_profit is None:
        return error_response("At least one of stop_loss or take_profit must be provided")

    result = await engine.update_stops(deal_id, body.stop_loss)

    if not result.success:
        return error_response(result.error or "Failed to modify stops")

    return success_response(
        {
            "deal_id": deal_id,
            "stop_loss": body.stop_loss,
            "take_profit": body.take_profit,
            "success": True,
        }
    )
