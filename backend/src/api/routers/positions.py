"""
Positions API router.
Manages open positions: list, close, modify stop-loss/take-profit.
"""

from fastapi import APIRouter, Depends, Path

from src.api.dependencies import get_execution_engine
from src.api.schemas import (
    ModifyStopsRequest,
    PositionResponse,
    error_response,
    success_response,
)
from src.execution.execution_engine import ExecutionEngine

router = APIRouter()


@router.get("/")
async def list_positions(
    epic: str | None = None,
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """List all open positions, optionally filtered by epic."""
    positions = await engine.get_open_positions(epic)

    result = [
        PositionResponse(
            deal_id=p.get("deal_id", ""),
            epic=p.get("epic", ""),
            direction=p.get("direction", ""),
            size=p.get("size", 0.0),
            entry_price=p.get("level", 0.0),
            stop_loss=p.get("stop_level"),
            take_profit=p.get("profit_level"),
            opened_at=p.get("opened_at"),
        ).model_dump()
        for p in positions
    ]

    return success_response(result)


@router.get("/{deal_id}")
async def get_position(
    deal_id: str = Path(...),
    engine: ExecutionEngine = Depends(get_execution_engine),
):
    """Get a single position by deal ID."""
    positions = await engine.get_open_positions()
    position = next((p for p in positions if p.get("deal_id") == deal_id), None)

    if position is None:
        return error_response(f"Position {deal_id} not found", 404)

    result = PositionResponse(
        deal_id=position.get("deal_id", ""),
        epic=position.get("epic", ""),
        direction=position.get("direction", ""),
        size=position.get("size", 0.0),
        entry_price=position.get("level", 0.0),
        stop_loss=position.get("stop_level"),
        take_profit=position.get("profit_level"),
        opened_at=position.get("opened_at"),
    )

    return success_response(result.model_dump())


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
