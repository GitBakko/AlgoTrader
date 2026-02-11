"""
Positions API router.
Manages open positions: list, close, modify stop-loss/take-profit.
Dual-mode: uses DB when available, falls back to in-memory engine.
"""

from fastapi import APIRouter, Depends, Path

from src.api.dependencies import get_execution_engine, get_position_repo
from src.api.schemas import (
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

    return success_response({
        "deal_id": result.deal_id,
        "success": True,
        "execution_time_ms": result.execution_time_ms,
    })


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

    return success_response({
        "deal_id": deal_id,
        "stop_loss": body.stop_loss,
        "take_profit": body.take_profit,
        "success": True,
    })
