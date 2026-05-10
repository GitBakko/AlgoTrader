"""
Execution engine orchestrator.
Coordinates order management, position tracking, and slippage recording.
"""

from datetime import UTC, datetime
from decimal import Decimal

from loguru import logger

from src.broker.client import CapitalComClient
from src.database.repositories.position_repository import PositionRepository
from src.database.repositories.trade_repository import TradeRepository
from src.execution.order_manager import OrderManager
from src.execution.position_tracker import PositionTracker
from src.execution.schemas import ExecutionMode, ExecutionOrder, ExecutionResult
from src.execution.slippage_tracker import SlippageTracker
from src.risk.schemas import RiskCheckResult
from src.strategy.schemas import TradingSignal


class ExecutionEngine:
    """
    Orchestrates the full execution pipeline:
    signal + risk result -> order -> fill -> position tracking.
    """

    def __init__(
        self,
        broker: CapitalComClient | None = None,
        mode: ExecutionMode = ExecutionMode.PAPER,
        position_repository: PositionRepository | None = None,
        trade_repository: TradeRepository | None = None,
        db_session_factory=None,
    ):
        """
        Initialize execution engine.

        Args:
            broker: Capital.com client (required for LIVE mode)
            mode: Execution mode (PAPER or LIVE)
            position_repository: Repository for persisting positions (optional, graceful degradation)
            trade_repository: Repository for persisting trade audit trail (optional, graceful degradation)
            db_session_factory: Async session factory for on-demand DB access (preferred over injected repos)
        """
        self._mode = mode
        self._position_tracker = PositionTracker(broker=broker, mode=mode)
        self._order_manager = OrderManager(
            broker=broker, mode=mode, position_tracker=self._position_tracker
        )
        self._slippage_tracker = SlippageTracker()

        # Database persistence: prefer session factory (creates own sessions per-operation)
        self._position_repository = position_repository
        self._trade_repository = trade_repository
        self._db_session_factory = db_session_factory

        has_db = (
            position_repository is not None and trade_repository is not None
        ) or db_session_factory is not None
        if not has_db:
            logger.warning(
                "ExecutionEngine initialized WITHOUT database persistence - "
                "trades will NOT be saved (testing mode only!)"
            )
        elif db_session_factory is not None:
            logger.info("ExecutionEngine initialized with session factory for DB persistence")

    @property
    def mode(self) -> ExecutionMode:
        return self._mode

    @property
    def slippage_tracker(self) -> SlippageTracker:
        return self._slippage_tracker

    async def execute_signal(
        self,
        signal: TradingSignal,
        risk_result: RiskCheckResult,
    ) -> ExecutionResult:
        """
        Execute a trading signal that has passed risk checks.

        Args:
            signal: Trading signal with direction and price
            risk_result: Approved risk check result with size and levels

        Returns:
            ExecutionResult with fill details
        """
        # Build execution order from signal + risk result
        order = ExecutionOrder(
            epic=signal.epic,
            direction=signal.direction.value,
            size=risk_result.position_size,
            entry_price=signal.entry_price,
            stop_loss=risk_result.stop_loss,
            take_profit=risk_result.take_profit,
        )

        # Submit order
        result = await self._order_manager.submit_order(order)

        if result.success and result.fill_price is not None:
            # Record slippage
            self._slippage_tracker.record_slippage(
                epic=signal.epic,
                expected_price=signal.entry_price,
                actual_price=result.fill_price,
                direction=signal.direction.value,
            )

            # Track position locally (all modes - needed for trailing stops, etc.)
            if result.deal_id:
                self._position_tracker.open_paper_position(
                    order=order,
                    fill_price=result.fill_price,
                    deal_id=result.deal_id,
                )

            # CRITICAL FIX (CRIT-2): Persist to database to prevent data loss on restart
            if self._position_repository and self._trade_repository and result.deal_id:
                try:
                    # Create Position record
                    from src.database.models import Position

                    position_db = Position(
                        deal_id=result.deal_id,
                        deal_reference=result.deal_reference,
                        epic=signal.epic,
                        direction=signal.direction.value,
                        size=Decimal(str(risk_result.position_size)),
                        entry_price=Decimal(str(result.fill_price)),
                        stop_loss=(
                            Decimal(str(risk_result.stop_loss)) if risk_result.stop_loss else None
                        ),
                        take_profit=(
                            Decimal(str(risk_result.take_profit))
                            if risk_result.take_profit
                            else None
                        ),
                        status="OPEN",
                        opened_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                    position_db = await self._position_repository.create(position_db)

                    # Create Trade audit record
                    from src.database.models import Trade

                    trade_db = Trade(
                        position_id=position_db.id,
                        deal_reference=result.deal_id,
                        trade_type="OPEN",
                        epic=signal.epic,
                        direction=signal.direction.value,
                        size=Decimal(str(risk_result.position_size)),
                        price=Decimal(str(result.fill_price)),
                        executed_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                    await self._trade_repository.create(trade_db)

                    logger.debug(f"✅ Persisted to DB: position_id={position_db.id}")
                except Exception as e:
                    logger.error(f"❌ Database persistence failed: {e} (trade still executed!)")

            logger.info(
                f"Executed: {signal.epic} {signal.direction.value} "
                f"size={risk_result.position_size:.4f} @ {result.fill_price:.2f} "
                f"deal={result.deal_id}"
            )
        else:
            logger.warning(
                f"Execution failed: {signal.epic} {signal.direction.value} " f"error={result.error}"
            )

        return result

    async def close_position(self, deal_id: str, reason: str = "MANUAL") -> ExecutionResult:
        """
        Close an open position.

        Args:
            deal_id: Deal ID to close
            reason: Close reason (SL, TP, MANUAL, SIGNAL)

        Returns:
            ExecutionResult
        """
        # Snapshot position info BEFORE closing (broker API won't have it after)
        pre_close_position = await self._position_tracker.get_position(deal_id)

        result = await self._order_manager.close_order(deal_id)

        if result.success:
            # Remove from local tracking
            closed_position = self._position_tracker.close_paper_position(deal_id)

            # Resolve position info: prefer local tracking, fallback to pre-close snapshot
            epic = "UNKNOWN"
            direction = "UNKNOWN"
            pnl = 0.0
            size = 0.0
            entry_price = 0.0

            # Try local tracking first, then pre-close broker snapshot
            pos_info = closed_position or pre_close_position
            if pos_info:
                epic = pos_info.get("epic", "UNKNOWN")
                direction = pos_info.get("direction", "UNKNOWN")
                entry_price = pos_info.get("level") or pos_info.get("entry_price", 0)
                size = pos_info.get("size", 0)

            # Close-detection v2 (Step 7): NO arithmetic (fill-entry)*size
            # fallback here. Authoritative P&L comes from the broker TRADE
            # row reconciled by CloseDetector (paper_loop._detect_broker_closed
            # → _finalize_close) on a subsequent tick. The `pnl` value below
            # is only a best-effort read from the DB for the immediate log /
            # broadcast; it stays 0.0 if the DB path cannot supply one.
            db_result = await self._persist_close_to_db(
                deal_id, reason, result.fill_price, epic, direction, size, entry_price
            )
            if db_result:
                epic, direction, pnl = db_result

            # Broadcast trade_closed event to frontend via WebSocket
            try:
                from src.api.websocket import ws_manager

                await ws_manager.broadcast(
                    "trades",
                    {
                        "type": "trade_closed",
                        "deal_id": deal_id,
                        "epic": epic,
                        "direction": direction,
                        "pnl": round(pnl, 2),
                        "close_reason": reason,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            except Exception as e:
                logger.debug(f"WS broadcast trade_closed failed: {e}")

            logger.info(f"Position closed: {deal_id} epic={epic} pnl={pnl:.2f} reason={reason}")

        return result

    async def _persist_close_to_db(
        self,
        deal_id: str,
        reason: str,
        fill_price: float | None,
        epic: str,
        direction: str,
        size: float = 0,
        entry_price: float = 0,
    ) -> tuple[str, str, float] | None:
        """
        Persist position close to DB. Returns (epic, direction, pnl) from DB if found.
        If position was never saved (e.g. opened before timezone fix), creates it as CLOSED.
        Uses session factory (preferred) or injected repos.
        """
        # Normalize close reason
        reason_map = {
            "STOP_LOSS_HIT": "SL",
            "TAKE_PROFIT_HIT": "TP",
            "TP1_HIT": "TP",
            "API close request": "MANUAL",
            "Graceful shutdown": "MANUAL",
        }
        db_reason = reason_map.get(reason, reason)

        # Try session factory first (DEMO/LIVE mode)
        if self._db_session_factory is not None:
            try:
                from src.database.models import Position, Trade

                now = datetime.now(UTC).replace(tzinfo=None)

                async with self._db_session_factory() as session:
                    repo = PositionRepository(session)
                    position_db = await repo.get_by_deal_id(deal_id)

                    # Fallback: Capital.com rotates the dealId (last hex
                    # nibble +1) between order-confirmation and /positions
                    # / close events. When the close-side dealId does not
                    # match any row, look up the still-OPEN row by the
                    # stable triple (epic, direction, entry_price ± 0.1%).
                    # Without this, the original OPEN row stays OPEN
                    # forever → false UNRECONCILED orphan on next restart.
                    if position_db is None and epic != "UNKNOWN" and entry_price:
                        matched = await repo.find_open_by_epic_direction_entry(
                            epic=epic,
                            direction=direction,
                            entry_price=float(entry_price),
                        )
                        if matched is not None:
                            logger.info(
                                f"[{epic}] Close dealId {deal_id} not in DB — "
                                f"matched open row {matched.deal_id} by "
                                f"(epic, direction, entry_price) fallback "
                                f"(broker dealId rotation)"
                            )
                            matched.deal_id = deal_id
                            position_db = matched

                    if position_db:
                        # Update existing position to CLOSED. Invariant #2:
                        # NO arithmetic (fill-entry)*size fallback. P&L is
                        # broker-authoritative — CloseDetector reconciles
                        # from the TRADE row on the next reconciler tick.
                        position_db.status = "CLOSED"
                        position_db.closed_at = now
                        position_db.close_reason = db_reason
                        if fill_price:
                            position_db.current_price = Decimal(str(fill_price))
                        # profit_loss left untouched here — None if absent.
                        await session.flush()
                    elif epic != "UNKNOWN" and size > 0:
                        # Position was never persisted at open — create it
                        # CLOSED with profit_loss=NULL. CloseDetector will
                        # backfill P&L from broker TRADE row on next tick.
                        position_db = Position(
                            deal_id=deal_id,
                            deal_reference=None,
                            epic=epic,
                            direction=direction,
                            size=Decimal(str(size)),
                            entry_price=Decimal(str(entry_price)),
                            current_price=Decimal(str(fill_price)) if fill_price else None,
                            profit_loss=None,
                            status="CLOSED",
                            opened_at=now,
                            closed_at=now,
                            close_reason=db_reason,
                        )
                        position_db = await repo.create(position_db)
                        logger.info(
                            f"Created CLOSED position in DB (never persisted at open): {deal_id} {epic}"
                        )
                    else:
                        logger.warning(
                            f"Position {deal_id} not found in DB and insufficient info to create"
                        )
                        return None

                    # Idempotent CLOSE Trade row (Invariant #10): SELECT-then-
                    # INSERT on (position_id, trade_type='CLOSE'). First writer
                    # wins. Prevents duplicate audit rows when reconciler tick
                    # also calls _finalize_close for the same deal.
                    from sqlalchemy import select as _select
                    existing_close = await session.execute(
                        _select(Trade)
                        .where(Trade.position_id == position_db.id)
                        .where(Trade.trade_type == "CLOSE")
                        .limit(1)
                    )
                    if existing_close.scalar_one_or_none() is None:
                        trade_db = Trade(
                            position_id=position_db.id,
                            deal_reference=deal_id,
                            trade_type="CLOSE",
                            epic=position_db.epic,
                            direction=position_db.direction,
                            size=position_db.size,
                            price=Decimal(str(fill_price)) if fill_price else position_db.entry_price,
                            profit_loss=position_db.profit_loss,
                            executed_at=now,
                        )
                        session.add(trade_db)
                    await session.commit()

                    logger.debug(f"Position closed in DB: {deal_id} P&L={position_db.profit_loss}")
                    return (
                        position_db.epic,
                        position_db.direction,
                        float(position_db.profit_loss or 0),
                    )
            except Exception as e:
                logger.error(f"Database close (session factory) failed: {e}")
            return None

        # Fallback: injected repos (PAPER mode or tests). Invariant #2:
        # NO arithmetic P&L fallback. Invariant #10: SELECT-then-INSERT
        # idempotency on CLOSE trade row.
        if self._position_repository and self._trade_repository:
            try:
                position_db = await self._position_repository.get_by_deal_id(deal_id)
                if position_db:
                    now_naive = datetime.now(UTC).replace(tzinfo=None)
                    position_db.status = "CLOSED"
                    position_db.closed_at = now_naive
                    position_db.close_reason = db_reason
                    if fill_price:
                        position_db.current_price = Decimal(str(fill_price))
                    # profit_loss left untouched — broker-authoritative.

                    # BaseRepository.update has signature (id, values).
                    # Pass the mutated fields explicitly so the repo issues
                    # an UPDATE row even when called against a real session
                    # (no auto-flush from in-place mutation across boundary).
                    update_values: dict = {
                        "status": "CLOSED",
                        "closed_at": now_naive,
                        "close_reason": db_reason,
                    }
                    if fill_price:
                        update_values["current_price"] = Decimal(str(fill_price))
                    try:
                        await self._position_repository.update(
                            position_db.id, update_values
                        )
                    except TypeError:
                        # Older mocks / repos with single-arg signature —
                        # accept silently to keep test compatibility.
                        await self._position_repository.update(position_db)

                    from src.database.models import Trade

                    # Idempotent CLOSE Trade row guard via attribute probe.
                    existing_close = None
                    finder = getattr(
                        self._trade_repository, "find_close_for_position", None
                    )
                    if finder is not None:
                        try:
                            existing_close = await finder(position_db.id)
                        except Exception:
                            existing_close = None

                    if existing_close is None:
                        trade_db = Trade(
                            position_id=position_db.id,
                            deal_reference=deal_id,
                            trade_type="CLOSE",
                            epic=position_db.epic,
                            direction=position_db.direction,
                            size=position_db.size,
                            price=Decimal(str(fill_price)) if fill_price else position_db.entry_price,
                            profit_loss=position_db.profit_loss,
                            executed_at=now_naive,
                        )
                        await self._trade_repository.create(trade_db)

                    logger.debug(f"Position closed in DB: {deal_id} P&L={position_db.profit_loss}")
                    return (
                        position_db.epic,
                        position_db.direction,
                        float(position_db.profit_loss or 0),
                    )
            except Exception as e:
                logger.error(f"Database close update failed: {e}")

        return None

    async def update_stops(
        self,
        deal_id: str,
        new_stop: float | None = None,
        stop_level: float | None = None,
        profit_level: float | None = None,
    ) -> ExecutionResult:
        """
        Update stop-loss and/or take-profit on an open position.

        Args:
            deal_id: Deal ID to modify
            new_stop: Legacy alias for stop_level (kept for backward compat)
            stop_level: New stop-loss level
            profit_level: New take-profit level

        Returns:
            ExecutionResult
        """
        # Support both old (new_stop) and new (stop_level) call sites
        sl = stop_level if stop_level is not None else new_stop
        return await self._order_manager.modify_stops(
            deal_id=deal_id,
            stop_level=sl,
            profit_level=profit_level,
        )

    async def partial_close(
        self,
        deal_id: str,
        close_pct: float,
        reason: str = "TP1_PARTIAL",
    ) -> ExecutionResult:
        """
        Partially close a position (reduce size by close_pct).

        Args:
            deal_id: Deal ID to partially close
            close_pct: Fraction to close (0.0 to 1.0)
            reason: Close reason

        Returns:
            ExecutionResult
        """
        if close_pct <= 0.0 or close_pct > 1.0:
            return ExecutionResult(
                success=False,
                deal_id=deal_id,
                error=f"Invalid close_pct: {close_pct}",
            )

        if close_pct >= 1.0:
            return await self.close_position(deal_id, reason=reason)

        if self._mode == ExecutionMode.PAPER:
            position = self._position_tracker.reduce_paper_position(deal_id, close_pct)
            if position is None:
                return ExecutionResult(
                    success=False,
                    deal_id=deal_id,
                    error=f"Position not found: {deal_id}",
                )
            logger.info(
                f"Partial close: {deal_id} -{close_pct:.0%} "
                f"remaining={position['size']:.4f} reason={reason}"
            )
            return ExecutionResult(
                success=True,
                deal_id=deal_id,
                fill_price=position.get("level"),
            )

        # DEMO/LIVE: Capital.com has no partial-close API.
        # Strategy: close full position, reopen with remaining size.

        # Step 1: Read position details before closing
        position = await self._position_tracker.get_position(deal_id)
        if position is None:
            return ExecutionResult(
                success=False,
                deal_id=deal_id,
                error=f"Position not found for partial close: {deal_id}",
            )

        original_size = position.get("size", 0)
        remaining_size = round(original_size * (1.0 - close_pct), 6)
        direction = position.get("direction", "BUY")
        epic = position.get("epic", "")
        stop_level = position.get("stop_level")
        profit_level = position.get("profit_level")
        entry_price = position.get("level", 0.0)

        # Step 2: Close full position via broker
        close_result = await self._order_manager.close_order(deal_id)
        if not close_result.success:
            return close_result

        # Remove old position from local tracker
        self._position_tracker.close_paper_position(deal_id)

        # Step 3: Reopen with remaining size
        reopen_order = ExecutionOrder(
            epic=epic,
            direction=direction,
            size=remaining_size,
            entry_price=close_result.fill_price or entry_price,
            stop_loss=stop_level,
            take_profit=profit_level,
        )
        reopen_result = await self._order_manager.submit_order(reopen_order)

        if reopen_result.success and reopen_result.deal_id:
            # Register new position in local tracker
            self._position_tracker.open_paper_position(
                order=reopen_order,
                fill_price=reopen_result.fill_price or entry_price,
                deal_id=reopen_result.deal_id,
            )
            logger.info(
                f"Partial close (DEMO): closed {deal_id} -{close_pct:.0%}, "
                f"reopened as {reopen_result.deal_id} size={remaining_size:.4f} "
                f"reason={reason}"
            )
            # Return new deal_id so caller can update trailing stop tracking
            return ExecutionResult(
                success=True,
                deal_id=reopen_result.deal_id,
                fill_price=reopen_result.fill_price,
            )

        # Position was closed but reopen failed — report with error note
        logger.error(
            f"Partial close (DEMO): closed {deal_id} but failed to reopen "
            f"remaining {remaining_size:.4f}: {reopen_result.error}"
        )
        return ExecutionResult(
            success=True,
            deal_id=deal_id,
            fill_price=close_result.fill_price,
            error=f"Reopen of remaining {remaining_size:.4f} failed: {reopen_result.error}",
        )

    async def get_open_positions(self, epic: str | None = None) -> list[dict]:
        """
        Get open positions.

        Args:
            epic: Filter by asset (None = all)

        Returns:
            List of position dicts
        """
        return await self._position_tracker.get_open_positions(epic)
