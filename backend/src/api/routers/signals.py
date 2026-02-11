"""
Signals API router.
Lists recent trading signals, test signal generation, and real ML-based predictions.
Dual-mode: uses DB when available, falls back to in-memory list.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Path, Query, Request

from loguru import logger

from src.api.dependencies import (
    get_db_session,
    get_execution_engine,
    get_prediction_service,
    get_risk_manager,
    get_signal_repo,
    get_strategy_manager,
)
from src.api.schemas import SignalResponse, error_response, success_response
from src.models.schemas import PredictionResult, SignalClass
from src.strategy.strategy_manager import StrategyManager

router = APIRouter()

# Maximum signals kept in memory
MAX_SIGNAL_HISTORY = 200


def _signal_from_db(s) -> dict:
    """Convert a DB Signal model to SignalResponse dict."""
    return SignalResponse(
        id=s.id,
        epic=s.epic,
        direction=s.direction,
        confidence=float(s.confidence),
        signal_class=0,
        entry_price=float(s.predicted_price) if s.predicted_price else 0.0,
        suggested_stop=float(s.stop_loss_price) if s.stop_loss_price else None,
        suggested_tp=float(s.take_profit_price) if s.take_profit_price else None,
        timestamp=s.generated_at.isoformat() if s.generated_at else "",
        status=s.status,
    ).model_dump()


@router.get("/")
async def list_signals(
    request: Request,
    epic: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    signal_repo=Depends(get_signal_repo),
):
    """List recent trading signals."""
    # Try DB first
    if signal_repo is not None:
        if epic:
            signals = await signal_repo.get_recent_signals(epic, hours=168)
        else:
            signals = await signal_repo.get_all(limit=limit)
        return success_response([_signal_from_db(s) for s in signals[:limit]])

    # Fallback: in-memory
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
    signal_class: int = Query(default=2, ge=0, le=2),
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


@router.post("/predict/{epic}")
async def predict_and_execute(
    request: Request,
    epic: str = Path(...),
    timeframe: str = Query(default="1h"),
    execute: bool = Query(default=False),
    prediction_service=Depends(get_prediction_service),
    manager: StrategyManager = Depends(get_strategy_manager),
    risk_mgr=Depends(get_risk_manager),
    engine=Depends(get_execution_engine),
    db_session=Depends(get_db_session),
):
    """
    Generate a real ML prediction for an asset and optionally execute the trade.

    Pipeline: PredictionService -> StrategyManager -> RiskManager -> ExecutionEngine

    Args:
        epic: Asset to predict (XAUUSD, BTCUSD, US500)
        timeframe: Timeframe for prediction (default 1h)
        execute: If True, execute the trade after risk approval
    """
    if prediction_service is None:
        return error_response("Prediction service not available", 503)

    if not prediction_service.has_model_for(epic):
        return error_response(
            f"No model loaded for {epic}. Train a model first.", 503
        )

    # Step 1: ML Prediction
    prediction = prediction_service.predict(epic, timeframe)
    if prediction is None:
        return error_response(f"Prediction failed for {epic}/{timeframe}", 500)

    # Step 2: Get market data for strategy/risk
    market_data = prediction_service.get_market_data(epic, timeframe)
    if market_data is None:
        return error_response(f"No market data available for {epic}", 500)

    # Step 3: Strategy -> TradingSignal
    try:
        signal = manager.process_prediction(prediction, epic, market_data)
    except Exception as e:
        return error_response(f"Strategy processing failed: {e}", 500)

    now = datetime.now(timezone.utc).isoformat()
    response_data = SignalResponse(
        epic=signal.epic,
        direction=signal.direction.value,
        confidence=signal.confidence,
        signal_class=signal.signal_class,
        entry_price=signal.entry_price,
        suggested_stop=signal.suggested_stop,
        suggested_tp=signal.suggested_tp,
        regime=signal.regime,
        timestamp=now,
        status="predicted",
    ).model_dump()

    # Step 4: Risk check
    state = risk_mgr.drawdown_monitor.state
    risk_result = risk_mgr.check_trade(
        signal=signal,
        equity=state.current_equity,
        atr=market_data["atr"],
    )

    response_data["risk_approved"] = risk_result.approved
    response_data["position_size"] = risk_result.position_size
    response_data["risk_stop_loss"] = risk_result.stop_loss
    response_data["risk_take_profit"] = risk_result.take_profit
    if not risk_result.approved:
        response_data["rejection_reason"] = risk_result.rejection_reason
        response_data["status"] = "rejected"

    # Step 5: Execute (only if approved and requested)
    if execute and risk_result.approved and signal.direction.value != "HOLD":
        exec_result = await engine.execute_signal(signal, risk_result)
        response_data["executed"] = exec_result.success
        response_data["deal_id"] = exec_result.deal_id
        response_data["fill_price"] = exec_result.fill_price
        response_data["status"] = "executed" if exec_result.success else "execution_failed"

        # Persist to DB via DI-provided session (auto-commit/rollback)
        if exec_result.success and db_session is not None:
            try:
                from src.execution.persistence import ExecutionPersistence

                await ExecutionPersistence.persist_execution(
                    session=db_session,
                    signal=signal,
                    result=exec_result,
                    position_size=risk_result.position_size,
                    stop_loss=risk_result.stop_loss,
                    take_profit=risk_result.take_profit,
                )
            except Exception as e:
                logger.warning(f"Failed to persist execution: {e}")

    # Publish signal event via Redis (fire-and-forget)
    event_bus = getattr(request.app.state, "event_bus", None)
    if event_bus:
        try:
            await event_bus.publish(f"signal:{epic}", response_data)
        except Exception as e:
            logger.debug(f"Event publish failed for signal:{epic}: {e}")

    # Store in signal history
    history: list = request.app.state.signal_history
    history.append(response_data)
    if len(history) > MAX_SIGNAL_HISTORY:
        request.app.state.signal_history = history[-MAX_SIGNAL_HISTORY:]

    return success_response(response_data)
