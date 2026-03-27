"""
Signal Intelligence Layer (SIL) API Router.

Endpoints:
  GET /api/sil/status   — SIL system status and client health
  GET /api/sil/data     — Current SIL data snapshot
  GET /api/sil/calendar — Today's economic calendar events
"""

from fastapi import APIRouter, Request

from src.external.sil_schemas import SILData
from src.utils.config import get_settings

router = APIRouter()


def _get_loop(request: Request):
    """Get the paper trading loop from app state (may be None)."""
    return getattr(request.app.state, "paper_loop", None)


@router.get("/status")
async def sil_status(request: Request):
    """Get SIL system status and client health."""
    settings = get_settings()
    loop = _get_loop(request)

    base = {
        "enabled": settings.sil_enabled,
        "calendar_gate_enabled": settings.sil_calendar_gate_enabled,
        "calendar_minutes_before": settings.sil_calendar_minutes_before,
        "calendar_minutes_after": settings.sil_calendar_minutes_after,
        "cache_ttl_minutes": settings.sil_cache_ttl_minutes,
        "features_count": 12,
    }

    if loop is None or not settings.sil_enabled:
        return {"success": True, "data": {**base, "clients_initialized": False}}

    sil_data: SILData = getattr(loop, "_sil_data", SILData())
    initialized = getattr(loop, "_sil_clients_initialized", False)

    clients = {}
    if initialized:
        for name, attr in [
            ("fear_greed", "_fg_client"),
            ("fred", "_fred_client"),
            ("alpha_vantage", "_av_client"),
            ("cot", "_cot_client"),
            ("social", "_social_client"),
        ]:
            client = getattr(loop, attr, None)
            if client:
                # Get cache age for primary key
                primary_key = {
                    "fear_greed": "fear_greed",
                    "fred": "fred",
                    "alpha_vantage": "av_financial_markets",
                    "cot": "cot_XAUUSD",
                    "social": "social_XAUUSD",
                }.get(name, name)
                age = client.cache_age_minutes(primary_key)
                clients[name] = {
                    "status": "cached" if age is not None else "not_fetched",
                    "cache_age_minutes": round(age, 1) if age is not None else None,
                }

    return {
        "success": True,
        "data": {
            **base,
            "clients_initialized": initialized,
            "clients": clients,
            "fetch_errors": sil_data.fetch_errors,
        },
    }


@router.get("/data")
async def sil_data(request: Request):
    """Get current SIL data snapshot."""
    settings = get_settings()
    if not settings.sil_enabled:
        return {"success": True, "data": {"enabled": False}}

    loop = _get_loop(request)
    if loop is None:
        return {"success": True, "data": {"enabled": True, "message": "Trading loop not running"}}

    sil: SILData = getattr(loop, "_sil_data", SILData())
    return {
        "success": True,
        "data": sil.model_dump(mode="json"),
    }


@router.get("/calendar")
async def sil_calendar(request: Request):
    """Get today's economic calendar events and blackout windows."""
    settings = get_settings()
    if not settings.sil_enabled or not settings.sil_calendar_gate_enabled:
        return {"success": True, "data": {"enabled": False, "events": []}}

    loop = _get_loop(request)
    if loop is None:
        return {
            "success": True,
            "data": {"enabled": True, "events": [], "message": "Trading loop not running"},
        }

    gate = getattr(loop, "_calendar_gate", None)
    if gate is None:
        return {"success": True, "data": {"enabled": True, "events": []}}

    events = gate.get_cached_events()
    from src.risk.economic_calendar_gate import EconomicCalendarGate

    return {
        "success": True,
        "data": {
            "enabled": True,
            "minutes_before": settings.sil_calendar_minutes_before,
            "minutes_after": settings.sil_calendar_minutes_after,
            "total_events": len(events),
            "high_impact_events": [
                {
                    "event": e.event,
                    "country": e.country,
                    "time": e.event_time.isoformat() if e.event_time else None,
                    "forecast": e.forecast,
                    "previous": e.previous,
                    "actual": e.actual,
                }
                for e in events
                if EconomicCalendarGate._is_high_impact(e.event)
            ],
        },
    }
