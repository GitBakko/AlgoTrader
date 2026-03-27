"""
Backtest API router.
Run backtests using the BacktestEngine with real ML signals on historical data,
or with rule-based strategies (squeeze_breakout, vwap_reversion, auto).
"""

import uuid
from datetime import datetime, timezone

import polars as pl
from fastapi import APIRouter, Path, Request
from loguru import logger

from src.api.schemas import (
    BacktestRunRequest,
    BacktestRunResponse,
    error_response,
    success_response,
)
from src.backtest.engine import BacktestEngine
from src.backtest.reporter import BacktestReporter
from src.backtest.schemas import BacktestConfig
from src.backtest.signal_generator import BacktestSignalGenerator
from src.features.builder import FeatureBuilder
from src.models.schemas import SignalClass
from src.strategy.squeeze_strategy import SqueezeBreakoutStrategy
from src.strategy.strategy_router import StrategyRouter
from src.strategy.vwap_strategy import VWAPReversionStrategy

router = APIRouter()

MAX_BACKTEST_RUNS = 100

VALID_STRATEGIES = {"ml_ensemble", "squeeze_breakout", "vwap_reversion", "auto"}


def _convert_strategy_signals(strategy_df: pl.DataFrame) -> pl.DataFrame:
    """
    Convert strategy backtest signals to BacktestEngine format.

    Strategy output: signal_direction (1=BUY, -1=SELL, 0=HOLD), signal_confidence
    Engine expects: signal (SignalClass: BUY=2, SELL=0, HOLD=1), confidence, atr
    """
    # Map signal_direction to SignalClass values
    signals_df = strategy_df.select(
        [
            pl.col("timestamp"),
            pl.when(pl.col("signal_direction") == 1)
            .then(pl.lit(SignalClass.BUY))  # 2
            .when(pl.col("signal_direction") == -1)
            .then(pl.lit(SignalClass.SELL))  # 0
            .otherwise(pl.lit(SignalClass.HOLD))  # 1
            .alias("signal"),
            pl.col("signal_confidence").alias("confidence"),
            (
                pl.col("atr_14").alias("atr")
                if "atr_14" in strategy_df.columns
                else pl.lit(0.0).alias("atr")
            ),
        ]
    ).sort("timestamp")

    return signals_df


