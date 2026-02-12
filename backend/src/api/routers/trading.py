"""
Trading API router.
Controls the paper trading loop: start, stop, status.
"""

from fastapi import APIRouter, Request

from src.api.schemas import error_response, success_response

router = APIRouter()


def _get_paper_loop(request: Request):
    """Get paper trading loop from app state."""
    return getattr(request.app.state, "paper_loop", None)


@router.post("/start")
async def start_paper_trading(request: Request):
    """Start the paper trading loop."""
    loop = _get_paper_loop(request)
    if loop is None:
        return error_response("Paper trading loop not initialized", 503)

    if loop.is_running:
        return error_response("Paper trading loop is already running", 409)

    if not loop.prediction_service.has_models:
        return error_response(
            "No ML models loaded. Train models first with scripts/train_models.py", 503
        )

    loop.start()
    return success_response({"message": "Paper trading started", **loop.get_status()})


@router.post("/stop")
async def stop_paper_trading(request: Request):
    """Stop the paper trading loop."""
    loop = _get_paper_loop(request)
    if loop is None:
        return error_response("Paper trading loop not initialized", 503)

    if not loop.is_running:
        return error_response("Paper trading loop is not running", 409)

    loop.stop()
    return success_response({"message": "Paper trading stopped", **loop.get_status()})


@router.get("/status")
async def paper_trading_status(request: Request):
    """Get current status of the paper trading loop."""
    loop = _get_paper_loop(request)
    if loop is None:
        return success_response({
            "running": False,
            "message": "Paper trading loop not initialized",
        })

    return success_response(loop.get_status())


@router.get("/positions")
async def paper_trading_positions(request: Request):
    """Get paper trading open positions from in-memory state."""
    loop = _get_paper_loop(request)
    if loop is None:
        return success_response([])

    return success_response(loop.get_paper_positions())


@router.get("/signals")
async def paper_trading_signals(request: Request):
    """Get paper trading signal history (latest 200)."""
    loop = _get_paper_loop(request)
    if loop is None:
        return success_response([])

    return success_response(loop.get_signal_history())
