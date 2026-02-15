"""
System API router.
Provides system settings, risk status, and event log.
"""

from fastapi import APIRouter, Depends, HTTPException, Request

from src.api.dependencies import get_risk_manager
from src.api.schemas import (
    RecoveryReportResponse,
    RiskStatusResponse,
    SystemSettingsResponse,
    success_response,
)
from src.risk.risk_manager import RiskManager
from src.utils.config import get_settings

router = APIRouter()


@router.get("/settings")
async def get_system_settings():
    """Get read-only system configuration."""
    settings = get_settings()

    response = SystemSettingsResponse(
        app_name=settings.app_name,
        app_version=settings.app_version,
        environment=settings.environment,
        trading_enabled=settings.trading_enabled,
        paper_trading=settings.paper_trading,
        use_demo=settings.use_demo,
        min_confidence_threshold=settings.min_confidence_threshold,
        max_risk_per_trade=settings.max_risk_per_trade,
        max_daily_drawdown=settings.max_daily_drawdown,
        max_total_drawdown=settings.max_total_drawdown,
    )

    return success_response(response.model_dump())


@router.get("/risk-status")
async def get_risk_status(
    risk_mgr: RiskManager = Depends(get_risk_manager),
):
    """Get current risk management status including drawdown and circuit breaker."""
    state = risk_mgr.drawdown_monitor.state

    response = RiskStatusResponse(
        peak_equity=state.peak_equity,
        current_equity=state.current_equity,
        current_drawdown_pct=state.current_drawdown_pct,
        daily_pnl=state.daily_pnl,
        circuit_breaker_active=state.circuit_breaker_active,
        circuit_breaker_reason=state.circuit_breaker_reason,
    )

    return success_response(response.model_dump())


@router.get("/events")
async def get_system_events(limit: int = 50):
    """
    Get recent system events.
    MVP: returns empty list. Full implementation with DB in Phase 5.
    """
    return success_response([])


@router.get("/recovery-report", response_model=RecoveryReportResponse)
async def get_recovery_report(request: Request) -> RecoveryReportResponse:
    """
    Get the last state recovery report from system startup.

    Returns:
        RecoveryReportResponse with recovery details and timestamp

    Raises:
        HTTPException: 404 if no recovery report available
    """
    report = getattr(request.app.state, "last_recovery_report", None)

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="No recovery report available (system not yet started or recovery failed)",
        )

    return RecoveryReportResponse(
        success=report.success,
        positions_recovered=report.positions_recovered,
        positions_source=report.positions_source,
        trailing_stops_restored=report.trailing_stops_restored,
        trade_history_count=report.trade_history_count,
        risk_state_restored=report.risk_state_restored,
        warnings=report.warnings,
        errors=report.errors,
        recovered_at=report.recovered_at,
    )
