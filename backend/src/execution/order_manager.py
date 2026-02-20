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
        position_tracker=None,
    ):
        """
        Initialize order manager.

        Args:
            broker: Capital.com client (required for LIVE mode)
            mode: Execution mode (PAPER or LIVE)
            position_tracker: Optional PositionTracker for updating local SL/TP on broker rejection
        """
        self._broker = broker
        self._mode = mode
        self._position_tracker = position_tracker

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

            opened_without_stops = False

            confirmation = await self._send_position_request(request, order)
            if confirmation is None:
                return ExecutionResult(
                    success=False,
                    error="Broker API timeout (10 seconds)",
                    error_detail={"timeout_seconds": 10.0, "epic": order.epic}
                )

            # Check if broker rejected due to invalid SL/TP — retry without them
            if confirmation.deal_status == "REJECTED":
                reason = confirmation.reason or ""
                if "stoploss" in reason.lower() or "takeprofit" in reason.lower():
                    logger.warning(
                        f"[{order.epic}] Broker rejected SL/TP ({reason}), "
                        f"retrying without — will set stops after fill"
                    )
                    request_no_stops = CreatePositionRequest(
                        epic=order.epic,
                        direction=direction,
                        size=order.size,
                    )
                    confirmation = await self._send_position_request(request_no_stops, order)
                    if confirmation is None:
                        return ExecutionResult(
                            success=False,
                            error="Broker API timeout on retry (10 seconds)",
                            error_detail={"timeout_seconds": 10.0, "epic": order.epic}
                        )
                    opened_without_stops = True

            # Check if broker accepted the deal
            if confirmation.deal_status == "REJECTED":
                reason = confirmation.reason or "Unknown rejection"
                # Include confirmation status for extra context
                extra = f" (status={confirmation.status})" if confirmation.status else ""
                logger.warning(
                    f"Order rejected by broker: {order.epic} {order.direction} "
                    f"size={order.size:.4f} reason={reason}{extra}"
                )
                parsed = parse_broker_error(reason, epic=order.epic)
                detail = parsed.to_dict()
                # Enrich with order context so the UI can show useful info
                detail["size"] = order.size
                detail["direction"] = order.direction
                detail["stop_loss"] = order.stop_loss
                detail["take_profit"] = order.take_profit
                return ExecutionResult(
                    success=False,
                    deal_id=confirmation.deal_id,
                    error=parsed.summary,
                    error_detail=detail,
                )

            slippage = abs(confirmation.level - order.entry_price)
            logger.info(
                f"Live fill: {order.epic} {order.direction} "
                f"size={order.size:.4f} @ {confirmation.level:.2f} "
                f"(expected {order.entry_price:.2f}, slippage={slippage:.4f})"
            )

            # CRITICAL: If opened without stops, set SL/TP via modify_stops
            if opened_without_stops and confirmation.deal_id:
                await self._set_stops_after_fill(
                    deal_id=confirmation.deal_id,
                    epic=order.epic,
                    direction=order.direction,
                    fill_price=confirmation.level,
                    original_sl=order.stop_loss,
                    original_tp=order.take_profit,
                    original_entry=order.entry_price,
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
            # Check if it's a SL/TP error — retry without stops
            error_str = str(e).lower()
            if "stoploss" in error_str or "takeprofit" in error_str:
                logger.warning(
                    f"[{order.epic}] Broker SL/TP error ({e}), retrying without stops"
                )
                try:
                    direction = Direction.BUY if order.direction == "BUY" else Direction.SELL
                    request_no_stops = CreatePositionRequest(
                        epic=order.epic,
                        direction=direction,
                        size=order.size,
                    )
                    confirmation = await self._send_position_request(request_no_stops, order)
                    if confirmation and confirmation.deal_status != "REJECTED":
                        slippage = abs(confirmation.level - order.entry_price)
                        logger.info(
                            f"Live fill (no SL/TP): {order.epic} {order.direction} "
                            f"size={order.size:.4f} @ {confirmation.level:.2f}"
                        )

                        # Set stops after fill
                        if confirmation.deal_id:
                            await self._set_stops_after_fill(
                                deal_id=confirmation.deal_id,
                                epic=order.epic,
                                direction=order.direction,
                                fill_price=confirmation.level,
                                original_sl=order.stop_loss,
                                original_tp=order.take_profit,
                                original_entry=order.entry_price,
                            )

                        return ExecutionResult(
                            success=True,
                            deal_id=confirmation.deal_id,
                            fill_price=confirmation.level,
                            slippage=slippage,
                        )
                except Exception:
                    pass  # Fall through to original error
            logger.error(f"Broker error for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False, error=parsed.summary, error_detail=parsed.to_dict(),
            )

    async def _send_position_request(self, request: CreatePositionRequest, order: ExecutionOrder):
        """Send position request to broker with timeout. Returns None on timeout."""
        try:
            return await asyncio.wait_for(
                self._broker.create_position(request),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.error(f"Broker API timeout (10s) for {order.epic} {order.direction}")
            return None

    async def _set_stops_after_fill(
        self,
        deal_id: str,
        epic: str,
        direction: str,
        fill_price: float,
        original_sl: float | None,
        original_tp: float | None,
        original_entry: float,
    ) -> None:
        """
        Set SL/TP on a broker position AFTER it has been filled.

        Recalculates stop/profit levels relative to the actual fill price
        (not the predicted OHLC price used to compute the original levels).
        This handles the case where broker rejected the initial SL/TP.
        """
        if original_sl is None and original_tp is None:
            return

        # Recalculate SL/TP relative to fill price (preserve distance from entry)
        adjusted_sl = None
        adjusted_tp = None

        if original_sl is not None and original_entry > 0:
            sl_distance = abs(original_entry - original_sl)
            if direction == "BUY":
                adjusted_sl = fill_price - sl_distance
            else:
                adjusted_sl = fill_price + sl_distance
            # Ensure SL is on the correct side
            if direction == "BUY" and adjusted_sl >= fill_price:
                adjusted_sl = fill_price * 0.97  # 3% fallback SL
            elif direction == "SELL" and adjusted_sl <= fill_price:
                adjusted_sl = fill_price * 1.03

        if original_tp is not None and original_entry > 0:
            tp_distance = abs(original_tp - original_entry)
            if direction == "BUY":
                adjusted_tp = fill_price + tp_distance
            else:
                adjusted_tp = fill_price - tp_distance

        logger.info(
            f"[{epic}] Setting post-fill stops: SL={adjusted_sl}, TP={adjusted_tp} "
            f"(fill={fill_price}, original SL={original_sl}, TP={original_tp})"
        )

        # Capital.com returns a DIFFERENT deal_id for create vs list.
        # We must look up the real position deal_id by listing positions
        # and matching by epic. Add delays for broker propagation.
        max_retries = 3
        delays = [2.0, 3.0, 5.0]  # seconds between retries
        actual_deal_id = deal_id  # fallback to creation deal_id

        for attempt in range(max_retries):
            try:
                await asyncio.sleep(delays[attempt])

                # Look up the real broker deal_id by epic
                if self._broker:
                    try:
                        positions = await asyncio.wait_for(
                            self._broker.list_positions(), timeout=10.0
                        )
                        for p in positions:
                            if p.epic == epic:
                                actual_deal_id = p.deal_id
                                break
                    except Exception as e:
                        logger.debug(f"[{epic}] Position lookup failed: {e}")

                if attempt > 0:
                    logger.info(
                        f"[{epic}] Retry #{attempt + 1} setting SL/TP "
                        f"(deal_id={actual_deal_id})..."
                    )

                result = await self.modify_stops(
                    deal_id=actual_deal_id,
                    stop_level=adjusted_sl,
                    profit_level=adjusted_tp,
                )
                if result.success:
                    logger.info(f"[{epic}] ✅ SL/TP set on broker: SL={adjusted_sl}, TP={adjusted_tp}")
                    return  # Success
                elif "not-found" in (result.error or ""):
                    logger.debug(f"[{epic}] Deal not yet available (attempt {attempt + 1})")
                    continue  # Retry
                else:
                    logger.warning(
                        f"[{epic}] ⚠️ Failed to set SL/TP on broker ({result.error}). "
                        f"Position {deal_id} will use LOCAL stop management only."
                    )
                    self._update_local_stops(deal_id, adjusted_sl, adjusted_tp)
                    return  # Non-retryable error
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(f"[{epic}] Exception on attempt {attempt + 1}: {e}")
                    continue
                logger.warning(
                    f"[{epic}] ⚠️ All {max_retries} attempts failed to set SL/TP ({e}). "
                    f"Position {deal_id} will use LOCAL stop management only."
                )
                self._update_local_stops(deal_id, adjusted_sl, adjusted_tp)

    def _update_local_stops(self, deal_id: str, sl: float | None, tp: float | None) -> None:
        """Update local position SL/TP when broker rejects. Falls back gracefully."""
        if self._position_tracker is None:
            return
        try:
            self._position_tracker.update_stops(deal_id, stop_level=sl, profit_level=tp)
        except Exception as e:
            logger.debug(f"Local stops update failed for {deal_id}: {e}")

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
