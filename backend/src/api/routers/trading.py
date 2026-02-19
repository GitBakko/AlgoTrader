"""
Trading API router.
Controls the trading loop: start, stop, status, positions, signals.
"""

import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.dependencies import get_journal_note_repo, get_position_repo
from src.api.schemas import UpdateTradeNoteRequest, error_response, success_response

# Timeout for broker-dependent async calls (seconds)
_BROKER_TIMEOUT = 8.0

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _get_loop(request: Request):
    """Get trading loop from app state."""
    return getattr(request.app.state, "paper_loop", None)


@router.post("/start")
@limiter.limit("5/minute")  # Max 5 start commands per minute
async def start_trading(request: Request):
    """Start the trading loop (idempotent: returns success if already running)."""
    # Check if shutting down
    if getattr(request.app.state, "is_shutting_down", False):
        return error_response(
            "Service is shutting down, not accepting new commands", 503
        )

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
@limiter.limit("5/minute")  # Max 5 stop commands per minute
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


@router.get("/performance")
async def trading_performance(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    epic: str | None = Query(default=None),
    position_repo=Depends(get_position_repo),
):
    """Get trading performance statistics from closed positions."""
    if position_repo is not None:
        try:
            date_from = datetime.now(timezone.utc) - timedelta(days=days)
            stats = await position_repo.get_performance_stats(
                date_from=date_from, epic=epic,
            )
            stats["source"] = "database"
            return success_response(stats)
        except Exception as e:
            logger.debug(f"DB performance stats failed: {e}")

    # Fallback: compute from in-memory trade history
    loop = _get_loop(request)
    if loop is None:
        return success_response({"trade_count": 0, "source": "none"})

    history = list(loop._trade_history)
    pnls = [h.get("pnl", 0) for h in history if "pnl" in h]
    wins = [v for v in pnls if v > 0]
    losses = [v for v in pnls if v <= 0]

    return success_response({
        "trade_count": len(pnls),
        "win_count": len(wins),
        "loss_count": len(losses),
        "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0,
        "total_pnl": round(sum(pnls), 2),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "profit_factor": 0,
        "max_consecutive_wins": 0,
        "max_consecutive_losses": 0,
        "best_trade": round(max(pnls), 2) if pnls else 0,
        "worst_trade": round(min(pnls), 2) if pnls else 0,
        "pnl_by_epic": {},
        "equity_curve": [],
        "source": "in_memory",
    })


@router.post("/emergency-stop")
@limiter.limit("5/minute")
async def emergency_stop(request: Request):
    """
    Emergency stop: halt the trading loop and close ALL open positions.

    This is a destructive operation — it stops the loop immediately and
    attempts to close every position via the broker (or paper tracker).
    """
    loop = _get_loop(request)
    if loop is None:
        return error_response("Trading loop not initialized", 503)

    result: dict = {"loop_stopped": False, "positions_closed": [], "errors": []}

    # 1. Stop the loop
    if loop.is_running:
        loop.stop()
        result["loop_stopped"] = True
        logger.warning("[EMERGENCY STOP] Trading loop stopped")
    else:
        result["loop_stopped"] = True  # already stopped
        logger.info("[EMERGENCY STOP] Trading loop was already stopped")

    # 2. Fetch open positions
    try:
        positions = await asyncio.wait_for(
            loop.get_positions_async(), timeout=_BROKER_TIMEOUT
        )
    except (asyncio.TimeoutError, Exception) as e:
        logger.warning(f"[EMERGENCY STOP] Async positions failed ({e}), trying sync")
        positions = loop.get_paper_positions()

    # 3. Close each position
    for pos in positions:
        deal_id = pos.get("deal_id") or pos.get("dealId")
        if not deal_id:
            continue
        try:
            close_result = await asyncio.wait_for(
                loop.execution_engine.close_position(deal_id, reason="EMERGENCY_STOP"),
                timeout=_BROKER_TIMEOUT,
            )
            if close_result.success:
                result["positions_closed"].append(deal_id)
            else:
                result["errors"].append(
                    f"{deal_id}: {close_result.error or 'close failed'}"
                )
        except Exception as e:
            result["errors"].append(f"{deal_id}: {e}")

    closed = len(result["positions_closed"])
    errors = len(result["errors"])
    logger.warning(
        f"[EMERGENCY STOP] Complete: {closed} closed, {errors} errors"
    )

    # 4. Fire alert (non-critical)
    try:
        from src.monitoring.alerting.alert_manager import get_alert_manager
        from src.utils.config import get_settings
        if getattr(get_settings(), "alerts_enabled", False):
            am = get_alert_manager()
            await am.alert_circuit_breaker(
                epic="ALL",
                reason=f"EMERGENCY STOP: {closed} positions closed, {errors} errors",
                consecutive_losses=0,
            )
    except Exception:
        pass

    return success_response({
        "message": f"Emergency stop eseguito: {closed} posizioni chiuse"
                   + (f", {errors} errori" if errors else ""),
        **result,
    })


# ── Signal Notes (Trade Journal annotations) ──


@router.get("/signals/notes")
async def list_signal_notes(
    note_repo=Depends(get_journal_note_repo),
):
    """Get all trade journal notes (keyed by 'epic|timestamp')."""
    if note_repo is None:
        return success_response({})

    try:
        notes = await note_repo.get_all_notes()
        return success_response(notes)
    except Exception as e:
        logger.warning(f"Failed to load signal notes: {e}")
        return success_response({})


@router.put("/signals/notes")
async def upsert_signal_note(
    body: UpdateTradeNoteRequest,
    note_repo=Depends(get_journal_note_repo),
):
    """Create or update a note for a trade journal signal entry."""
    if note_repo is None:
        return error_response("Database not available", 503)

    # Empty notes = delete
    if not body.notes.strip():
        await note_repo.delete_note(body.epic, body.signal_timestamp)
        return success_response({"deleted": True})

    note = await note_repo.upsert_note(
        epic=body.epic,
        signal_timestamp=body.signal_timestamp,
        notes=body.notes.strip(),
    )
    return success_response({
        "epic": note.epic,
        "signal_timestamp": note.signal_timestamp,
        "notes": note.notes,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
    })
