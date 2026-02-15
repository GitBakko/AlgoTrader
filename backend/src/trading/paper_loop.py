"""
Paper trading loop.
Background task that checks for new 1h candles every 5 minutes and runs
the full ML prediction -> execution pipeline when new data is detected.

Phase 8 integration:
- TrailingStopManager: register on open, update_price each iteration, partial_close at TP1
- CircuitBreakers: heartbeat each iteration, record_trade_result on close
- EquityCurveFilter: record_trade_close on position close
- Kelly sizing: pass trade history to risk_manager.check_trade()
"""

import asyncio
import time as _time
from collections import deque
from datetime import datetime, timezone

from loguru import logger

from src.broker.client import CapitalComClient
from src.data.data_access import DataAccessLayer
from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.models.prediction_service import PredictionService
from src.risk.risk_manager import RiskManager
from src.risk.trailing_stop_manager import TrailingPhase, TrailingStopConfig, TrailingStopManager
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
        broker: CapitalComClient | None = None,
        interval_seconds: int = CHECK_INTERVAL,
        epics: list[str] | None = None,
        trailing_stop_config: TrailingStopConfig | None = None,
        db_session_factory = None,
        trailing_stop_manager: TrailingStopManager | None = None,
    ):
        self.prediction_service = prediction_service
        self.strategy_manager = strategy_manager
        self.risk_manager = risk_manager
        self.execution_engine = execution_engine
        self.data_access = data_access
        self.broker = broker
        self.interval_seconds = interval_seconds
        self.epics = epics or [
            # Original 8 assets
            "XAUUSD", "BTCUSD", "US500", "WTIUSD",
            "NVDA", "TSLA", "XAGUSD", "DE40",
            # Phase 12: New 11 assets (EURUSD excluded, NAS100 excluded - insufficient data)
            "SOLUSD", "ETHUSD", "BNBUSD", "DOGUSD", "DASHUSD", "ICPUSD",
            "NATGAS", "COPPER", "PLATINUM",
            "GBPUSD", "USDJPY",
        ]

        # Phase 8/14: trailing stop manager (use recovered one or create new)
        self.trailing_stop_manager = trailing_stop_manager or TrailingStopManager(trailing_stop_config)
        # In-memory trade history for Kelly sizing (last 200 trades, auto-discards old entries)
        self._trade_history: deque[dict] = deque(maxlen=200)
        # Phase 14: database session factory for state persistence
        self._db_session_factory = db_session_factory

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
        # Market info cache (avoid repeated API calls)
        self._market_info_cache: dict[str, dict] = {}
        self._market_cache_ttl = 3600  # 1 hour
        self._market_cache_ts: dict[str, float] = {}

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

    async def get_positions_async(self) -> list[dict]:
        """Get positions for all modes (async, works with broker or in-memory)."""
        return await self.execution_engine.get_open_positions()

    def get_paper_positions(self) -> list[dict]:
        """Get paper positions (sync, PAPER mode only, for backward compat)."""
        if self.execution_engine.mode == ExecutionMode.PAPER:
            return self.execution_engine._position_tracker.get_paper_positions_sync()
        return []

    def get_signal_history(self) -> list[dict]:
        """Get signal history as a list (public accessor, defensive copy)."""
        return list(self._signal_history)

    async def _persist_risk_state(self) -> None:
        """
        Persist current RiskManager state to database.
        Saves DrawdownMonitor, CircuitBreakers, and EquityCurveFilter state.
        """
        if self._db_session_factory is None:
            return  # No database available, skip persistence

        try:
            from decimal import Decimal

            from src.database.repositories import RiskStateRepository

            async with self._db_session_factory() as session:
                repo = RiskStateRepository(session)

                # Extract state from RiskManager components
                dm_state = self.risk_manager.drawdown_monitor.state
                cb_state = self.risk_manager.circuit_breakers
                ec_state = self.risk_manager.equity_curve_filter

                # Tripped breakers: {epic: datetime} → {epic: iso_string}
                tripped_breakers_serialized = {
                    epic: ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
                    for epic, ts in cb_state.tripped_breakers.items()
                }

                # Equity curve: keep last 50 points
                equity_curve_points = list(ec_state.equity_curve)[-50:]

                await repo.create_snapshot(
                    peak_equity=Decimal(str(dm_state.peak_equity)),
                    daily_start_equity=Decimal(str(dm_state.daily_start_equity)),
                    current_equity=Decimal(str(dm_state.current_equity)),
                    consecutive_losses=cb_state.consecutive_losses,
                    tripped_breakers=tripped_breakers_serialized,
                    equity_curve_points=equity_curve_points,
                )
                await session.commit()
                logger.debug("Persisted risk state to database")
        except Exception as e:
            logger.warning(f"Risk state persistence failed: {e}")

    async def _persist_trailing_stop_state(self, deal_id: str) -> None:
        """
        Persist trailing stop state for a specific position.

        Args:
            deal_id: Position deal identifier
        """
        if self._db_session_factory is None:
            return  # No database available, skip persistence

        try:
            from decimal import Decimal

            from src.database.repositories import TrailingStopRepository
            from src.execution.schemas import Direction

            state = self.trailing_stop_manager.get_state(deal_id)
            if state is None:
                return  # Position not tracked

            async with self._db_session_factory() as session:
                repo = TrailingStopRepository(session)

                await repo.upsert(
                    deal_id=deal_id,
                    epic=state.epic,
                    direction=Direction(state.direction),
                    entry_price=Decimal(str(state.entry_price)),
                    current_stop=Decimal(str(state.current_stop)),
                    phase=state.phase,
                    tp1_level=Decimal(str(state.tp1_level)) if state.tp1_level else None,
                    tp2_level=Decimal(str(state.tp2_level)) if state.tp2_level else None,
                    highest_price=Decimal(str(state.highest_price)) if state.highest_price else None,
                    lowest_price=Decimal(str(state.lowest_price)) if state.lowest_price else None,
                )
                await session.commit()
                logger.debug(f"Persisted trailing stop state for {deal_id}")
        except Exception as e:
            logger.warning(f"Trailing stop persistence failed for {deal_id}: {e}")

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

    async def _is_market_open(self, epic: str) -> tuple[bool, str | None]:
        """Check if market is open via cached broker market details."""
        if not self.broker:
            return True, None  # No broker → assume open (PAPER mode)

        now = _time.monotonic()
        cached_ts = self._market_cache_ts.get(epic, 0)
        if epic in self._market_info_cache and (now - cached_ts) < self._market_cache_ttl:
            info = self._market_info_cache[epic]
        else:
            try:
                info = await asyncio.wait_for(
                    self.broker.get_market_details(epic), timeout=10.0
                )
                self._market_info_cache[epic] = info
                self._market_cache_ts[epic] = now
            except Exception as e:
                logger.debug(f"[{epic}] Market info fetch failed: {e}")
                return True, None  # Graceful: if fetch fails, try anyway

        status = info.get("snapshot", {}).get("marketStatus", "TRADEABLE")
        if status != "TRADEABLE":
            return False, f"Mercato {epic} chiuso (status: {status})"
        return True, None

    async def _run_iteration(self, *, force: bool = False) -> None:
        """
        Check for new candles and run predictions where needed.

        Args:
            force: If True, process all epics regardless of candle status.
        """
        self._check_count += 1

        # Phase 8: circuit breaker heartbeat (resets timeout counter)
        self.risk_manager.circuit_breakers.heartbeat()

        # Fetch positions once per iteration (avoid N+1)
        try:
            current_positions = await asyncio.wait_for(
                self.get_positions_async(), timeout=10.0
            )
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"Position fetch timed out/failed ({e}), using local cache")
            current_positions = self.get_paper_positions()

        # Phase 8: update trailing stops for open positions
        await self._update_trailing_stops(current_positions)

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

        # Phase 14: persist risk state after iteration
        await self._persist_risk_state()

    async def _fetch_equity(self) -> float:
        """Get current equity. DEMO/LIVE: from broker. PAPER: from risk manager."""
        if self.broker and self.execution_engine.mode != ExecutionMode.PAPER:
            try:
                accounts = await asyncio.wait_for(
                    self.broker.get_accounts(), timeout=10.0
                )
                if accounts:
                    acc = accounts[0]
                    # Capital.com: 'deposit' is the funded amount, 'balance' can be 0
                    base = acc.deposit or acc.available or acc.balance
                    return base + acc.profit_loss
            except Exception as e:
                logger.warning(f"Broker equity fetch failed, using local: {e}")
        return self.risk_manager.drawdown_monitor.state.current_equity

    async def _process_epic(self, epic: str, open_positions: list[dict]) -> None:
        """Run the full pipeline for a single epic."""
        # Step 0: Market hours check (DEMO/LIVE only)
        is_open, closed_reason = await self._is_market_open(epic)
        if not is_open:
            signal_info = {
                "epic": epic,
                "direction": "HOLD",
                "confidence": 0.0,
                "entry_price": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": "market_closed",
                "rejection_reason": closed_reason,
            }
            self._last_signals[epic] = signal_info
            self._signal_history.appendleft(signal_info)
            logger.info(f"[{epic}] {closed_reason}")
            return

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
            "strategy_name": signal.strategy_name,
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

        # Step 4: Risk check (Phase 8: pass trade_history for Kelly sizing)
        equity = await self._fetch_equity()
        self.risk_manager.update_equity(equity)
        risk_result = self.risk_manager.check_trade(
            signal=signal,
            equity=equity,
            atr=market_data["atr"],
            open_positions=open_positions,
            trade_history=self._trade_history or None,
        )

        if not risk_result.approved:
            signal_info["status"] = "rejected"
            signal_info["rejection_reason"] = risk_result.rejection_reason
            logger.info(
                f"[{epic}] Risk REJECTED: {risk_result.rejection_reason}"
            )
            return

        logger.info(
            f"[{epic}] Risk APPROVED: size={risk_result.position_size:.4f}, "
            f"SL={risk_result.stop_loss}, TP={risk_result.take_profit} "
            f"sizing={risk_result.sizing_method}"
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

            # Phase 8: register position for trailing stop management
            if exec_result.deal_id:
                self.trailing_stop_manager.register_position(
                    deal_id=exec_result.deal_id,
                    epic=epic,
                    direction=signal.direction.value,
                    entry_price=exec_result.fill_price or signal.entry_price,
                    stop_loss=risk_result.stop_loss,
                    atr=market_data["atr"],
                )
                # Phase 14: persist trailing stop state
                await self._persist_trailing_stop_state(exec_result.deal_id)
        else:
            signal_info["status"] = "exec_failed"
            signal_info["rejection_reason"] = exec_result.error
            if exec_result.error_detail:
                signal_info["error_detail"] = exec_result.error_detail
            logger.warning(f"[{epic}] Execution failed: {exec_result.error}")

    async def _update_trailing_stops(self, current_positions: list[dict]) -> None:
        """
        Update trailing stops for all tracked positions.
        Called once per iteration to advance stop phases and trigger partial closes.
        """
        tracked = self.trailing_stop_manager.tracked_positions
        if not tracked:
            return

        # Build position lookup for current prices
        pos_by_id = {p.get("deal_id"): p for p in current_positions}

        for deal_id in list(tracked):
            position = pos_by_id.get(deal_id)
            if position is None:
                # Position was closed externally
                self.trailing_stop_manager.unregister_position(deal_id)
                continue

            current_price = position.get("level", 0)
            if current_price <= 0:
                continue

            # Get ATR for the epic (from prediction service market data)
            epic = position.get("epic", "")
            atr = None
            try:
                md = self.prediction_service.get_market_data(epic)
                if md:
                    atr = md.get("atr")
            except Exception:
                pass

            state_before = self.trailing_stop_manager.get_state(deal_id)
            phase_before = TrailingPhase(state_before.phase) if state_before else TrailingPhase.INITIAL

            new_stop, phase = self.trailing_stop_manager.update_price(
                deal_id=deal_id,
                current_price=current_price,
                current_atr=atr,
            )

            # Update broker/paper stop if changed
            if new_stop is not None:
                try:
                    await self.execution_engine.update_stops(deal_id, new_stop)
                    # Phase 14: persist updated trailing stop state
                    await self._persist_trailing_stop_state(deal_id)
                except Exception as e:
                    logger.debug(f"[{epic}] Stop update failed: {e}")

            # Phase 8: partial close at TP1 (INITIAL → BREAKEVEN transition)
            if phase == TrailingPhase.BREAKEVEN and phase_before == TrailingPhase.INITIAL:
                try:
                    result = await self.execution_engine.partial_close(
                        deal_id, 0.5, "TP1_HIT"
                    )
                    if result.success:
                        logger.info(f"[{epic}] TP1 hit: closed 50% of position")
                except Exception as e:
                    logger.warning(f"[{epic}] TP1 partial close failed: {e}")

    def _on_position_closed(self, deal_id: str, pnl: float) -> None:
        """
        Handle position close events for Phase 8 modules.
        Records trade result for circuit breakers, equity curve, and Kelly history.
        """
        # Circuit breaker: track consecutive wins/losses
        self.risk_manager.circuit_breakers.record_trade_result(is_win=(pnl > 0))

        # Equity curve filter: record equity point
        equity = self.risk_manager.drawdown_monitor.state.current_equity
        self.risk_manager.equity_curve_filter.record_trade_close(equity)

        # Kelly: add to trade history (deque auto-discards oldest when maxlen=200 reached)
        self._trade_history.append({"pnl": pnl})

        # Trailing stop: unregister
        self.trailing_stop_manager.unregister_position(deal_id)

        # Phase 14: persist risk state after position close (skip if no event loop)
        try:
            asyncio.create_task(self._persist_risk_state())
        except RuntimeError:
            pass  # No event loop (called from tests)

        logger.debug(
            f"Position closed: deal={deal_id} pnl={pnl:.2f} "
            f"(history={len(self._trade_history)} trades)"
        )

    def get_status(self) -> dict:
        """Get current status of the trading loop (defensive copies, sync)."""
        positions = self.get_paper_positions()
        total_pnl = sum(p.get("unrealized_pnl", 0) for p in positions)

        # Phase 8: circuit breaker and trailing stop info
        cb_tripped = self.risk_manager.circuit_breakers.tripped_breakers
        trailing_tracked = self.trailing_stop_manager.tracked_positions
        eq_below_sma = self.risk_manager.equity_curve_filter.is_below_sma

        return {
            "running": self._running,
            "execution_mode": self.execution_engine.mode.value,
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
            "circuit_breakers_tripped": cb_tripped,
            "trailing_stops_tracked": len(trailing_tracked),
            "equity_curve_below_sma": eq_below_sma,
            "kelly_trade_history_size": len(self._trade_history),
        }

    async def get_status_async(self) -> dict:
        """Get status with live position data (async, works for all modes)."""
        status = self.get_status()
        positions = await self.get_positions_async()
        status["open_positions"] = len(positions)
        status["total_unrealized_pnl"] = sum(
            p.get("unrealized_pnl", 0) for p in positions
        )
        return status
