"""
Trading API router.
Controls the trading loop: start, stop, status, positions, signals.
"""

import asyncio

from fastapi import APIRouter, Request
from loguru import logger

from src.api.schemas import error_response, success_response

# Timeout for broker-dependent async calls (seconds)
_BROKER_TIMEOUT = 8.0

router = APIRouter()


def _get_loop(request: Request):
    """Get trading loop from app state."""
    return getattr(request.app.state, "paper_loop", None)


@router.post("/start")
async def start_trading(request: Request):
    """Start the trading loop (idempotent: returns success if already running)."""
    loop = _get_loop(request)
    if loop is None:
        return error_response("Trading loop not initialized", 503)

    if not loop.prediction_service.has_models:
        return error_response(
            "No ML models loaded. Train models first with scripts/train_models.py", 503
        )

    mode = loop.execution_engine.mode.value
    if loop.is_running:
        return success_response({
            "message": f"Trading già attivo in modalità {mode}",
            **loop.get_status(),
        })

    loop.start()
    return success_response({
        "message": f"Trading avviato in modalità {mode}",
        **loop.get_status(),
    })


@router.post("/stop")
async def stop_trading(request: Request):
    """Stop the trading loop (idempotent: returns success if already stopped)."""
    loop = _get_loop(request)
    if loop is None:
        return error_response("Trading loop not initialized", 503)

    if not loop.is_running:
        return success_response({
            "message": "Trading già fermo",
            **loop.get_status(),
        })

    loop.stop()
    return success_response({"message": "Trading fermato", **loop.get_status()})


@router.get("/status")
async def trading_status(request: Request):
    """Get current status of the trading loop."""
    loop = _get_loop(request)
    if loop is None:
        return success_response({
            "running": False,
            "execution_mode": "PAPER",
            "message": "Trading loop not initialized",
        })

    try:
        status = await asyncio.wait_for(loop.get_status_async(), timeout=_BROKER_TIMEOUT)
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Async status fetch failed ({e}), using sync fallback")
        status = loop.get_status()
    return success_response(status)


@router.get("/positions")
async def trading_positions(request: Request):
    """Get open positions (paper in-memory or broker positions)."""
    loop = _get_loop(request)
    if loop is None:
        return success_response([])

    try:
        positions = await asyncio.wait_for(loop.get_positions_async(), timeout=_BROKER_TIMEOUT)
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"Async positions fetch failed ({e}), using sync fallback")
        positions = loop.get_paper_positions()
    return success_response(positions)


@router.get("/signals")
async def trading_signals(request: Request):
    """Get trading signal history (latest 200)."""
    loop = _get_loop(request)
    if loop is None:
        return success_response([])

    return success_response(loop.get_signal_history())
