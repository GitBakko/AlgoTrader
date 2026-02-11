"""
Signals API router.
Lists recent trading signals and allows manual signal generation for testing.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request

from src.api.dependencies import get_strategy_manager
from src.api.schemas import SignalResponse, error_response, success_response
from src.models.schemas import PredictionResult, SignalClass
from src.strategy.strategy_manager import StrategyManager

router = APIRouter()

# Maximum signals kept in memory
MAX_SIGNAL_HISTORY = 200


@router.get("/")
async def list_signals(
    request: Request,
    epic: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
):
    """List recent trading signals."""
    signals: list[dict] = request.app.state.signal_history

    if epic:
        signals = [s for s in signals if s.get("epic") == epic]

    # Return most recent first
    result = signals[-limit:][::-1]

    return success_response(result)


@router.get("/generate")
async def generate_test_signal(
    request: Request,
    epic: str = Query(default="XAUUSD"),
    confidence: float = Query(default=0.80, ge=0.0, le=1.0),
    signal_class: int = Query(default=3, ge=0, le=4),
    manager: StrategyManager = Depends(get_strategy_manager),
):
    """
    Generate a test signal using the strategy pipeline.
    Useful for testing the signal generation flow without live data.
    """
    sc = SignalClass(signal_class)
    probs = {cls.name: 0.0 for cls in SignalClass}
    probs[sc.name] = confidence

    prediction = PredictionResult(
        signal_class=sc,
        signal_name=sc.name,
        confidence=confidence,
        probabilities=probs,
    )

    # Default market data for testing
    market_data = {
        "current_price": {"XAUUSD": 2000.0, "BTCUSD": 50000.0, "US500": 5000.0}.get(
            epic, 1000.0
        ),
        "atr": {"XAUUSD": 20.0, "BTCUSD": 1000.0, "US500": 50.0}.get(epic, 10.0),
    }

    try:
        signal = manager.process_prediction(prediction, epic, market_data)
    except Exception as e:
        return error_response(f"Signal generation failed: {e}")

    now = datetime.now(timezone.utc).isoformat()
    response = SignalResponse(
        epic=signal.epic,
        direction=signal.direction.value,
        confidence=signal.confidence,
        signal_class=signal.signal_class,
        entry_price=signal.entry_price,
        suggested_stop=signal.suggested_stop,
        suggested_tp=signal.suggested_tp,
        regime=signal.regime,
        timestamp=now,
        status="generated",
    )

    # Store in history
    history: list = request.app.state.signal_history
    history.append(response.model_dump())
    if len(history) > MAX_SIGNAL_HISTORY:
        request.app.state.signal_history = history[-MAX_SIGNAL_HISTORY:]

    return success_response(response.model_dump())
