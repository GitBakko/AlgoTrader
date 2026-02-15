"""
Order management: creates, closes, and modifies orders via broker or paper trading.
"""

import asyncio
import time
from uuid import uuid4

from loguru import logger

from src.broker.client import CapitalComClient
from src.broker.exceptions import (
    CapitalComError,
    InsufficientFundsError,
    MarketClosedError,
    OrderRejectedError,
    RateLimitError,
)
from src.utils.broker_error_parser import parse_broker_error
from src.broker.models import CreatePositionRequest, Direction, ModifyPositionRequest
from src.execution.schemas import ExecutionMode, ExecutionOrder, ExecutionResult


class OrderManager:
    """Manages order submission, closing, and modification."""

    def __init__(
        self,
        broker: CapitalComClient | None = None,
        mode: ExecutionMode = ExecutionMode.PAPER,
    ):
        """
        Initialize order manager.

        Args:
            broker: Capital.com client (required for LIVE mode)
            mode: Execution mode (PAPER or LIVE)
        """
        self._broker = broker
        self._mode = mode

        if mode in (ExecutionMode.DEMO, ExecutionMode.LIVE) and broker is None:
            raise ValueError("Broker client is required for DEMO/LIVE execution mode")

    @property
    def mode(self) -> ExecutionMode:
        return self._mode

    async def submit_order(self, order: ExecutionOrder) -> ExecutionResult:
        """
        Submit an order for execution.

        Args:
            order: Order to execute

        Returns:
            ExecutionResult with fill details
        """
        start = time.monotonic()

        if self._mode == ExecutionMode.PAPER:
            result = self._paper_fill(order)
        else:
            result = await self._live_fill(order)

        result.execution_time_ms = (time.monotonic() - start) * 1000
        return result

    async def close_order(self, deal_id: str) -> ExecutionResult:
        """
        Close an open position.

        Args:
            deal_id: Deal ID to close

        Returns:
            ExecutionResult
        """
        start = time.monotonic()

        if self._mode == ExecutionMode.PAPER:
            result = ExecutionResult(
                success=True,
                deal_id=deal_id,
            )
        else:
            result = await self._live_close(deal_id)

        result.execution_time_ms = (time.monotonic() - start) * 1000
        return result

    async def modify_stops(
        self,
        deal_id: str,
        stop_level: float | None = None,
        profit_level: float | None = None,
    ) -> ExecutionResult:
        """
        Modify stop-loss and/or take-profit of an open position.

        Args:
            deal_id: Deal ID to modify
            stop_level: New stop-loss level
            profit_level: New take-profit level

        Returns:
            ExecutionResult
        """
        if self._mode == ExecutionMode.PAPER:
            return ExecutionResult(success=True, deal_id=deal_id)

        try:
            request = ModifyPositionRequest(
                stop_level=stop_level,
                profit_level=profit_level,
            )

            # CRITICAL FIX (CRIT-6): Add 10-second timeout to prevent infinite hang
            try:
                await asyncio.wait_for(
                    self._broker.modify_position(deal_id, request),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error(f"Broker API timeout (10s) modifying position {deal_id}")
                return ExecutionResult(
                    success=False,
                    deal_id=deal_id,
                    error="Broker API timeout (10 seconds)",
                    error_detail={"timeout_seconds": 10.0}
                )

            return ExecutionResult(success=True, deal_id=deal_id)
        except CapitalComError as e:
            logger.error(f"Failed to modify position {deal_id}: {e}")
            return ExecutionResult(success=False, deal_id=deal_id, error=str(e))

    def _paper_fill(self, order: ExecutionOrder) -> ExecutionResult:
        """Simulate a paper trading fill."""
        deal_id = f"PAPER-{uuid4().hex[:8]}"
        logger.info(
            f"Paper fill: {order.epic} {order.direction} "
            f"size={order.size:.4f} @ {order.entry_price:.2f} -> {deal_id}"
        )
        return ExecutionResult(
            success=True,
            deal_id=deal_id,
            fill_price=order.entry_price,
            slippage=0.0,
        )

    async def _live_fill(self, order: ExecutionOrder) -> ExecutionResult:
        """Execute a live order via broker."""
        try:
            direction = Direction.BUY if order.direction == "BUY" else Direction.SELL
            request = CreatePositionRequest(
                epic=order.epic,
                direction=direction,
                size=order.size,
                stop_level=order.stop_loss,
                profit_level=order.take_profit,
            )

            # CRITICAL FIX (CRIT-6): Add 10-second timeout to prevent infinite hang
            try:
                confirmation = await asyncio.wait_for(
                    self._broker.create_position(request),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error(f"Broker API timeout (10s) for {order.epic} {order.direction}")
                return ExecutionResult(
                    success=False,
                    error="Broker API timeout (10 seconds)",
                    error_detail={"timeout_seconds": 10.0, "epic": order.epic}
                )

            # Check if broker accepted the deal
            if confirmation.deal_status == "REJECTED":
                reason = confirmation.reason or "Unknown rejection"
                logger.warning(
                    f"Order rejected by broker: {order.epic} {order.direction} "
                    f"reason={reason}"
                )
                parsed = parse_broker_error(reason, epic=order.epic)
                return ExecutionResult(
                    success=False,
                    deal_id=confirmation.deal_id,
                    error=parsed.summary,
                    error_detail=parsed.to_dict(),
                )

            slippage = abs(confirmation.level - order.entry_price)
            logger.info(
                f"Live fill: {order.epic} {order.direction} "
                f"size={order.size:.4f} @ {confirmation.level:.2f} "
                f"(expected {order.entry_price:.2f}, slippage={slippage:.4f})"
            )

            return ExecutionResult(
                success=True,
                deal_id=confirmation.deal_id,
                fill_price=confirmation.level,
                slippage=slippage,
            )

        except MarketClosedError as e:
            logger.info(f"Market closed for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False, error=parsed.summary, error_detail=parsed.to_dict(),
            )
        except InsufficientFundsError as e:
            logger.error(f"Insufficient funds for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False, error=parsed.summary, error_detail=parsed.to_dict(),
            )
        except OrderRejectedError as e:
            logger.error(f"Order rejected for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False, error=parsed.summary, error_detail=parsed.to_dict(),
            )
        except RateLimitError as e:
            logger.warning(f"Rate limited on {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False, error=parsed.summary, error_detail=parsed.to_dict(),
            )
        except CapitalComError as e:
            logger.error(f"Broker error for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False, error=parsed.summary, error_detail=parsed.to_dict(),
            )

    async def _live_close(self, deal_id: str) -> ExecutionResult:
        """Close a live position via broker."""
        try:
            # CRITICAL FIX (CRIT-6): Add 10-second timeout to prevent infinite hang
            try:
                confirmation = await asyncio.wait_for(
                    self._broker.close_position(deal_id),
                    timeout=10.0
                )
            except asyncio.TimeoutError:
                logger.error(f"Broker API timeout (10s) closing position {deal_id}")
                return ExecutionResult(
                    success=False,
                    deal_id=deal_id,
                    error="Broker API timeout (10 seconds)",
                    error_detail={"timeout_seconds": 10.0}
                )

            return ExecutionResult(
                success=True,
                deal_id=confirmation.deal_id,
                fill_price=confirmation.level,
            )
        except CapitalComError as e:
            logger.error(f"Failed to close position {deal_id}: {e}")
            return ExecutionResult(success=False, deal_id=deal_id, error=str(e))
