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
from src.monitoring.metrics import MetricsCollector
from src.monitoring.trade_logger import get_trade_logger, SignalType, ExecutionStatus, RiskEventType
from src.strategy.strategy_manager import StrategyManager
from src.utils.constants import TRADABLE_ASSETS

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
        self.epics = epics or list(TRADABLE_ASSETS)

        # Derive log source from execution mode
        from src.execution.schemas import ExecutionMode
        mode = execution_engine.mode if execution_engine else ExecutionMode.PAPER
        self._log_source = {
            ExecutionMode.PAPER: "paper_trading",
            ExecutionMode.DEMO: "demo_trading",
            ExecutionMode.LIVE: "live_trading",
        }.get(mode, "paper_trading")

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

        # HIGH-7 FIX: Track recently processed signals to prevent duplicates
        # Format: (epic, direction, entry_price_rounded) -> timestamp
        self._recent_signals: dict[tuple[str, str, float], datetime] = {}
        self._signal_dedup_window_seconds = 60  # Ignore duplicates within 60s
        self._last_signals: dict[str, dict] = {}
        self._signal_history: deque[dict] = deque(maxlen=MAX_SIGNAL_HISTORY)
        # Track last processed candle timestamp per epic
        self._last_candle_ts: dict[str, datetime] = {}
        # Market info cache (avoid repeated API calls)
        self._market_info_cache: dict[str, dict] = {}
        self._market_cache_ttl = 3600  # 1 hour
        self._market_cache_ts: dict[str, float] = {}
        # Dedicated min deal size cache (seeded from DB at startup, updated per-iteration)
        self._min_deal_size_cache: dict[str, float] = {}
        # Regime distribution tracking per epic (Step 7: regime detection)
        self._regime_counts: dict[str, dict[str, int]] = {}
        # Track positions from previous iteration to detect broker-closed positions
        self._previous_positions: dict[str, dict] = {}
        # Asset momentum rotation
        self._active_assets: set[str] | None = None  # None = all assets
        self._asset_rotation_ts: float = 0.0
        self._per_asset_losses: dict[str, int] = {}  # consecutive loss counter per asset

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
        """Get positions for all modes (async, works with broker or in-memory).

        Enriches each position with trailing_stop_phase from TrailingStopManager.
        """
        positions = await self.execution_engine.get_open_positions()
        for pos in positions:
            deal_id = pos.get("deal_id", "")
            state = self.trailing_stop_manager.get_state(deal_id)
            if state is None:
                # Try matching by epic (broker deal_ids can differ)
                for tracked_id in self.trailing_stop_manager.tracked_positions:
                    ts = self.trailing_stop_manager.get_state(tracked_id)
                    if ts and ts.epic == pos.get("epic"):
                        state = ts
                        break
            if state:
                from src.risk.trailing_stop_manager import TrailingPhase
                pos["trailing_stop_phase"] = TrailingPhase(state.phase).name
        return positions

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

                # Tripped breakers: {breaker_type: reason_string}
                tripped_breakers_serialized = dict(cb_state.tripped_breakers)

                # Equity curve: keep last 50 points
                equity_curve_points = list(ec_state._equity_points)[-50:]

                await repo.create_snapshot(
                    peak_equity=Decimal(str(dm_state.peak_equity)),
                    daily_start_equity=Decimal(str(dm_state.daily_start_equity)),
                    current_equity=Decimal(str(dm_state.current_equity)),
                    consecutive_losses=cb_state._consecutive_losses,
                    tripped_breakers=tripped_breakers_serialized,
                    equity_curve_points=equity_curve_points,
                )
                await session.commit()
                logger.debug("Persisted risk state to database")
        except Exception as e:
            logger.warning(f"Risk state persistence failed: {e}")

    async def _persist_position_open(
        self, deal_id: str, epic: str, direction: str,
        size: float, entry_price: float,
        stop_loss: float | None, take_profit: float | None,
    ) -> None:
        """Persist a newly opened position to the database."""
        if self._db_session_factory is None:
            return

        try:
            from decimal import Decimal
            from src.database.models import Position, Trade
            from src.database.repositories import PositionRepository

            async with self._db_session_factory() as session:
                repo = PositionRepository(session)

                # Check for existing (idempotency)
                existing = await repo.get_by_deal_id(deal_id)
                if existing:
                    logger.debug(f"Position {deal_id} already in DB, skipping")
                    await session.commit()
                    return

                pos = Position(
                    deal_id=deal_id,
                    epic=epic,
                    direction=direction,
                    size=Decimal(str(size)),
                    entry_price=Decimal(str(entry_price)),
                    stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
                    take_profit=Decimal(str(take_profit)) if take_profit else None,
                    status="OPEN",
                    opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                pos = await repo.create(pos)

                # Also create an OPEN trade record
                trade = Trade(
                    position_id=pos.id,
                    deal_reference=deal_id,
                    trade_type="OPEN",
                    epic=epic,
                    direction=direction,
                    size=Decimal(str(size)),
                    price=Decimal(str(entry_price)),
                    executed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                session.add(trade)
                await session.commit()
                logger.debug(f"Persisted OPEN position to DB: {deal_id} ({epic} {direction})")
        except Exception as e:
            logger.warning(f"Position open persistence failed for {deal_id}: {e}")

    async def _persist_position_close(
        self, deal_id: str, epic: str, direction: str,
        size: float, entry_price: float, exit_price: float,
        pnl: float, close_reason: str,
        opened_at: datetime | None = None,
    ) -> None:
        """Persist position close to the database (update status + create CLOSE trade)."""
        if self._db_session_factory is None:
            return

        # Normalize close_reason to short form expected by frontend
        reason_map = {
            "STOP_LOSS_HIT": "SL",
            "TAKE_PROFIT_HIT": "TP",
            "TP1_HIT": "TP",
            "API close request": "MANUAL",
            "Graceful shutdown": "MANUAL",
        }
        close_reason = reason_map.get(close_reason, close_reason)

        try:
            from decimal import Decimal
            from src.database.models import Position, Trade
            from src.database.repositories import PositionRepository

            async with self._db_session_factory() as session:
                repo = PositionRepository(session)
                pos = await repo.get_by_deal_id(deal_id)

                if pos is None:
                    # Position was never persisted at open — create it as CLOSED
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    actual_opened = opened_at or now
                    if isinstance(actual_opened, str):
                        try:
                            parsed = datetime.fromisoformat(actual_opened)
                            # Convert to UTC if timezone-aware, then strip tzinfo
                            if parsed.tzinfo is not None:
                                parsed = parsed.astimezone(timezone.utc)
                            actual_opened = parsed.replace(tzinfo=None)
                        except (ValueError, TypeError):
                            actual_opened = now
                    elif hasattr(actual_opened, 'tzinfo') and actual_opened.tzinfo is not None:
                        actual_opened = actual_opened.astimezone(timezone.utc).replace(tzinfo=None)

                    # Guard: opened_at must never be after closed_at
                    if actual_opened > now:
                        logger.warning(
                            f"Position {deal_id}: opened_at ({actual_opened}) > "
                            f"closed_at ({now}), correcting to closed_at"
                        )
                        actual_opened = now

                    pos = Position(
                        deal_id=deal_id,
                        epic=epic,
                        direction=direction,
                        size=Decimal(str(size)),
                        entry_price=Decimal(str(entry_price)),
                        current_price=Decimal(str(exit_price)),
                        profit_loss=Decimal(str(round(pnl, 2))),
                        stop_loss=None,
                        take_profit=None,
                        status="CLOSED",
                        opened_at=actual_opened,
                        closed_at=now,
                        close_reason=close_reason,
                    )
                    pos = await repo.create(pos)
                else:
                    # Update existing
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    pos.status = "CLOSED"
                    pos.current_price = Decimal(str(exit_price))
                    pos.profit_loss = Decimal(str(round(pnl, 2)))
                    pos.closed_at = now
                    pos.close_reason = close_reason
                    # Guard: correct opened_at if it's somehow after closed_at
                    if pos.opened_at and pos.opened_at > now:
                        logger.warning(
                            f"Position {deal_id}: DB opened_at ({pos.opened_at}) > "
                            f"closed_at ({now}), correcting"
                        )
                        pos.opened_at = now
                    await session.flush()
                    await session.refresh(pos)

                # Create CLOSE trade record
                trade = Trade(
                    position_id=pos.id,
                    deal_reference=deal_id,
                    trade_type="CLOSE",
                    epic=epic,
                    direction=direction,
                    size=Decimal(str(size)),
                    price=Decimal(str(exit_price)),
                    profit_loss=Decimal(str(round(pnl, 2))),
                    executed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                session.add(trade)
                await session.commit()
                logger.info(f"Persisted CLOSED position to DB: {deal_id} ({epic} P&L={pnl:.2f} reason={close_reason})")
        except Exception as e:
            logger.warning(f"Position close persistence failed for {deal_id}: {e}")

    async def _detect_broker_closed(self, current_positions: list[dict]) -> None:
        """
        Detect positions closed by the broker (SL/TP hit on Capital.com side).
        Compares current broker positions with previous iteration to find disappeared ones.
        Persists closures to DB, pushes WebSocket events, and logs for System Logs page.
        """
        if self.execution_engine.mode == ExecutionMode.PAPER:
            # PAPER mode: we manage all closes locally, no broker reconciliation needed
            return

        current_deals = {p.get("deal_id") for p in current_positions if p.get("deal_id")}

        # First iteration: just record positions, nothing to compare yet
        if not self._previous_positions:
            self._previous_positions = {p.get("deal_id"): p for p in current_positions if p.get("deal_id")}
            return

        # Find positions that disappeared (closed by broker)
        for deal_id, prev_pos in list(self._previous_positions.items()):
            if deal_id in current_deals:
                continue  # Still open

            epic = prev_pos.get("epic", "UNKNOWN")
            direction = prev_pos.get("direction", "BUY")
            size = prev_pos.get("size", 0)
            entry_price = prev_pos.get("level", 0)
            stop_level = prev_pos.get("stop_level")
            profit_level = prev_pos.get("profit_level")

            # Determine close reason from SL/TP levels and live broker price.
            # The broker closed this position — we query the current market price
            # to determine whether SL or TP was hit (since we don't have the exact
            # exit price from the broker activity API).
            close_reason = "EXTERNAL"
            exit_price = entry_price  # Fallback

            if stop_level and stop_level > 0 and profit_level and profit_level > 0:
                # Both SL and TP were set — get live price from broker to determine
                # which level was hit. This is far more reliable than stale candle data.
                live_price = None
                try:
                    market = await self.broker.get_market_details(epic)
                    snapshot = market.get("snapshot", {})
                    bid = snapshot.get("bid", 0)
                    offer = snapshot.get("offer", 0)
                    if bid and offer:
                        live_price = (bid + offer) / 2
                except Exception as e:
                    logger.debug(f"Could not get live price for {epic}: {e}")

                if live_price:
                    # Use live price to determine which level was crossed
                    if direction == "BUY":
                        # BUY: SL below entry, TP above entry
                        # If price is at/above TP level → TP hit
                        # If price is at/below SL level → SL hit
                        if live_price >= profit_level:
                            close_reason = "TP"
                            exit_price = profit_level
                        elif live_price <= stop_level:
                            close_reason = "SL"
                            exit_price = stop_level
                        else:
                            # Price between SL and TP — compare distance
                            dist_to_sl = abs(live_price - stop_level)
                            dist_to_tp = abs(live_price - profit_level)
                            if dist_to_tp < dist_to_sl:
                                close_reason = "TP"
                                exit_price = profit_level
                            else:
                                close_reason = "SL"
                                exit_price = stop_level
                    else:
                        # SELL: SL above entry, TP below entry
                        # If price is at/below TP level → TP hit
                        # If price is at/above SL level → SL hit
                        if live_price <= profit_level:
                            close_reason = "TP"
                            exit_price = profit_level
                        elif live_price >= stop_level:
                            close_reason = "SL"
                            exit_price = stop_level
                        else:
                            dist_to_sl = abs(live_price - stop_level)
                            dist_to_tp = abs(live_price - profit_level)
                            if dist_to_tp < dist_to_sl:
                                close_reason = "TP"
                                exit_price = profit_level
                            else:
                                close_reason = "SL"
                                exit_price = stop_level
                else:
                    # Fallback: no live price — cannot reliably determine SL vs TP.
                    # Default to EXTERNAL (unknown) rather than guessing wrong.
                    # This should rarely happen since we just queried the broker.
                    close_reason = "EXTERNAL"
                    exit_price = entry_price
                    logger.warning(
                        f"[{epic}] Cannot determine SL/TP for {deal_id} — "
                        f"no live price available, marking as EXTERNAL"
                    )
            elif stop_level and stop_level > 0:
                close_reason = "SL"
                exit_price = stop_level
            elif profit_level and profit_level > 0:
                close_reason = "TP"
                exit_price = profit_level

            # Calculate P&L using actual exit price (SL/TP level)
            if direction == "BUY":
                pnl = (exit_price - entry_price) * size
            else:
                pnl = (entry_price - exit_price) * size

            logger.warning(
                f"[{epic}] Position {deal_id} closed by broker "
                f"(reason={close_reason}, exit={exit_price:.6f}, P&L=${pnl:.2f})"
            )

            # Record in trade history for Kelly sizing + per-asset CB
            self._on_position_closed(deal_id, pnl, epic=epic)

            # Persist to database
            await self._persist_position_close(
                deal_id=deal_id, epic=epic, direction=direction,
                size=size, entry_price=entry_price, exit_price=exit_price,
                pnl=pnl, close_reason=close_reason,
                opened_at=prev_pos.get("opened_at"),
            )

            # Clean up trailing stop if tracked
            if deal_id in self.trailing_stop_manager.tracked_positions:
                self.trailing_stop_manager.unregister_position(deal_id)

            # Broadcast trade_closed event to frontend via WebSocket
            try:
                from src.api.websocket import ws_manager
                await ws_manager.broadcast("trades", {
                    "type": "trade_closed",
                    "deal_id": deal_id,
                    "epic": epic,
                    "direction": direction,
                    "pnl": round(pnl, 2),
                    "close_reason": close_reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as e:
                logger.debug(f"WS broadcast trade_closed failed: {e}")

            # Log execution close for System Logs page
            try:
                await get_trade_logger().log_execution(
                    epic=epic, direction=direction, size=size,
                    entry_price=entry_price,
                    status=ExecutionStatus.EXECUTED, deal_id=deal_id,
                    source=self._log_source,
                )
            except Exception as e:
                logger.debug(f"TradeLogger log_execution failed for broker-closed {deal_id}: {e}")

            # Fire trade-closed alert (Telegram, Email, etc.)
            if self._log_source in ("demo_trading", "live_trading"):
                try:
                    from src.monitoring.alerting.alert_manager import get_alert_manager
                    from src.utils.config import get_settings
                    if getattr(get_settings(), "alerts_enabled", False):
                        am = get_alert_manager()
                        await am.alert_trade_closed(
                            epic=epic,
                            direction=direction,
                            deal_id=deal_id,
                            exit_price=exit_price,
                            pnl=round(pnl, 2),
                            reason=close_reason,
                        )
                except Exception as alert_err:
                    logger.warning(f"Trade close alert failed: {alert_err}")

        # Update previous positions for next iteration
        self._previous_positions = {p.get("deal_id"): p for p in current_positions if p.get("deal_id")}

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
            from src.broker.models import Direction

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

        # Reset heartbeat so the 30s timeout doesn't trip on first iteration
        # (CircuitBreakerManager may have been created minutes/hours ago at startup)
        self.risk_manager.circuit_breakers.heartbeat()

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
        """Callback when the loop task finishes — auto-restart on crash."""
        if task.cancelled():
            self._running = False
            return
        exc = task.exception()
        if exc:
            logger.error(f"🚨 Paper trading loop crashed: {exc}")
            # Auto-restart after 30 seconds
            logger.info("🔄 Auto-restarting paper trading loop in 30 seconds...")
            self._running = False
            try:
                loop = asyncio.get_event_loop()
                loop.call_later(30.0, self._auto_restart)
            except RuntimeError:
                logger.error("Cannot auto-restart: no event loop available")

    def _auto_restart(self) -> None:
        """Auto-restart the trading loop after a crash."""
        if self._running:
            return  # Already running (manual restart happened)
        logger.info("🔄 Auto-restarting paper trading loop now...")
        self.start()

    async def _run_loop(self) -> None:
        """Main loop: check for new candles at fixed intervals."""
        consecutive_errors = 0
        max_consecutive_errors = 10

        # Run first iteration immediately (process all epics regardless)
        try:
            await self._run_iteration(force=True)
            consecutive_errors = 0
        except Exception as e:
            self._error_count += 1
            consecutive_errors += 1
            logger.error(f"First iteration failed: {e}")

        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                if not self._running:
                    break
                await self._run_iteration(force=False)
                consecutive_errors = 0  # Reset on success
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                self._error_count += 1
                logger.error(
                    f"Paper trading iteration error ({consecutive_errors}/{max_consecutive_errors}): {e}"
                )
                if consecutive_errors >= max_consecutive_errors:
                    logger.error(
                        f"🚨 {max_consecutive_errors} consecutive errors — "
                        f"stopping loop for auto-restart"
                    )
                    raise  # Let _on_task_done handle restart
                # Exponential backoff: 30s, 60s, 120s, ... max 5min
                backoff = min(30 * (2 ** (consecutive_errors - 1)), 300)
                logger.info(f"Waiting {backoff}s before next attempt...")
                await asyncio.sleep(backoff)

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
                # Sync dedicated min deal size cache
                min_val = info.get("dealingRules", {}).get("minDealSize", {}).get("value")
                if min_val is not None:
                    self._min_deal_size_cache[epic] = float(min_val)
            except Exception as e:
                logger.debug(f"[{epic}] Market info fetch failed: {e}")
                return True, None  # Graceful: if fetch fails, try anyway

        status = info.get("snapshot", {}).get("marketStatus", "TRADEABLE")
        if status != "TRADEABLE":
            return False, f"Mercato {epic} chiuso (status: {status})"
        return True, None

    def _get_min_deal_size(self, epic: str) -> float | None:
        """
        Get minDealSize with fallback chain:
        1. _market_info_cache (fresh data from _is_market_open each iteration)
        2. _min_deal_size_cache (seeded at startup from DB/prefetch)
        3. None (validation skipped, broker will reject if too small)
        """
        # Priority 1: Fresh data from _is_market_open() cache
        info = self._market_info_cache.get(epic)
        if info:
            dealing_rules = info.get("dealingRules", {})
            min_deal = dealing_rules.get("minDealSize", {})
            value = min_deal.get("value")
            if value is not None:
                return float(value)

        # Priority 2: Pre-fetched / DB-loaded cache
        if epic in self._min_deal_size_cache:
            return self._min_deal_size_cache[epic]

        return None

    def seed_min_deal_sizes(self, sizes: dict[str, float]) -> None:
        """Seed the min deal size cache with pre-fetched or DB-loaded data."""
        self._min_deal_size_cache.update(sizes)
        logger.info(f"Seeded min deal size cache with {len(sizes)} entries")

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

        # Detect positions closed by broker (SL/TP hit on Capital.com side)
        await self._detect_broker_closed(current_positions)

        # Phase 8: update trailing stops for open positions
        await self._update_trailing_stops(current_positions)

        # CRITICAL: Check and auto-close positions with violated stop losses
        await self._check_stop_losses(current_positions)

        open_epics = {p.get("epic") for p in current_positions}

        # Early exit: skip signal generation if already at max open positions
        max_positions = self.risk_manager.circuit_breakers.config.max_open_positions
        if len(current_positions) >= max_positions:
            logger.debug(
                f"Check #{self._check_count}: at max positions "
                f"({len(current_positions)}/{max_positions}), skipping signal generation"
            )
            return

        # Asset momentum rotation: refresh active assets weekly
        self._refresh_active_assets()

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
                # Refresh heartbeat per-epic so the 30s timeout measures
                # "loop alive" not "total iteration duration" (21 epics can exceed 30s)
                self.risk_manager.circuit_breakers.heartbeat()
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
        # Asset rotation check
        if self._active_assets is not None and epic not in self._active_assets:
            return  # Skip non-active assets

        # Per-asset circuit breaker (5 consecutive losses)
        if self._per_asset_losses.get(epic, 0) >= 5:
            logger.debug(f"[{epic}] Per-asset CB: 5 consecutive losses, skipping")
            return

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

        # Log market state with regime info (Step 7: regime detection)
        regime = market_data.get("regime", "unknown")
        adx = market_data.get("adx", 0)
        rsi = market_data.get("rsi", 0)
        logger.info(
            f"[{epic}] Market state: regime={regime}, ADX={adx:.1f}, RSI={rsi:.1f}"
        )

        # Track regime distribution
        if epic not in self._regime_counts:
            self._regime_counts[epic] = {}
        self._regime_counts[epic][regime] = self._regime_counts[epic].get(regime, 0) + 1

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

        # Map direction to SignalType for structured logging
        _dir_map = {"BUY": SignalType.LONG, "SELL": SignalType.SHORT, "HOLD": SignalType.HOLD}
        _signal_type = _dir_map.get(signal.direction.value, SignalType.HOLD)

        logger.info(
            f"[{epic}] Signal: {signal.direction.value} "
            f"@ {signal.entry_price:.2f} "
            f"(confidence={signal.confidence:.3f})"
        )

        # Record signal metric
        MetricsCollector.record_signal(
            epic=epic,
            direction=signal.direction.value,
            strategy=signal.strategy_name or "unknown",
            confidence=signal.confidence,
        )

        if signal.direction.value == "HOLD":
            signal_info["status"] = "hold"
            # Log HOLD signal
            try:
                await get_trade_logger().log_signal(
                    epic=epic, direction=_signal_type, confidence=signal.confidence,
                    strategy=signal.strategy_name or "unknown",
                    execution_status=ExecutionStatus.HOLD,
                    source=self._log_source,
                )
            except Exception:
                pass
            logger.info(f"[{epic}] HOLD signal, skipping execution")
            return

        # HIGH-7 FIX: Duplicate signal detection
        signal_key = (epic, signal.direction.value, round(signal.entry_price, 2))
        now = datetime.now(timezone.utc)

        if signal_key in self._recent_signals:
            last_time = self._recent_signals[signal_key]
            age_seconds = (now - last_time).total_seconds()

            if age_seconds < self._signal_dedup_window_seconds:
                signal_info["status"] = "duplicate"
                signal_info["rejection_reason"] = f"Duplicate signal (last seen {age_seconds:.1f}s ago)"
                logger.warning(
                    f"[{epic}] DUPLICATE signal detected: {signal.direction.value} "
                    f"@ {signal.entry_price:.2f} (last seen {age_seconds:.1f}s ago) - SKIPPING"
                )
                return

        # Record this signal
        self._recent_signals[signal_key] = now

        # Cleanup old signals (>5 minutes)
        self._recent_signals = {
            k: v for k, v in self._recent_signals.items()
            if (now - v).total_seconds() < 300
        }

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
            # Log rejected signal + risk event
            try:
                tl = get_trade_logger()
                await tl.log_signal(
                    epic=epic, direction=_signal_type, confidence=signal.confidence,
                    strategy=signal.strategy_name or "unknown",
                    execution_status=ExecutionStatus.REJECTED,
                    rejection_reason=risk_result.rejection_reason,
                    source=self._log_source,
                )
                await tl.log_risk_decision(
                    event_type=RiskEventType.POSITION_LIMIT, epic=epic,
                    description=risk_result.rejection_reason or "Risk check failed",
                    action="rejected_trade", current_equity=equity,
                    open_positions=len(open_positions),
                    source=self._log_source,
                )
            except Exception:
                pass
            return

        logger.info(
            f"[{epic}] Risk APPROVED: size={risk_result.position_size:.4f}, "
            f"SL={risk_result.stop_loss}, TP={risk_result.take_profit} "
            f"sizing={risk_result.sizing_method}"
        )

        # Step 4b: Validate against broker minDealSize (DEMO/LIVE only)
        # If size is close to minimum (>=80%), round up instead of rejecting
        min_deal_size = self._get_min_deal_size(epic)
        if min_deal_size is not None and risk_result.position_size < min_deal_size:
            if risk_result.position_size >= min_deal_size * 0.80:
                logger.info(
                    f"[{epic}] Size {risk_result.position_size:.4f} rounded up "
                    f"to min_deal_size {min_deal_size}"
                )
                risk_result.position_size = min_deal_size
            else:
                reason = (
                    f"Size calcolata ({risk_result.position_size:.4f}) inferiore "
                    f"al minimo del broker ({min_deal_size}) per {epic}"
                )
                signal_info["status"] = "rejected"
                signal_info["rejection_reason"] = reason
                signal_info["error_detail"] = {
                    "error_type": "min_size",
                    "summary": f"Size troppo piccola per {epic} (min: {min_deal_size})",
                    "details": f"Size calcolata: {risk_result.position_size:.4f}, minimo broker: {min_deal_size}",
                    "size": risk_result.position_size,
                    "min_deal_size": min_deal_size,
                    "direction": signal.direction.value,
                }
                logger.warning(f"[{epic}] MIN SIZE REJECTED: {reason}")
                try:
                    tl = get_trade_logger()
                    await tl.log_signal(
                        epic=epic, direction=_signal_type, confidence=signal.confidence,
                        strategy=signal.strategy_name or "unknown",
                        execution_status=ExecutionStatus.REJECTED,
                        rejection_reason=reason,
                        source=self._log_source,
                    )
                except Exception:
                    pass
                return

        # HIGH-8 FIX: Refresh equity immediately before execution
        # to catch any changes since risk check (manual trades, other systems, etc.)
        final_equity = await self._fetch_equity()
        if abs(final_equity - equity) > equity * 0.01:  # >1% change
            logger.warning(
                f"[{epic}] Equity changed since risk check: "
                f"{equity:.2f} -> {final_equity:.2f} "
                f"({((final_equity - equity) / equity) * 100:+.2f}%)"
            )
            self.risk_manager.update_equity(final_equity)

        # Step 5: Execute (paper mode)
        exec_start = _time.monotonic()
        exec_result = await self.execution_engine.execute_signal(signal, risk_result)
        exec_duration = _time.monotonic() - exec_start

        if exec_result.success:
            self._trade_count += 1
            signal_info["status"] = "executed"
            logger.info(
                f"[{epic}] EXECUTED: deal_id={exec_result.deal_id}, "
                f"fill={exec_result.fill_price:.2f}"
            )
            MetricsCollector.record_trade_execution(
                epic=epic,
                direction=signal.direction.value,
                outcome="success",
                duration_seconds=exec_duration,
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

            # Persist position to database
            await self._persist_position_open(
                deal_id=exec_result.deal_id or "",
                epic=epic,
                direction=signal.direction.value,
                size=risk_result.position_size,
                entry_price=exec_result.fill_price or signal.entry_price,
                stop_loss=risk_result.stop_loss,
                take_profit=risk_result.take_profit,
            )

            # Log executed signal + execution
            try:
                tl = get_trade_logger()
                await tl.log_signal(
                    epic=epic, direction=_signal_type, confidence=signal.confidence,
                    strategy=signal.strategy_name or "unknown",
                    execution_status=ExecutionStatus.EXECUTED,
                    source=self._log_source,
                )
                await tl.log_execution(
                    epic=epic, direction=signal.direction.value,
                    size=risk_result.position_size, entry_price=exec_result.fill_price or signal.entry_price,
                    status=ExecutionStatus.EXECUTED, deal_id=exec_result.deal_id,
                    stop_loss=risk_result.stop_loss, take_profit=risk_result.take_profit,
                    equity_at_entry=equity, source=self._log_source,
                )
            except Exception:
                pass
        else:
            signal_info["status"] = "exec_failed"
            signal_info["rejection_reason"] = exec_result.error
            if exec_result.error_detail:
                signal_info["error_detail"] = exec_result.error_detail
            logger.warning(f"[{epic}] Execution failed: {exec_result.error}")
            MetricsCollector.record_trade_execution(
                epic=epic,
                direction=signal.direction.value,
                outcome="failed",
                duration_seconds=exec_duration,
            )
            # Log failed execution
            try:
                tl = get_trade_logger()
                await tl.log_signal(
                    epic=epic, direction=_signal_type, confidence=signal.confidence,
                    strategy=signal.strategy_name or "unknown",
                    execution_status=ExecutionStatus.EXEC_FAILED,
                    rejection_reason=exec_result.error,
                    source=self._log_source,
                )
                await tl.log_execution(
                    epic=epic, direction=signal.direction.value,
                    size=risk_result.position_size, entry_price=signal.entry_price,
                    status=ExecutionStatus.EXEC_FAILED, error_message=exec_result.error,
                    source=self._log_source,
                )
            except Exception:
                pass

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
                        # In DEMO/LIVE mode, partial_close returns a NEW deal_id
                        # (close + reopen). Update trailing stop tracking if changed.
                        new_deal_id = result.deal_id
                        if new_deal_id and new_deal_id != deal_id:
                            state = self.trailing_stop_manager.get_state(deal_id)
                            if state:
                                self.trailing_stop_manager.unregister_position(deal_id)
                                self.trailing_stop_manager.register_position(
                                    deal_id=new_deal_id,
                                    epic=state.epic,
                                    direction=state.direction,
                                    entry_price=state.entry_price,
                                    stop_loss=state.current_stop,
                                    atr=None,
                                )
                                logger.info(
                                    f"[{epic}] Trailing stop migrated: "
                                    f"{deal_id} -> {new_deal_id}"
                                )
                except Exception as e:
                    logger.warning(f"[{epic}] TP1 partial close failed: {e}")

    async def _check_stop_losses(self, current_positions: list[dict]) -> None:
        """
        CRITICAL: Check if any open position has violated its stop loss OR take profit.
        Auto-close positions where:
          - SL violated: price <= SL (longs) or price >= SL (shorts)
          - TP hit: price >= TP (longs) or price <= TP (shorts)

        This is essential for locally-managed risk when broker doesn't have SL/TP set.
        """
        if not current_positions:
            return

        for position in current_positions:
            deal_id = position.get("deal_id")
            epic = position.get("epic", "")
            direction = position.get("direction", "")
            stop_level = position.get("stop_level")
            profit_level = position.get("profit_level")

            # Skip if no stop loss AND no take profit set
            if (stop_level is None or stop_level <= 0) and (profit_level is None or profit_level <= 0):
                continue

            # Get current market price
            try:
                latest = self.data_access.get_latest_price(epic, timeframe="1h")
                if latest is None:
                    continue

                current_price = latest.get("close", 0)
                if current_price <= 0:
                    continue

                # Check if stop loss violated
                stop_violated = False
                if stop_level is not None and stop_level > 0:
                    if direction == "BUY" and current_price <= stop_level:
                        stop_violated = True
                        logger.warning(
                            f"🚨 [{epic}] STOP LOSS VIOLATED! "
                            f"Price {current_price:.5f} <= SL {stop_level:.5f} (LONG)"
                        )
                    elif direction == "SELL" and current_price >= stop_level:
                        stop_violated = True
                        logger.warning(
                            f"🚨 [{epic}] STOP LOSS VIOLATED! "
                            f"Price {current_price:.5f} >= SL {stop_level:.5f} (SHORT)"
                        )

                # Check if take profit hit
                tp_hit = False
                if not stop_violated and profit_level is not None and profit_level > 0:
                    if direction == "BUY" and current_price >= profit_level:
                        tp_hit = True
                        logger.info(
                            f"🎯 [{epic}] TAKE PROFIT HIT! "
                            f"Price {current_price:.5f} >= TP {profit_level:.5f} (LONG)"
                        )
                    elif direction == "SELL" and current_price <= profit_level:
                        tp_hit = True
                        logger.info(
                            f"🎯 [{epic}] TAKE PROFIT HIT! "
                            f"Price {current_price:.5f} <= TP {profit_level:.5f} (SHORT)"
                        )

                # Auto-close position if SL violated or TP hit
                if stop_violated or tp_hit:
                    close_reason = "STOP_LOSS_HIT" if stop_violated else "TAKE_PROFIT_HIT"
                    reason_label = "SL" if stop_violated else "TP"
                    try:
                        logger.info(f"[{epic}] Auto-closing position {deal_id} due to {close_reason}")

                        result = await self.execution_engine.close_position(
                            deal_id=deal_id,
                            reason=close_reason,
                        )

                        if result.success:
                            entry_price = position.get("level") or position.get("entry_price", 0)
                            size = position.get("size", 0)
                            if direction == "BUY":
                                pnl = (current_price - entry_price) * size
                            else:
                                pnl = (entry_price - current_price) * size
                            logger.info(
                                f"✅ [{epic}] Position closed at {reason_label}: "
                                f"P&L = ${pnl:.2f}"
                            )

                            self._on_position_closed(deal_id, pnl, epic=epic)

                            # Persist closed position to database
                            await self._persist_position_close(
                                deal_id=deal_id,
                                epic=epic,
                                direction=direction,
                                size=size,
                                entry_price=entry_price,
                                exit_price=current_price,
                                pnl=pnl,
                                close_reason=close_reason,
                                opened_at=position.get("opened_at"),
                            )

                            # Broadcast trade_closed event to frontend via WebSocket
                            try:
                                from src.api.websocket import ws_manager
                                await ws_manager.broadcast("trades", {
                                    "type": "trade_closed",
                                    "deal_id": deal_id,
                                    "epic": epic,
                                    "direction": direction,
                                    "pnl": round(pnl, 2),
                                    "close_reason": close_reason,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                            except Exception as e:
                                logger.debug(f"WS broadcast trade_closed failed: {e}")

                            # Log execution close for System Logs page
                            try:
                                await get_trade_logger().log_execution(
                                    epic=epic, direction=direction, size=size,
                                    entry_price=entry_price,
                                    status=ExecutionStatus.EXECUTED, deal_id=deal_id,
                                    source=self._log_source,
                                )
                            except Exception as e:
                                logger.debug(f"TradeLogger log_execution failed for {deal_id}: {e}")

                            status = "sl_hit" if stop_violated else "tp_hit"
                            self._signal_history.append({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "epic": epic,
                                "direction": direction,
                                "confidence": 0.0,
                                "status": status,
                                "reason": f"{reason_label} hit at {current_price:.5f}",
                                "deal_id": deal_id,
                                "pnl": pnl,
                            })
                        else:
                            logger.error(
                                f"❌ [{epic}] Failed to close position at {reason_label}: {result.error}"
                            )

                    except Exception as e:
                        logger.error(f"❌ [{epic}] Error closing position at {reason_label}: {e}")

            except Exception as e:
                logger.debug(f"[{epic}] Risk level check failed: {e}")

    def _on_position_closed(self, deal_id: str, pnl: float, epic: str = "") -> None:
        """
        Handle position close events for Phase 8 modules.
        Records trade result for circuit breakers, equity curve, Kelly history,
        and per-asset circuit breaker.
        """
        # Circuit breaker: track consecutive wins/losses
        self.risk_manager.circuit_breakers.record_trade_result(is_win=(pnl > 0))

        # Equity curve filter: record equity point
        equity = self.risk_manager.drawdown_monitor.state.current_equity
        self.risk_manager.equity_curve_filter.record_trade_close(equity)

        # Kelly: add to trade history (deque auto-discards oldest when maxlen=200 reached)
        self._trade_history.append({"pnl": pnl})

        # Per-asset circuit breaker: track consecutive losses
        if epic:
            self._record_per_asset_result(epic, is_win=(pnl > 0))

        # Trailing stop: unregister
        self.trailing_stop_manager.unregister_position(deal_id)

        # Phase 14: persist risk state after position close (skip if no event loop)
        try:
            asyncio.create_task(self._persist_risk_state())
        except RuntimeError:
            pass  # No event loop (called from tests)

        logger.debug(
            f"Position closed: deal={deal_id} epic={epic} pnl={pnl:.2f} "
            f"(history={len(self._trade_history)} trades)"
        )

    def _refresh_active_assets(self) -> None:
        """Refresh asset rotation weekly."""
        import time
        now = time.monotonic()
        if self._active_assets is not None and (now - self._asset_rotation_ts) < 7 * 24 * 3600:
            return  # Refresh weekly

        try:
            from src.trading.asset_rotation import compute_momentum_scores, select_active_assets
            from src.data.storage import ParquetStorageManager
            from src.data.data_access import DataAccessLayer

            storage = ParquetStorageManager()
            data_access = DataAccessLayer(storage=storage)
            scores = compute_momentum_scores(data_access)

            if scores:
                selected = select_active_assets(scores)
                self._active_assets = set(selected)
                self._asset_rotation_ts = now
                logger.info(f"Asset rotation: {len(selected)} active assets: {selected}")
            else:
                self._active_assets = None  # Fallback to all
        except Exception as e:
            logger.warning(f"Asset rotation failed: {e}")
            self._active_assets = None

    def _record_per_asset_result(self, epic: str, is_win: bool) -> None:
        """Track consecutive losses per asset for per-asset circuit breaker."""
        if is_win:
            self._per_asset_losses[epic] = 0
        else:
            self._per_asset_losses[epic] = self._per_asset_losses.get(epic, 0) + 1

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
            "kelly_stats": self._get_kelly_stats(),
            "regime_distribution": dict(self._regime_counts),
            "min_deal_sizes_cached": len(self._min_deal_size_cache),
            "active_assets": len(self._active_assets) if self._active_assets else len(self.epics),
            "per_asset_losses": {k: v for k, v in self._per_asset_losses.items() if v > 0},
        }

    def _get_kelly_stats(self) -> dict | None:
        """Compute Kelly stats for API response."""
        history = list(self._trade_history)
        if not history:
            return None
        if self.risk_manager.kelly_sizer is None:
            return None
        wins = [t["pnl"] for t in history if t["pnl"] > 0]
        losses = [t["pnl"] for t in history if t["pnl"] < 0]
        min_trades = self.risk_manager.kelly_sizer.min_trades
        stats = self.risk_manager.kelly_sizer.compute_stats(history)
        result: dict = {
            "total_trades": len(history),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": len(wins) / max(1, len(wins) + len(losses)),
            "total_pnl": round(sum(t["pnl"] for t in history), 2),
            "min_required": min_trades,
            "active": stats is not None,
            "method": "kelly" if stats else "fixed_fractional",
        }
        if stats:
            result["avg_win"] = round(stats.avg_win, 2)
            result["avg_loss"] = round(stats.avg_loss, 2)
            result["kelly_fraction"] = round(stats.kelly_fraction, 4)
            result["half_kelly"] = round(stats.half_kelly, 4)
        return result

    async def get_status_async(self) -> dict:
        """Get status with live position data (async, works for all modes)."""
        status = self.get_status()
        positions = await self.get_positions_async()
        status["open_positions"] = len(positions)
        status["total_unrealized_pnl"] = sum(
            p.get("unrealized_pnl", 0) for p in positions
        )
        return status
