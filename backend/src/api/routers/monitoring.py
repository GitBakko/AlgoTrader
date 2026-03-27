"""
Monitoring API Router - Endpoints for trading logs and statistics.

Provides access to structured logging data for analysis and debugging.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from loguru import logger

from src.api.schemas import success_response, error_response
from src.monitoring.log_analyzer import ExecutionStats, LogAnalyzer, RiskStats, SignalStats

router = APIRouter(prefix="/monitoring", tags=["monitoring"])

# Singleton LogAnalyzer instance
_log_analyzer: LogAnalyzer | None = None


def get_log_analyzer() -> LogAnalyzer:
    """Get global LogAnalyzer instance."""
    global _log_analyzer
    if _log_analyzer is None:
        _log_analyzer = LogAnalyzer()
    return _log_analyzer


# ═══════════════════════════════════════════════════════════════════════════
# Signal Logs Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/logs/signals")
async def get_signal_logs(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
):
    """
    Get signal generation statistics.

    Returns aggregated statistics about trading signals:
    - Total signals generated
    - Execution rate (signals that resulted in trades)
    - Breakdown by epic, strategy, direction

    Args:
        days: Number of days to analyze (default: 30, max: 365)

    Returns:
        Signal statistics
    """
    analyzer = get_log_analyzer()
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    try:
        stats: SignalStats = await analyzer.get_signal_stats(start_date, end_date)

        return success_response(
            {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days,
                },
                "summary": {
                    "total_signals": stats.total_signals,
                    "executed": stats.executed,
                    "rejected": stats.rejected,
                    "hold": stats.hold,
                    "execution_rate_pct": stats.execution_rate_pct,
                },
                "by_epic": stats.by_epic,
                "by_strategy": stats.by_strategy,
                "by_direction": stats.by_direction,
            }
        )

    except Exception as e:
        logger.error(f"Failed to get signal logs: {e}")
        return error_response(str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Execution Logs Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/logs/executions")
async def get_execution_logs(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
):
    """
    Get trade execution statistics.

    Returns detailed statistics about executed trades:
    - Total trades, open positions, closed trades
    - P&L metrics (total, average, by epic)
    - Win rate and profit factor
    - Average trade duration

    Args:
        days: Number of days to analyze (default: 30, max: 365)

    Returns:
        Execution statistics
    """
    analyzer = get_log_analyzer()
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    try:
        stats: ExecutionStats = await analyzer.get_execution_stats(start_date, end_date)

        return success_response(
            {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days,
                },
                "summary": {
                    "total_trades": stats.total_trades,
                    "open_positions": stats.open_positions,
                    "closed_trades": stats.closed_trades,
                    "total_pnl": stats.total_pnl,
                    "avg_pnl": stats.avg_pnl,
                    "wins": stats.wins,
                    "losses": stats.losses,
                    "win_rate_pct": stats.win_rate_pct,
                    "avg_win": stats.avg_win,
                    "avg_loss": stats.avg_loss,
                    "profit_factor": stats.profit_factor,
                    "avg_duration_hours": stats.avg_duration_hours,
                },
                "by_epic": stats.by_epic,
            }
        )

    except Exception as e:
        logger.error(f"Failed to get execution logs: {e}")
        return error_response(str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Risk Event Logs Endpoints
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/logs/risk-events")
async def get_risk_event_logs(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
):
    """
    Get risk management event statistics.

    Returns aggregated statistics about risk events:
    - Circuit breaker triggers
    - Position limit hits
    - Drawdown statistics
    - Event breakdown by type

    Args:
        days: Number of days to analyze (default: 30, max: 365)

    Returns:
        Risk event statistics
    """
    analyzer = get_log_analyzer()
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    try:
        stats: RiskStats = await analyzer.get_risk_stats(start_date, end_date)

        return success_response(
            {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days,
                },
                "summary": {
                    "total_events": stats.total_events,
                    "circuit_breaker_triggers": stats.circuit_breaker_triggers,
                    "position_limit_hits": stats.position_limit_hits,
                    "drawdown_limit_hits": stats.drawdown_limit_hits,
                    "max_drawdown_pct": stats.max_drawdown_pct,
                    "avg_daily_pnl": stats.avg_daily_pnl,
                    "last_event": (
                        stats.last_event_timestamp.isoformat()
                        if stats.last_event_timestamp
                        else None
                    ),
                },
                "by_event_type": stats.by_event_type,
            }
        )

    except Exception as e:
        logger.error(f"Failed to get risk event logs: {e}")
        return error_response(str(e))


# ═══════════════════════════════════════════════════════════════════════════
# Combined Performance Overview
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/stats/performance")
async def get_performance_overview(
    days: int = Query(default=7, ge=1, le=365, description="Number of days to analyze"),
):
    """
    Get combined performance overview.

    Provides a comprehensive snapshot of trading performance including:
    - Signal generation metrics
    - Execution performance (P&L, win rate)
    - Risk management status
    - System health indicators

    Args:
        days: Number of days to analyze (default: 7, max: 365)

    Returns:
        Combined performance statistics
    """
    analyzer = get_log_analyzer()
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)

    try:
        # Fetch all stats in parallel (not truly parallel due to Python GIL, but structured)
        signal_stats = await analyzer.get_signal_stats(start_date, end_date)
        exec_stats = await analyzer.get_execution_stats(start_date, end_date)
        risk_stats = await analyzer.get_risk_stats(start_date, end_date)

        # Calculate health score (0-100)
        health_score = _calculate_health_score(signal_stats, exec_stats, risk_stats)

        return success_response(
            {
                "period": {
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "days": days,
                },
                "health_score": health_score,
                "signals": {
                    "total": signal_stats.total_signals,
                    "execution_rate_pct": signal_stats.execution_rate_pct,
                    "top_strategy": (
                        max(signal_stats.by_strategy.items(), key=lambda x: x[1])[0]
                        if signal_stats.by_strategy
                        else None
                    ),
                },
                "execution": {
                    "total_trades": exec_stats.total_trades,
                    "open_positions": exec_stats.open_positions,
                    "total_pnl": exec_stats.total_pnl,
                    "win_rate_pct": exec_stats.win_rate_pct,
                    "profit_factor": exec_stats.profit_factor,
                },
                "risk": {
                    "circuit_breaker_triggers": risk_stats.circuit_breaker_triggers,
                    "max_drawdown_pct": risk_stats.max_drawdown_pct,
                    "avg_daily_pnl": risk_stats.avg_daily_pnl,
                },
            }
        )

    except Exception as e:
        logger.error(f"Failed to get performance overview: {e}")
        return error_response(str(e))


def _calculate_health_score(
    signal_stats: SignalStats,
    exec_stats: ExecutionStats,
    risk_stats: RiskStats,
) -> int:
    """
    Calculate system health score (0-100).

    Scoring factors:
    - Execution rate: 30% weight
    - Win rate: 40% weight
    - Risk events: 30% weight (inverse)

    Args:
        signal_stats: Signal statistics
        exec_stats: Execution statistics
        risk_stats: Risk statistics

    Returns:
        Health score (0-100)
    """
    score = 100.0

    # Execution rate component (target: 50-80%)
    exec_rate = signal_stats.execution_rate_pct
    if exec_rate < 20:
        score -= 30  # Too few signals executed
    elif exec_rate > 90:
        score -= 15  # Possibly too aggressive
    else:
        score -= abs(exec_rate - 65) * 0.3  # Optimal around 65%

    # Win rate component (target: 55-70%)
    win_rate = exec_stats.win_rate_pct
    if win_rate < 40:
        score -= 40  # Poor performance
    elif win_rate > 80:
        score -= 20  # Possibly curve-fitted
    else:
        score -= abs(win_rate - 60) * 0.5  # Optimal around 60%

    # Risk events component (fewer is better)
    if risk_stats.circuit_breaker_triggers > 5:
        score -= 30  # Frequent circuit breakers
    elif risk_stats.circuit_breaker_triggers > 2:
        score -= 15
    elif risk_stats.circuit_breaker_triggers > 0:
        score -= 5

    # Drawdown penalty
    if risk_stats.max_drawdown_pct > 10:
        score -= 20
    elif risk_stats.max_drawdown_pct > 7:
        score -= 10
    elif risk_stats.max_drawdown_pct > 5:
        score -= 5

    # Clamp to [0, 100]
    return max(0, min(100, int(score)))
