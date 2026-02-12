"""
Paper trading loop.
Background task that checks for new 1h candles every 5 minutes and runs
the full ML prediction -> execution pipeline when new data is detected.
"""

import asyncio
from collections import deque
from datetime import datetime, timezone

from loguru import logger

from src.data.data_access import DataAccessLayer
from src.execution.execution_engine import ExecutionEngine
from src.models.prediction_service import PredictionService
from src.risk.risk_manager import RiskManager
from src.strategy.strategy_manager import StrategyManager

# How often to check for new candles (seconds)
CHECK_INTERVAL = 300  # 5 minutes
MAX_SIGNAL_HISTORY = 200


class PaperTradingLoop:
    """
    Controllable background loop that runs paper trading iterations.

    Checks every 5 minutes for new 1h candles. When a new candle is detected
    for any epic, it runs the full prediction pipeline for that epic only.

    Each iteration:
    1. Check if new 1h candle available (compare timestamps)
    2. PredictionService.predict() for each epic with new data
    3. StrategyManager.process_prediction() -> TradingSignal
    4. RiskManager.check_trade() -> RiskCheckResult
    5. ExecutionEngine.execute_signal() (paper mode) -> ExecutionResult
    """

    def __init__(
        self,
        prediction_service: PredictionService,
        strategy_manager: StrategyManager,
        risk_manager: RiskManager,
        execution_engine: ExecutionEngine,
        data_access: DataAccessLayer | None = None,
        interval_seconds: int = CHECK_INTERVAL,
        epics: list[str] | None = None,
    ):
        self.prediction_service = prediction_service
        self.strategy_manager = strategy_manager
        self.risk_manager = risk_manager
        self.execution_engine = execution_engine
        self.data_access = data_access
        self.interval_seconds = interval_seconds
        self.epics = epics or [
            "XAUUSD", "BTCUSD", "US500", "WTIUSD",
            "NVDA", "TSLA", "XAGUSD", "DE40",
        ]

        self._running = False
        self._task: asyncio.Task | None = None
        self._last_run: datetime | None = None
        self._iteration_count = 0
        self._check_count = 0
        self._trade_count = 0
        self._signal_count = 0
        self._error_count = 0
        self._last_signals: dict[str, dict] = {}
        self._signal_history: deque[dict] = deque(maxlen=MAX_SIGNAL_HISTORY)
        # Track last processed candle timestamp per epic
        self._last_candle_ts: dict[str, datetime] = {}

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def last_run(self) -> datetime | None:
        return self._last_run

    @property
    def iteration_count(self) -> int:
        return self._iteration_count

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def signal_count(self) -> int:
        return self._signal_count

    @property
    def last_signals(self) -> dict[str, dict]:
        """Last signal info per epic (read-only copy)."""
        return dict(self._last_signals)

    def get_paper_positions(self) -> list[dict]:
        """Get current paper trading positions (public accessor)."""
        return self.execution_engine._position_tracker.get_paper_positions_sync()

    def get_signal_history(self) -> list[dict]:
        """Get signal history as a list (public accessor, defensive copy)."""
        return list(self._signal_history)

    def start(self) -> None:
        """Start the paper trading loop."""
        if self._running:
            logger.warning("Paper trading loop is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="paper_trading_loop")
        self._task.add_done_callback(self._on_task_done)
        logger.info(
            f"Paper trading loop started (check every {self.interval_seconds}s, "
            f"epics={self.epics})"
        )

    def stop(self) -> None:
        """Stop the paper trading loop."""
        if not self._running:
            logger.warning("Paper trading loop is not running")
            return

        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("Paper trading loop stopped")

    def _on_task_done(self, task: asyncio.Task) -> None:
        """Callback when the loop task finishes."""
        self._running = False
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(f"Paper trading loop crashed: {exc}")

    async def _run_loop(self) -> None:
        """Main loop: check for new candles at fixed intervals."""
        # Run first iteration immediately (process all epics regardless)
        try:
            await self._run_iteration(force=True)
        except Exception as e:
            self._error_count += 1
            logger.error(f"First iteration failed: {e}")

        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                await self._run_iteration(force=False)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Paper trading iteration error: {e}")
                await asyncio.sleep(60)

    def _has_new_candle(self, epic: str) -> bool:
        """Check if there's a new 1h candle since last processed."""
        if self.data_access is None:
            return True  # No data access → always run (legacy behavior)

        try:
            latest = self.data_access.get_latest_price(epic, timeframe="1h")
            if latest is None:
                return False

            candle_ts = latest.get("timestamp")
            if candle_ts is None:
                return False

            last_ts = self._last_candle_ts.get(epic)

            if last_ts is None or candle_ts > last_ts:
                self._last_candle_ts[epic] = candle_ts
                return True
            return False
        except Exception as e:
            logger.debug(f"[{epic}] Candle check failed: {e}")
            return True  # On error, run anyway to avoid missing signals

    async def _run_iteration(self, *, force: bool = False) -> None:
        """
        Check for new candles and run predictions where needed.

        Args:
            force: If True, process all epics regardless of candle status.
        """
        self._check_count += 1

        # Fetch positions once per iteration (avoid N+1)
        current_positions = self.get_paper_positions()
        open_epics = {p.get("epic") for p in current_positions}

        epics_to_process = []
        for epic in self.epics:
            if not self.prediction_service.has_model_for(epic):
                continue
            if epic in open_epics:
                continue  # Already has open position
            if force or self._has_new_candle(epic):
                epics_to_process.append(epic)

        if not epics_to_process:
            logger.debug(
                f"Check #{self._check_count}: no new candles, skipping"
            )
            return

        self._iteration_count += 1
        self._last_run = datetime.now(timezone.utc)
        logger.info(
            f"Paper trading iteration #{self._iteration_count} "
            f"(check #{self._check_count}, epics: {epics_to_process})"
        )

        for epic in epics_to_process:
            try:
                await self._process_epic(epic, current_positions)
            except Exception as e:
                self._error_count += 1
                logger.error(f"Error processing {epic} (total errors: {self._error_count}): {e}")

    async def _process_epic(self, epic: str, open_positions: list[dict]) -> None:
        """Run the full pipeline for a single epic."""
        # Step 1: ML Prediction
        prediction = self.prediction_service.predict(epic)
        if prediction is None:
            logger.debug(f"[{epic}] No prediction generated")
            return

        logger.info(
            f"[{epic}] Prediction: {prediction.signal_name} "
            f"(confidence={prediction.confidence:.3f})"
        )

        # Step 2: Get market data
        market_data = self.prediction_service.get_market_data(epic)
        if market_data is None:
            logger.warning(f"[{epic}] No market data available")
            return

        # Step 3: Strategy -> TradingSignal
        signal = self.strategy_manager.process_prediction(prediction, epic, market_data)
        self._signal_count += 1
        signal_info = {
            "epic": epic,
            "direction": signal.direction.value,
            "confidence": signal.confidence,
            "entry_price": signal.entry_price,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "predicted",
        }
        self._last_signals[epic] = signal_info
        self._signal_history.appendleft(signal_info)

        logger.info(
            f"[{epic}] Signal: {signal.direction.value} "
            f"@ {signal.entry_price:.2f} "
            f"(confidence={signal.confidence:.3f})"
        )

        if signal.direction.value == "HOLD":
            signal_info["status"] = "hold"
            logger.info(f"[{epic}] HOLD signal, skipping execution")
            return

        # Step 4: Risk check
        state = self.risk_manager.drawdown_monitor.state
        risk_result = self.risk_manager.check_trade(
            signal=signal,
            equity=state.current_equity,
            atr=market_data["atr"],
            open_positions=open_positions,
        )

        if not risk_result.approved:
            signal_info["status"] = "rejected"
            logger.info(
                f"[{epic}] Risk REJECTED: {risk_result.rejection_reason}"
            )
            return

        logger.info(
            f"[{epic}] Risk APPROVED: size={risk_result.position_size:.4f}, "
            f"SL={risk_result.stop_loss}, TP={risk_result.take_profit}"
        )

        # Step 5: Execute (paper mode)
        exec_result = await self.execution_engine.execute_signal(signal, risk_result)
        if exec_result.success:
            self._trade_count += 1
            signal_info["status"] = "executed"
            logger.info(
                f"[{epic}] EXECUTED: deal_id={exec_result.deal_id}, "
                f"fill={exec_result.fill_price:.2f}"
            )
        else:
            signal_info["status"] = "rejected"
            logger.warning(f"[{epic}] Execution failed: {exec_result.error}")

    def get_status(self) -> dict:
        """Get current status of the paper trading loop (defensive copies)."""
        positions = self.get_paper_positions()
        total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)

        return {
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "epics": list(self.epics),
            "iteration_count": self._iteration_count,
            "check_count": self._check_count,
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "signal_count": self._signal_count,
            "trade_count": self._trade_count,
            "error_count": self._error_count,
            "open_positions": len(positions),
            "total_unrealized_pnl": total_pnl,
            "last_signals": dict(self._last_signals),
            "models_loaded": self.prediction_service.get_loaded_models(),
            "last_candle_timestamps": {
                epic: ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                for epic, ts in self._last_candle_ts.items()
            },
        }