@router.post("/run")
async def run_backtest(
    request: Request,
    body: BacktestRunRequest,
):
    """
    Run a backtest using BacktestEngine with ML-generated signals
    or rule-based strategy signals.

    Strategies:
    - ml_ensemble (default): ML model inference via BacktestSignalGenerator
    - squeeze_breakout: Volatility squeeze breakout strategy
    - vwap_reversion: VWAP SD band mean-reversion strategy
    - auto: StrategyRouter selects based on regime

    Requires:
    - DataAccessLayer with historical data (app.state.data_access)
    - For ml_ensemble: PredictionService with loaded models + FeatureBuilder
    """
    strategy_name = body.strategy
    if strategy_name not in VALID_STRATEGIES:
        return error_response(
            f"Invalid strategy '{strategy_name}'. " f"Valid: {', '.join(sorted(VALID_STRATEGIES))}",
            400,
        )

    run_id = uuid.uuid4().hex[:12]
    now_str = datetime.now(timezone.utc).isoformat()

    # Get services from app state
    data_access = getattr(request.app.state, "data_access", None)

    if data_access is None:
        return error_response("DataAccessLayer not available.", 500)

    epic = body.epic
    timeframe = body.timeframe

    # ML-specific validations
    if strategy_name == "ml_ensemble":
        prediction_service = getattr(request.app.state, "prediction_service", None)
        feature_builder = getattr(request.app.state, "feature_builder", None)

        if prediction_service is None or not prediction_service.has_models:
            return error_response("No ML models loaded. Train models first.", 400)
        if feature_builder is None:
            return error_response("FeatureBuilder not available.", 500)
        if not prediction_service.has_model_for(epic):
            return error_response(f"No model loaded for {epic}.", 400)

    # Parse date range
    start_date = None
    end_date = None
    if body.start_date:
        try:
            start_date = datetime.fromisoformat(body.start_date)
        except ValueError:
            return error_response(f"Invalid start_date format: {body.start_date}", 400)
    if body.end_date:
        try:
            end_date = datetime.fromisoformat(body.end_date)
        except ValueError:
            return error_response(f"Invalid end_date format: {body.end_date}", 400)

    # Load OHLC data
    ohlc_df = data_access.get_candles(
        epic=epic,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
    )

    if ohlc_df.is_empty() or len(ohlc_df) < 100:
        return error_response(
            f"Insufficient data for {epic}/{timeframe}: {len(ohlc_df)} bars (need >= 100).",
            400,
        )

    # === Generate signals based on strategy ===
    if strategy_name == "ml_ensemble":
        # Existing ML flow
        prediction_service = request.app.state.prediction_service
        feature_builder = request.app.state.feature_builder

        model, meta = prediction_service._loaded_models[epic]
        calibrator = prediction_service._calibrators.get(epic)
        feature_names = meta.feature_names or []

        signal_gen = BacktestSignalGenerator()
        signals_df = signal_gen.generate_signals(
            model=model,
            feature_builder=feature_builder,
            ohlc_df=ohlc_df,
            epic=epic,
            timeframe=timeframe,
            feature_names=feature_names,
            calibrator=calibrator,
            min_confidence=0.40,
        )
    else:
        # Rule-based strategy flow
        # Build features (single-timeframe, no DataAccessLayer needed for indicators)
        fb = FeatureBuilder(data_access=None)
        df_with_features, _ = fb.build_features_from_df(
            ohlc_df,
            epic,
            timeframe,
            include_regime=True,
            normalize=False,
        )

        # Create strategy instance and generate signals
        if strategy_name == "squeeze_breakout":
            strategy = SqueezeBreakoutStrategy()
        elif strategy_name == "vwap_reversion":
            strategy = VWAPReversionStrategy()
        elif strategy_name == "auto":
            router_inst = StrategyRouter()
            router_inst.register_strategy(SqueezeBreakoutStrategy())
            router_inst.register_strategy(VWAPReversionStrategy())
            strategy = router_inst
        else:
            return error_response(f"Unknown strategy: {strategy_name}", 400)

        strategy_df = strategy.generate_backtest_signals(
            df_with_features,
            epic,
            timeframe,
        )

        # Convert strategy signals to BacktestEngine format
        signals_df = _convert_strategy_signals(strategy_df)

    if signals_df.is_empty():
        return error_response("Signal generation produced no signals.", 500)

    # Determine backtest date range from actual data
    bt_start = ohlc_df["timestamp"].min()
    bt_end = ohlc_df["timestamp"].max()

    # Run backtest
    config = BacktestConfig(
        epic=epic,
        timeframe=timeframe,
        start_date=bt_start,
        end_date=bt_end,
        initial_capital=body.initial_equity,
        risk_per_trade=body.risk_per_trade,
    )

    engine = BacktestEngine(config)
    result = engine.run(ohlc_df, signals_df)

    # Generate report
    report = BacktestReporter.generate_report(result)
    metrics = result.metrics

    # Build response
    run_response = BacktestRunResponse(
        id=run_id,
        epic=epic,
        status="completed",
        total_return_pct=round(metrics.get("total_return", 0.0) * 100, 2),
        sharpe_ratio=round(metrics.get("sharpe_ratio", 0.0), 2),
        max_drawdown_pct=round(metrics.get("max_drawdown", 0.0) * 100, 2),
        total_trades=metrics.get("total_trades", 0),
        win_rate=round(metrics.get("win_rate", 0.0) * 100, 1),
        created_at=now_str,
    )

    # Store in app state
    runs: dict = request.app.state.backtest_runs
    runs[run_id] = {
        "summary": run_response.model_dump(),
        "config": body.model_dump(),
        "equity_curve": report.get("equity_curve", []),
        "trades": report.get("trades", []),
        "metrics": report.get("risk_metrics", {}),
        "trade_metrics": report.get("trade_metrics", {}),
    }

    # Evict oldest runs if over limit
    if len(runs) > MAX_BACKTEST_RUNS:
        oldest = sorted(runs, key=lambda k: runs[k]["summary"].get("created_at", ""))
        for key in oldest[: len(runs) - MAX_BACKTEST_RUNS]:
            del runs[key]

    logger.info(
        f"Backtest {run_id} complete: {epic}/{timeframe} [{strategy_name}], "
        f"{result.total_trades} trades, return={metrics.get('total_return', 0):.2%}"
    )

    return success_response(run_response.model_dump())


@router.get("/runs")
async def list_backtest_runs(request: Request):
    """List all backtest runs."""
    runs: dict = request.app.state.backtest_runs
    summaries = [run["summary"] for run in runs.values()]

    # Most recent first
    summaries.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    return success_response(summaries)


@router.get("/runs/{run_id}")
async def get_backtest_run(
    request: Request,
    run_id: str = Path(...),
):
    """Get detailed backtest results including equity curve and trades."""
    runs: dict = request.app.state.backtest_runs
    run = runs.get(run_id)

    if run is None:
        return error_response(f"Backtest run {run_id} not found", 404)

    return success_response(run)
