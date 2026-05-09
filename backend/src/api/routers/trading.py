"""
Trading API router.
Controls the trading loop: start, stop, status, positions, signals.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from loguru import logger
from slowapi import Limiter
from slowapi.util import get_remote_address

from src.api.dependencies import get_db_session, get_journal_note_repo, get_position_repo
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
        return error_response("Service is shutting down, not accepting new commands", 503)

    loop = _get_loop(request)
    if loop is None:
        return error_response("Trading loop not initialized", 503)

    if not loop.prediction_service.has_models:
        return error_response(
            "No ML models loaded. Train models first with scripts/train_models.py", 503
        )

    mode = loop.execution_engine.mode.value
    if loop.is_running:
        return success_response(
            {
                "message": f"Trading già attivo in modalità {mode}",
                **loop.get_status(),
            }
        )

    loop.start()
    return success_response(
        {
            "message": f"Trading avviato in modalità {mode}",
            **loop.get_status(),
        }
    )


@router.post("/stop")
@limiter.limit("5/minute")  # Max 5 stop commands per minute
async def stop_trading(request: Request):
    """Stop the trading loop (idempotent: returns success if already stopped)."""
    loop = _get_loop(request)
    if loop is None:
        return error_response("Trading loop not initialized", 503)

    if not loop.is_running:
        return success_response(
            {
                "message": "Trading già fermo",
                **loop.get_status(),
            }
        )

    loop.stop()
    return success_response({"message": "Trading fermato", **loop.get_status()})


@router.get("/status")
async def trading_status(request: Request):
    """Get current status of the trading loop."""
    loop = _get_loop(request)
    if loop is None:
        return success_response(
            {
                "running": False,
                "execution_mode": "PAPER",
                "message": "Trading loop not initialized",
            }
        )

    try:
        status = await asyncio.wait_for(loop.get_status_async(), timeout=_BROKER_TIMEOUT)
    except (TimeoutError, Exception) as e:
        logger.warning(f"Async status fetch failed ({e}), using sync fallback")
        status = loop.get_status()

    # Inject WS price status
    from src.api.websocket import ws_price_status

    status["ws_price_status"] = dict(ws_price_status)

    return success_response(status)


@router.get("/positions")
async def trading_positions(request: Request):
    """Get open positions (paper in-memory or broker positions)."""
    loop = _get_loop(request)
    if loop is None:
        return success_response([])

    try:
        positions = await asyncio.wait_for(loop.get_positions_async(), timeout=_BROKER_TIMEOUT)
    except (TimeoutError, Exception) as e:
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


@router.get("/events")
async def trading_events(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    hours: int = Query(default=24, ge=1, le=168),
    session=Depends(get_db_session),
):
    """Aggregated activity feed for the cockpit live-feed-timeline (HANDOFF §3.8).

    Merges three sources captured by the trading loop and the alert manager:
        * `signals` table  → signal-emit (status=EXECUTED) and signal-reject (status=REJECTED)
        * `positions` table → position-open (opened_at) and position-close (closed_at)
        * `notifications` table → alerts (errors, training events, circuit breakers, ...)

    Returns a flat list of normalized events sorted by timestamp DESC, capped at ``limit``.
    Each item: ``{ id, ts, kind, epic?, title, meta?, severity? }``.

    The cockpit also reads ``/trading/status`` on a 10s cadence to surface
    iteration ticks; iteration events are deliberately not produced here.
    """
    if session is None:
        return success_response([])

    from sqlalchemy import text as sql_text

    cutoff = (datetime.now(UTC) - timedelta(hours=hours)).replace(tzinfo=None)
    events: list[dict] = []

    # 1. Signals — emit + reject (include strategy + reason from JSONB features)
    try:
        result = await session.execute(
            sql_text(
                """
                SELECT id, epic, direction, confidence, status, generated_at,
                       predicted_price, stop_loss_price, take_profit_price,
                       features
                  FROM signals
                 WHERE generated_at > :cutoff
                   AND status IN ('EXECUTED', 'REJECTED', 'PENDING')
                 ORDER BY generated_at DESC
                 LIMIT :limit
                """
            ),
            {"cutoff": cutoff, "limit": limit * 2},
        )
        for row in result.mappings():
            status = (row["status"] or "").upper()
            features = row["features"] or {}
            strategy = features.get("strategy_name") or features.get("strategy") or "—"
            direction = (row["direction"] or "").upper()
            confidence = (
                round(float(row["confidence"]) * 100) if row["confidence"] is not None else None
            )
            price = float(row["predicted_price"]) if row["predicted_price"] is not None else None
            kind = (
                "signal-emit"
                if status == "EXECUTED"
                else "signal-reject"
                if status == "REJECTED"
                else "signal-pending"
            )
            detail = (
                features.get("rejection_reason")
                if status == "REJECTED"
                else features.get("regime") or direction
            )
            events.append(
                {
                    "id": f"signal-{row['id']}",
                    "ts": row["generated_at"].isoformat() if row["generated_at"] else None,
                    "kind": kind,
                    "epic": row["epic"],
                    "direction": direction or None,
                    "confidence": confidence,
                    "price": price,
                    "strategy": strategy,
                    "detail": detail,
                    "title": f"{direction} {row['epic']}",
                    "meta": (
                        f"conf {confidence}%" if confidence is not None else strategy
                    ),
                    "severity": "info" if status == "EXECUTED" else "warning",
                }
            )
    except Exception as e:
        logger.debug(f"events: signals query failed: {e}")

    # 2. Positions — open + close. LEFT JOIN signals to recover strategy
    # and confidence so the feed row matches the mock spec without
    # firing a second roundtrip per row.
    try:
        result = await session.execute(
            sql_text(
                """
                SELECT p.id, p.deal_id, p.epic, p.direction, p.opened_at, p.closed_at,
                       p.entry_price, p.close_reason, p.profit_loss,
                       s.confidence  AS sig_confidence,
                       s.features    AS sig_features
                  FROM positions p
                  LEFT JOIN signals s ON s.id = p.signal_id
                 WHERE p.opened_at > :cutoff OR (p.closed_at IS NOT NULL AND p.closed_at > :cutoff)
                 ORDER BY GREATEST(p.opened_at, COALESCE(p.closed_at, p.opened_at)) DESC
                 LIMIT :limit
                """
            ),
            {"cutoff": cutoff, "limit": limit * 2},
        )
        for row in result.mappings():
            opened_at = row["opened_at"]
            closed_at = row["closed_at"]
            features = row["sig_features"] or {}
            strategy = features.get("strategy_name") or features.get("strategy") or "—"
            direction = (row["direction"] or "").upper()
            confidence = (
                round(float(row["sig_confidence"]) * 100)
                if row["sig_confidence"] is not None
                else None
            )
            price = float(row["entry_price"]) if row["entry_price"] is not None else None

            if opened_at and opened_at > cutoff:
                events.append(
                    {
                        "id": f"pos-open-{row['id']}",
                        "ts": opened_at.isoformat(),
                        "kind": "position-open",
                        "epic": row["epic"],
                        "direction": direction or None,
                        "confidence": confidence,
                        "price": price,
                        "strategy": strategy,
                        "detail": "aperta",
                        "title": f"{direction} {row['epic']} aperta",
                        "meta": row["deal_id"],
                        "deal_id": row["deal_id"],
                        "severity": "info",
                    }
                )
            if closed_at and closed_at > cutoff:
                pnl = row["profit_loss"]
                pnl_str = f"{float(pnl):+.2f}" if pnl is not None else "—"
                kind_severity = (
                    "info" if pnl is not None and float(pnl) >= 0 else "warning"
                )
                close_reason = row["close_reason"] or "manual"
                events.append(
                    {
                        "id": f"pos-close-{row['id']}",
                        "ts": closed_at.isoformat(),
                        "kind": "position-close",
                        "epic": row["epic"],
                        "direction": direction or None,
                        "confidence": confidence,
                        "price": price,
                        "strategy": strategy,
                        "detail": f"{close_reason} · {pnl_str}",
                        "title": f"{direction} {row['epic']} chiusa · {pnl_str}",
                        # `meta` keeps the close_reason for the UI badge.
                        # `deal_id` is the authoritative deal identifier for
                        # routing the click to the audit drawer — never
                        # overload `meta` for that role.
                        "meta": close_reason,
                        "deal_id": row["deal_id"],
                        "severity": kind_severity,
                    }
                )
    except Exception as e:
        logger.debug(f"events: positions query failed: {e}")

    # 3. Notifications — errors, model lifecycle, circuit breakers, etc.
    try:
        result = await session.execute(
            sql_text(
                """
                SELECT id, alert_type, severity, title, message, epic, created_at
                  FROM notifications
                 WHERE created_at > :cutoff
                 ORDER BY created_at DESC
                 LIMIT :limit
                """
            ),
            {"cutoff": cutoff, "limit": limit * 2},
        )
        # Skip TRADE_OPENED / TRADE_CLOSED / SIGNAL_GENERATED — already covered by
        # the signals + positions queries above to avoid duplicate rows.
        skip_alert_types = {"TRADE_OPENED", "TRADE_CLOSED", "SIGNAL_GENERATED"}
        for row in result.mappings():
            alert_type = row["alert_type"] or ""
            if alert_type in skip_alert_types:
                continue
            kind = (
                "model-load"
                if alert_type.startswith("TRAINING_")
                else "error"
                if (row["severity"] or "").upper() in ("ERROR", "CRITICAL")
                else "alert"
            )
            events.append(
                {
                    "id": f"notif-{row['id']}",
                    "ts": row["created_at"].isoformat() if row["created_at"] else None,
                    "kind": kind,
                    "epic": row["epic"],
                    "direction": None,
                    "confidence": None,
                    "price": None,
                    "strategy": None,
                    "detail": row["message"][:120] if row["message"] else None,
                    "title": row["title"] or alert_type,
                    "meta": row["message"][:120] if row["message"] else None,
                    "severity": (row["severity"] or "info").lower(),
                }
            )
    except Exception as e:
        logger.debug(f"events: notifications query failed: {e}")

    # Sort merged stream by ts DESC, drop missing timestamps, cap at limit.
    events = [e for e in events if e["ts"]]
    events.sort(key=lambda e: e["ts"], reverse=True)
    return success_response(events[:limit])


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
            date_from = datetime.now(UTC) - timedelta(days=days)
            # Anchor max-drawdown / Calmar to the broker's live equity so
            # the figures stay in lockstep with /dashboard/equity-curve.
            from src.api.dependencies import get_risk_manager  # local import to avoid cycle

            risk_mgr = get_risk_manager(request)
            live_equity = risk_mgr.drawdown_monitor.state.current_equity if risk_mgr else None
            terminal = float(live_equity) if live_equity and live_equity > 0 else None
            stats = await position_repo.get_performance_stats(
                date_from=date_from,
                epic=epic,
                terminal_equity=terminal,
            )
            # Dashboard v2: enrich with "trades opened today" count.
            try:
                stats["daily_trade_count"] = await position_repo.get_opened_today_count()
            except Exception as e:
                logger.debug(f"daily_trade_count query failed: {e}")
                stats["daily_trade_count"] = 0
            # Dashboard v2 (D4): duration-medians aggregate for the scatter card.
            try:
                stats["duration_medians"] = await position_repo.get_duration_medians(
                    date_from=date_from,
                    epic=epic,
                )
            except Exception as e:
                logger.debug(f"duration_medians query failed: {e}")
                stats["duration_medians"] = None
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

    return success_response(
        {
            "trade_count": len(pnls),
            "win_count": len(wins),
            "loss_count": len(losses),
            "win_rate": round(len(wins) / len(pnls), 4) if pnls else 0,
            "tp_hit_rate": 0.0,
            "tp_count": 0,
            "daily_trade_count": 0,
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
        }
    )


@router.get("/performance/breakdown")
async def performance_breakdown(
    request: Request,
    tf: str = Query(default="30D"),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    position_repo=Depends(get_position_repo),
):
    """
    Per-day BUY/SELL × TP/SL/Going breakdown for Dashboard v2 Deliverable C.

    Query params:
        tf    — preset timeframe ("1D", "7D", "30D", "90D", "YTD", "ALL", "CUSTOM")
        from  — ISO date (YYYY-MM-DD) — required only when tf=CUSTOM
        to    — ISO date (YYYY-MM-DD) — required only when tf=CUSTOM

    Response:
        {
            "success": true,
            "data": {
                "timeframe": "30D",
                "days": [{ date, buy{tp,sl,going,pnl}, sell{tp,sl,going,pnl} }]
            }
        }
    """
    now = datetime.now(UTC)
    tf_upper = (tf or "").upper()

    # Resolve window.
    if tf_upper == "CUSTOM":
        if not date_from or not date_to:
            return error_response("CUSTOM timeframe requires both `from` and `to`", 400)
        try:
            d_from = datetime.fromisoformat(date_from).replace(tzinfo=UTC)
            d_to = datetime.fromisoformat(date_to).replace(
                hour=23, minute=59, second=59, tzinfo=UTC
            )
        except ValueError:
            return error_response("Invalid date format (expected YYYY-MM-DD)", 400)
    else:
        tf_days = {
            "1D": 1, "7D": 7, "30D": 30, "90D": 90, "ALL": 3650,
        }
        if tf_upper == "YTD":
            d_from = datetime(now.year, 1, 1, tzinfo=UTC)
            d_to = now
        elif tf_upper in tf_days:
            d_from = now - timedelta(days=tf_days[tf_upper])
            d_to = now
        else:
            return error_response(
                f"Unknown timeframe '{tf}' (expected 1D|7D|30D|90D|YTD|ALL|CUSTOM)", 400
            )

    if position_repo is None:
        return success_response({
            "timeframe": tf_upper,
            "days": [],
            "source": "none",
        })

    try:
        days = await position_repo.get_breakdown_by_day(d_from, d_to)
    except Exception as e:
        logger.error(f"breakdown query failed: {e}")
        return error_response(f"breakdown query failed: {e}", 500)

    return success_response({
        "timeframe": tf_upper,
        "from": d_from.strftime("%Y-%m-%d"),
        "to": d_to.strftime("%Y-%m-%d"),
        "days": days,
        "source": "database",
    })


@router.get("/performance/delta")
async def performance_delta(
    request: Request,
    tf: str = Query(default="30D"),
    date_from: str | None = Query(default=None, alias="from"),
    date_to: str | None = Query(default=None, alias="to"),
    position_repo=Depends(get_position_repo),
):
    """
    Win-rate delta vs retro-shifted previous period (Dashboard v2 Phase 4 §A).

    Calls `get_performance_stats()` twice — once for the current window and
    once for the previous window of equal length immediately before it —
    and returns the delta in percentage points.

    Query params: tf (1D|7D|30D|90D|YTD|ALL|CUSTOM), from/to for CUSTOM.

    Response data:
        timeframe, date_from, date_to, prev_from, prev_to,
        win_rate_current, win_rate_previous, delta_pp,
        n_current, n_previous, wins_current, losses_current, source
    """
    now = datetime.now(UTC)
    tf_upper = (tf or "").upper()

    if tf_upper == "CUSTOM":
        if not date_from or not date_to:
            return error_response("CUSTOM timeframe requires both `from` and `to`", 400)
        try:
            d_from = datetime.fromisoformat(date_from).replace(tzinfo=UTC)
            d_to = datetime.fromisoformat(date_to).replace(
                hour=23, minute=59, second=59, tzinfo=UTC
            )
        except ValueError:
            return error_response("Invalid date format (expected YYYY-MM-DD)", 400)
    else:
        tf_days = {"1D": 1, "7D": 7, "30D": 30, "90D": 90, "ALL": 3650}
        if tf_upper == "YTD":
            d_from = datetime(now.year, 1, 1, tzinfo=UTC)
            d_to = now
        elif tf_upper in tf_days:
            d_from = now - timedelta(days=tf_days[tf_upper])
            d_to = now
        else:
            return error_response(
                f"Unknown timeframe '{tf}' (expected 1D|7D|30D|90D|YTD|ALL|CUSTOM)", 400
            )

    window = d_to - d_from
    prev_to = d_from
    prev_from = d_from - window

    empty_payload = {
        "timeframe": tf_upper,
        "date_from": d_from.strftime("%Y-%m-%d"),
        "date_to": d_to.strftime("%Y-%m-%d"),
        "prev_from": prev_from.strftime("%Y-%m-%d"),
        "prev_to": prev_to.strftime("%Y-%m-%d"),
        "win_rate_current": None,
        "win_rate_previous": None,
        "delta_pp": None,
        "n_current": 0,
        "n_previous": 0,
        "wins_current": 0,
        "losses_current": 0,
        "source": "none",
    }

    if position_repo is None:
        return success_response(empty_payload)

    try:
        cur_stats = await position_repo.get_performance_stats(
            date_from=d_from, date_to=d_to
        )
        prev_stats = await position_repo.get_performance_stats(
            date_from=prev_from, date_to=prev_to
        )
    except Exception as e:
        logger.error(f"performance/delta query failed: {e}")
        return error_response(f"performance/delta query failed: {e}", 500)

    n_cur = int(cur_stats.get("trade_count", 0))
    n_prev = int(prev_stats.get("trade_count", 0))

    wr_cur = cur_stats.get("win_rate") if n_cur > 0 else None
    wr_prev = prev_stats.get("win_rate") if n_prev > 0 else None
    delta_pp = (
        round((wr_cur - wr_prev) * 100, 2)
        if wr_cur is not None and wr_prev is not None
        else None
    )

    return success_response({
        "timeframe": tf_upper,
        "date_from": d_from.strftime("%Y-%m-%d"),
        "date_to": d_to.strftime("%Y-%m-%d"),
        "prev_from": prev_from.strftime("%Y-%m-%d"),
        "prev_to": prev_to.strftime("%Y-%m-%d"),
        "win_rate_current": round(wr_cur, 4) if wr_cur is not None else None,
        "win_rate_previous": round(wr_prev, 4) if wr_prev is not None else None,
        "delta_pp": delta_pp,
        "n_current": n_cur,
        "n_previous": n_prev,
        "wins_current": int(cur_stats.get("win_count", 0)),
        "losses_current": int(cur_stats.get("loss_count", 0)),
        "source": "database",
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
        positions = await asyncio.wait_for(loop.get_positions_async(), timeout=_BROKER_TIMEOUT)
    except (TimeoutError, Exception) as e:
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
                result["errors"].append(f"{deal_id}: {close_result.error or 'close failed'}")
        except Exception as e:
            result["errors"].append(f"{deal_id}: {e}")

    closed = len(result["positions_closed"])
    errors = len(result["errors"])
    logger.warning(f"[EMERGENCY STOP] Complete: {closed} closed, {errors} errors")

    # 4. Fire CRITICAL alert (M2 fix: Invariant #4 says CRITICAL, and the
    # alert must NOT be gated on `alerts_enabled` — operator visibility
    # of an emergency stop is non-negotiable).
    try:
        from src.monitoring.alerting.alert_manager import get_alert_manager
        from src.monitoring.alerting.schemas import (
            Alert,
            AlertSeverity,
            AlertType,
        )

        am = get_alert_manager()
        alert = Alert(
            alert_type=AlertType.SYSTEM_ERROR,
            severity=AlertSeverity.CRITICAL,
            title="EMERGENCY STOP EXECUTED",
            message=f"{closed} positions closed, {errors} errors",
            details={"positions_closed": closed, "errors": errors},
        )
        await am.send_alert(alert)
    except Exception as alert_err:
        logger.error(f"Emergency stop alert failed: {alert_err}")

    return success_response(
        {
            "message": f"Emergency stop eseguito: {closed} posizioni chiuse"
            + (f", {errors} errori" if errors else ""),
            **result,
        }
    )


@router.post("/reset-circuit-breakers")
@limiter.limit("5/minute")
async def reset_circuit_breakers(request: Request):
    """Manually reset all circuit breakers and per-asset loss counters."""
    loop = _get_loop(request)
    if loop is None:
        return error_response("Trading loop not initialized", 503)

    reset_list = loop.risk_manager.circuit_breakers.reset_all()
    loop._per_asset_losses.clear()

    if reset_list:
        logger.warning(f"[CB RESET] Manual reset: {reset_list}")
    else:
        logger.info("[CB RESET] Manual reset requested (no breakers were active)")

    return success_response(
        {
            "message": f"Circuit breakers resettati: {len(reset_list)} breaker"
            + (f" ({', '.join(reset_list)})" if reset_list else ""),
            "reset_breakers": reset_list,
        }
    )


@router.post("/reset-risk-state")
@limiter.limit("3/minute")
async def reset_risk_state(request: Request):
    """Reset Kelly trade history + equity curve filter for fresh strategy start."""
    loop = _get_loop(request)
    if loop is None:
        return error_response("Trading loop not initialized", 503)

    # Clear Kelly trade history
    old_kelly_size = len(loop._trade_history)
    loop._trade_history.clear()

    # Clear equity curve filter
    old_eq_points = 0
    if hasattr(loop.risk_manager, "equity_curve_filter"):
        ecf = loop.risk_manager.equity_curve_filter
        old_eq_points = len(ecf._equity_points)
        ecf._equity_points.clear()

    # Reset circuit breakers too
    reset_list = loop.risk_manager.circuit_breakers.reset_all()
    loop._per_asset_losses.clear()

    # Clear epic SL cooldown tracker
    old_sl_cooldowns = {k: len(v) for k, v in loop._epic_sl_hits.items() if v}
    loop._epic_sl_hits.clear()

    logger.warning(
        f"[RISK RESET] Manual full reset: "
        f"kelly_history={old_kelly_size}->0, "
        f"equity_points={old_eq_points}->0, "
        f"cb={len(reset_list)}, "
        f"sl_cooldowns={old_sl_cooldowns}"
    )

    return success_response(
        {
            "message": "Risk state resettato completamente",
            "kelly_trades_cleared": old_kelly_size,
            "equity_points_cleared": old_eq_points,
            "circuit_breakers_reset": len(reset_list),
        }
    )


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
    return success_response(
        {
            "epic": note.epic,
            "signal_timestamp": note.signal_timestamp,
            "notes": note.notes,
            "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        }
    )


# ─────────────────────────────────────────────────────────────────────
# P&L history (60s snapshots)
# ─────────────────────────────────────────────────────────────────────

# Read window cap — keep payloads small + protect the DB.
_PNL_HISTORY_MAX_MINUTES = 24 * 60


@router.get("/pnl-history")
async def get_pnl_history(
    minutes: int = Query(180, ge=1, le=_PNL_HISTORY_MAX_MINUTES),
    session=Depends(get_db_session),
):
    """Real Paper Trading P&L history captured every 60s.

    Powers the Paper Trading v2 KPI strip (P&L Open / P&L Today
    sparklines) — replaces the synthetic ramps the cockpit used to draw
    when no history was available.
    """
    if session is None:
        return success_response({"points": [], "source": "no-db"})

    from src.database.repositories.pnl_snapshot_repository import (
        PaperPnlSnapshotRepository,
    )

    repo = PaperPnlSnapshotRepository(session)
    rows = await repo.list_recent(minutes=minutes)
    points = [
        {
            "ts": row.captured_at.isoformat(),
            "pnl_open": float(row.pnl_open),
            "pnl_today": float(row.pnl_today),
            "equity": float(row.equity) if row.equity is not None else None,
            "open_count": int(row.open_count),
        }
        for row in rows
    ]
    return success_response(
        {
            "points": points,
            "minutes": minutes,
            "source": "snapshot",
        }
    )


async def _auto_heal_broker_only_position(
    *, request: Request, deal_id: str, session
):
    """Persist a broker-reported position that is missing from our `positions`
    table. Returns the freshly-created Position row, or None when the broker
    does not have the deal either (genuinely unknown).

    Path of least surprise: the History tab should never lie about the
    broker's reality. When `bcdb` is alive on Capital.com but never made it
    into our DB (state-recovery loaded it from `broker.list_positions` at
    startup but the open path that calls `_persist_position_open` was bypassed),
    the user opening the drawer should see the OPEN event seeded from
    broker truth, plus a `recovered=True` marker so they understand the
    history begins at first observation rather than at original open.

    On any error (broker unreachable, persistence failure) the helper
    returns None and the caller falls through to the "not-found" branch.
    """
    try:
        from datetime import UTC as _UTC
        from datetime import datetime as _dt
        from decimal import Decimal as _Dec

        from src.database.models import Position as _PositionModel
        from src.database.models import Trade as _TradeModel
        from src.database.repositories.position_repository import (
            PositionRepository as _PositionRepository,
        )

        loop = _get_loop(request)
        if loop is None:
            return None
        try:
            broker_positions = await asyncio.wait_for(
                loop.get_positions_async(), timeout=_BROKER_TIMEOUT
            )
        except (TimeoutError, Exception) as e:
            logger.debug(f"[auto-heal] broker fetch failed: {e}")
            return None

        match = next(
            (p for p in broker_positions if p.get("deal_id") == deal_id),
            None,
        )
        if match is None:
            return None

        epic = match.get("epic") or "UNKNOWN"
        direction = match.get("direction") or "BUY"
        size = float(match.get("size") or 0)
        entry = float(match.get("level") or 0)
        stop_level = match.get("stop_level")
        profit_level = match.get("profit_level")
        opened_at_raw = match.get("opened_at")
        try:
            if isinstance(opened_at_raw, str):
                opened_at = _dt.fromisoformat(opened_at_raw)
                if opened_at.tzinfo is not None:
                    opened_at = opened_at.astimezone(_UTC).replace(tzinfo=None)
            elif opened_at_raw is not None and hasattr(opened_at_raw, "tzinfo"):
                opened_at = (
                    opened_at_raw.astimezone(_UTC).replace(tzinfo=None)
                    if opened_at_raw.tzinfo is not None
                    else opened_at_raw
                )
            else:
                opened_at = _dt.now(_UTC).replace(tzinfo=None)
        except (ValueError, TypeError):
            opened_at = _dt.now(_UTC).replace(tzinfo=None)

        repo = _PositionRepository(session)
        pos = _PositionModel(
            deal_id=deal_id,
            deal_reference=match.get("deal_reference"),
            epic=epic,
            direction=direction,
            size=_Dec(str(size)),
            entry_price=_Dec(str(entry)) if entry else _Dec("0"),
            stop_loss=_Dec(str(stop_level)) if stop_level is not None else None,
            take_profit=_Dec(str(profit_level)) if profit_level is not None else None,
            status="OPEN",
            opened_at=opened_at,
        )
        pos = await repo.create(pos)
        # Seed an OPEN trade row so the History tab opens with a real audit
        # entry rather than only the synthesised fallback.
        trade = _TradeModel(
            position_id=pos.id,
            deal_reference=deal_id,
            trade_type="OPEN",
            epic=epic,
            direction=direction,
            size=_Dec(str(size)),
            price=_Dec(str(entry)) if entry else _Dec("0"),
            executed_at=opened_at,
            notes=(
                "Auto-heal: position recovered from broker live snapshot "
                "(was missing from DB — likely state-recovery ghost from "
                "a prior session)."
            ),
        )
        session.add(trade)
        await session.commit()
        logger.warning(
            f"[auto-heal] Persisted broker-only position "
            f"{deal_id} ({epic} {direction} size={size} entry={entry}) "
            f"on first /events request — seeded OPEN trade row"
        )
        return pos
    except Exception as e:
        logger.warning(f"[auto-heal] failed for {deal_id}: {e}")
        return None


@router.get("/positions/{deal_id}/events")
async def get_position_events(
    deal_id: str,
    request: Request,
    session=Depends(get_db_session),
):
    """Per-position event timeline (open, modify, close).

    Powers the position-detail-drawer's History tab. Returns rows sourced
    from the immutable `trades` audit table joined with the parent
    `positions` row, so a position with no Trade rows still surfaces its
    OPEN/CLOSE events synthesised from the Position itself.

    Auto-heal: when the deal_id is missing from `positions` but the broker
    still reports it (state-recovery ghost from a previous session), the
    endpoint persists a fresh `positions` + OPEN `trades` row inline using
    the broker's live snapshot. This guarantees the History tab is never
    empty for a position the broker considers open, and seeds the audit
    trail forward — subsequent trailing transitions will append to the
    same lineage.
    """
    if session is None:
        return success_response(
            {"deal_id": deal_id, "events": [], "position": None, "source": "no-db"}
        )

    from src.database.repositories.position_repository import PositionRepository
    from src.database.repositories.trade_repository import TradeRepository

    pos_repo = PositionRepository(session)
    position = await pos_repo.get_by_deal_id(deal_id)
    if position is None:
        # Try auto-heal: if the broker still has this position, persist it.
        position = await _auto_heal_broker_only_position(
            request=request, deal_id=deal_id, session=session
        )
        if position is None:
            logger.warning(
                f"[events] position not found in DB for deal_id={deal_id} "
                f"and not present at broker — returning empty timeline"
            )
            return success_response(
                {
                    "deal_id": deal_id,
                    "events": [],
                    "position": None,
                    "source": "not-found",
                }
            )

    trade_repo = TradeRepository(session)
    trades = await trade_repo.get_by_position(position.id) if position.id else []

    events: list[dict] = []
    seen_open = False
    seen_close = False

    for t in trades:
        ev_type = (t.trade_type or "").upper()
        if ev_type == "OPEN":
            seen_open = True
        elif ev_type == "CLOSE":
            seen_close = True
        events.append(
            {
                "ts": t.executed_at.isoformat() if t.executed_at else None,
                "type": ev_type or "TRADE",
                "deal_reference": t.deal_reference,
                "size": float(t.size) if t.size is not None else None,
                "price": float(t.price) if t.price is not None else None,
                "profit_loss": float(t.profit_loss) if t.profit_loss is not None else None,
                "commission": float(t.commission) if t.commission is not None else None,
                "notes": t.notes,
            }
        )

    # Synthesise OPEN/CLOSE from the Position row when the trades audit
    # table missed them (older positions, mid-failure persistence).
    if not seen_open:
        events.append(
            {
                "ts": position.opened_at.isoformat() if position.opened_at else None,
                "type": "OPEN",
                "deal_reference": position.deal_reference,
                "size": float(position.size) if position.size is not None else None,
                "price": float(position.entry_price) if position.entry_price is not None else None,
                "profit_loss": None,
                "commission": None,
                "synthesised": True,
            }
        )
    if not seen_close and position.status == "CLOSED":
        events.append(
            {
                "ts": position.closed_at.isoformat() if position.closed_at else None,
                "type": "CLOSE",
                "deal_reference": None,
                "size": float(position.size) if position.size is not None else None,
                "price": None,
                "profit_loss": (
                    float(position.profit_loss) if position.profit_loss is not None else None
                ),
                "commission": None,
                "close_reason": position.close_reason,
                "synthesised": True,
            }
        )

    # Sort chronologically; rows with no timestamp sink to the bottom so
    # the UI never has to handle nulls in the middle of the timeline.
    events.sort(key=lambda e: (e["ts"] is None, e["ts"] or ""))

    return success_response(
        {
            "deal_id": deal_id,
            "events": events,
            "position": {
                "id": position.id,
                "epic": position.epic,
                "direction": position.direction,
                "status": position.status,
                "opened_at": position.opened_at.isoformat() if position.opened_at else None,
                "closed_at": position.closed_at.isoformat() if position.closed_at else None,
                "close_reason": position.close_reason,
                "entry_price": (
                    float(position.entry_price) if position.entry_price is not None else None
                ),
                "stop_loss": (
                    float(position.stop_loss) if position.stop_loss is not None else None
                ),
                "take_profit": (
                    float(position.take_profit) if position.take_profit is not None else None
                ),
                "profit_loss": (
                    float(position.profit_loss) if position.profit_loss is not None else None
                ),
                "size": float(position.size) if position.size is not None else None,
            },
            "source": "trades+position",
        }
    )


@router.get("/positions/{deal_id}/pnl-history")
async def get_position_pnl_history(
    deal_id: str,
    minutes: int = Query(360, ge=1, le=_PNL_HISTORY_MAX_MINUTES),
    session=Depends(get_db_session),
):
    """Per-position P&L history captured every 60s for the lifetime
    of the open position. Powers the position-card price chart.
    """
    if session is None:
        return success_response({"deal_id": deal_id, "points": [], "source": "no-db"})

    from src.database.repositories.pnl_snapshot_repository import (
        PositionPnlSnapshotRepository,
    )

    repo = PositionPnlSnapshotRepository(session)
    rows = await repo.list_for_deal(deal_id=deal_id, minutes=minutes)
    points = [
        {
            "ts": row.captured_at.isoformat(),
            "pnl": float(row.pnl),
            "pnl_pct": float(row.pnl_pct),
            "price": float(row.current_price),
        }
        for row in rows
    ]
    return success_response(
        {
            "deal_id": deal_id,
            "points": points,
            "minutes": minutes,
            "source": "snapshot",
        }
    )
