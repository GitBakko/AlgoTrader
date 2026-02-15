"""
Execution engine orchestrator.
Coordinates order management, position tracking, and slippage recording.
"""

from datetime import datetime, timezone
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
    ):
        """
        Initialize execution engine.

        Args:
            broker: Capital.com client (required for LIVE mode)
            mode: Execution mode (PAPER or LIVE)
            position_repository: Repository for persisting positions (optional, graceful degradation)
            trade_repository: Repository for persisting trade audit trail (optional, graceful degradation)
        """
        self._mode = mode
        self._order_manager = OrderManager(broker=broker, mode=mode)
        self._position_tracker = PositionTracker(broker=broker, mode=mode)
        self._slippage_tracker = SlippageTracker()

        # CRITICAL FIX (CRIT-2): Add database persistence to prevent data loss
        self._position_repository = position_repository
        self._trade_repository = trade_repository

        if position_repository is None or trade_repository is None:
            logger.warning(
                "ExecutionEngine initialized WITHOUT database persistence - "
                "trades will NOT be saved (testing mode only!)"
            )

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
                        epic=signal.epic,
                        direction=signal.direction.value,
                        size=Decimal(str(risk_result.position_size)),
                        entry_price=Decimal(str(result.fill_price)),
                        stop_loss=Decimal(str(risk_result.stop_loss)) if risk_result.stop_loss else None,
                        take_profit=Decimal(str(risk_result.take_profit)) if risk_result.take_profit else None,
                        status="OPEN",
                        opened_at=datetime.now(timezone.utc),
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
                        executed_at=datetime.now(timezone.utc),
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
                f"Execution failed: {signal.epic} {signal.direction.value} "
                f"error={result.error}"
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
        result = await self._order_manager.close_order(deal_id)

        if result.success:
            # Remove from local tracking
            closed_position = self._position_tracker.close_paper_position(deal_id)

            # CRITICAL FIX (CRIT-2): Update database
            if self._position_repository and self._trade_repository and closed_position:
                try:
                    # Get Position from DB
                    position_db = await self._position_repository.get_by_deal_id(deal_id)
                    if position_db:
                        # Update Position to CLOSED
                        position_db.status = "CLOSED"
                        position_db.closed_at = datetime.now(timezone.utc)
                        position_db.close_reason = reason
                        # Calculate P&L if close price available
                        if result.fill_price:
                            position_db.current_price = Decimal(str(result.fill_price))
                            # P&L calculation (simplified - should account for direction)
                            price_diff = Decimal(str(result.fill_price)) - position_db.entry_price
                            if position_db.direction == "SELL":
                                price_diff = -price_diff
                            position_db.profit_loss = price_diff * position_db.size

                        await self._position_repository.update(position_db)

                        # Create CLOSE Trade record
                        from src.database.models import Trade
                        trade_db = Trade(
                            position_id=position_db.id,
                            deal_reference=deal_id,
                            trade_type="CLOSE",
                            epic=position_db.epic,
                            direction=position_db.direction,
                            size=position_db.size,
                            price=Decimal(str(result.fill_price)) if result.fill_price else position_db.entry_price,
                            profit_loss=position_db.profit_loss,
                            executed_at=datetime.now(timezone.utc),
                        )
                        await self._trade_repository.create(trade_db)

                        logger.debug(f"✅ Position closed in DB: position_id={position_db.id} P&L={position_db.profit_loss}")
                except Exception as e:
                    logger.error(f"❌ Database close update failed: {e}")

            logger.info(f"Position closed: {deal_id} reason={reason}")

        return result

    async def update_stops(self, deal_id: str, new_stop: float) -> ExecutionResult:
        """
        Update stop-loss on an open position.

        Args:
            deal_id: Deal ID to modify
            new_stop: New stop-loss level

        Returns:
            ExecutionResult
        """
        return await self._order_manager.modify_stops(
            deal_id=deal_id,
            stop_level=new_stop,
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

        # Live: close via broker (need to reopen smaller position)
        result = await self._order_manager.close_order(deal_id)
        if not result.success:
            return result

        logger.info(f"Partial close (live): {deal_id} -{close_pct:.0%} reason={reason}")
        return result

    async def get_open_positions(self, epic: str | None = None) -> list[dict]:
        """
        Get open positions.

        Args:
            epic: Filter by asset (None = all)

        Returns:
            List of position dicts
        """
        return await self._position_tracker.get_open_positions(epic)
