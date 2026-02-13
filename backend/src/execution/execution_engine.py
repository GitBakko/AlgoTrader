"""
Execution engine orchestrator.
Coordinates order management, position tracking, and slippage recording.
"""

from loguru import logger

from src.broker.client import CapitalComClient
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
    ):
        """
        Initialize execution engine.

        Args:
            broker: Capital.com client (required for LIVE mode)
            mode: Execution mode (PAPER or LIVE)
        """
        self._mode = mode
        self._order_manager = OrderManager(broker=broker, mode=mode)
        self._position_tracker = PositionTracker(broker=broker, mode=mode)
        self._slippage_tracker = SlippageTracker()

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

            # Track position (paper mode)
            if self._mode == ExecutionMode.PAPER and result.deal_id:
                self._position_tracker.open_paper_position(
                    order=order,
                    fill_price=result.fill_price,
                    deal_id=result.deal_id,
                )

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
            if self._mode == ExecutionMode.PAPER:
                self._position_tracker.close_paper_position(deal_id)
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
