"""
Order management: creates, closes, and modifies orders via broker or paper trading.
"""

import asyncio
import time
from uuid import uuid4

from loguru import logger
from pydantic import ValidationError

from src.broker.client import CapitalComClient
from src.broker.exceptions import (
    CapitalComError,
    InsufficientFundsError,
    MarketClosedError,
    OrderRejectedError,
    RateLimitError,
)
from src.broker.models import CreatePositionRequest, Direction, ModifyPositionRequest
from src.execution.schemas import ExecutionMode, ExecutionOrder, ExecutionResult
from src.utils.broker_error_parser import parse_broker_error


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
                await asyncio.wait_for(self._broker.modify_position(deal_id, request), timeout=10.0)
            except TimeoutError:
                logger.error(f"Broker API timeout (10s) modifying position {deal_id}")
                return ExecutionResult(
                    success=False,
                    deal_id=deal_id,
                    error="Broker API timeout (10 seconds)",
                    error_detail={"timeout_seconds": 10.0},
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
                    error_detail={"timeout_seconds": 10.0, "epic": order.epic},
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
                            error_detail={"timeout_seconds": 10.0, "epic": order.epic},
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
            actual_sl = order.stop_loss
            actual_tp = order.take_profit
            if opened_without_stops and confirmation.deal_id:
                actual_sl, actual_tp = await self._set_stops_after_fill(
                    deal_id=confirmation.deal_id,
                    epic=order.epic,
                    direction=order.direction,
                    fill_price=confirmation.level,
                    original_sl=order.stop_loss,
                    original_tp=order.take_profit,
                    original_entry=order.entry_price,
                )

            # Read back the actual SL/TP from the broker as authoritative source
            if confirmation.deal_id:
                try:
                    actual_sl, actual_tp = await self._read_actual_stops(
                        confirmation.deal_id, fallback_sl=actual_sl, fallback_tp=actual_tp
                    )
                except Exception as e:
                    logger.debug(f"Could not read actual stops for {confirmation.deal_id}: {e}")

            return ExecutionResult(
                success=True,
                deal_id=confirmation.deal_id,
                deal_reference=(
                    confirmation.deal_reference
                    if isinstance(getattr(confirmation, "deal_reference", None), str)
                    else None
                ),
                fill_price=confirmation.level,
                slippage=slippage,
                actual_stop_loss=actual_sl,
                actual_take_profit=actual_tp,
            )

        except MarketClosedError as e:
            logger.info(f"Market closed for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False,
                error=parsed.summary,
                error_detail=parsed.to_dict(),
            )
        except InsufficientFundsError as e:
            logger.error(f"Insufficient funds for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False,
                error=parsed.summary,
                error_detail=parsed.to_dict(),
            )
        except OrderRejectedError as e:
            logger.error(f"Order rejected for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False,
                error=parsed.summary,
                error_detail=parsed.to_dict(),
            )
        except RateLimitError as e:
            logger.warning(f"Rate limited on {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False,
                error=parsed.summary,
                error_detail=parsed.to_dict(),
            )
        except CapitalComError as e:
            # Check if it's a SL/TP error — retry with corrected levels or without
            error_str = str(e).lower()
            if "stoploss" in error_str or "takeprofit" in error_str:
                # Extract broker's minimum/maximum from error message
                import re as _re

                val_match = _re.search(r":\s*([\d.]+)", str(e))
                broker_limit = float(val_match.group(1)) if val_match else None

                # First attempt: retry with broker's corrected SL/TP
                if broker_limit is not None:
                    direction = Direction.BUY if order.direction == "BUY" else Direction.SELL
                    corrected_sl = order.stop_loss
                    corrected_tp = order.take_profit

                    if "stoploss.minvalue" in error_str:
                        # Broker says SL must be >= minvalue (for SELL) or <= for BUY
                        # Add 0.5% margin beyond broker's minimum
                        margin = broker_limit * 0.005
                        if order.direction == "SELL":
                            corrected_sl = broker_limit + margin
                        else:
                            corrected_sl = broker_limit - margin
                    elif "takeprofit.maxvalue" in error_str:
                        margin = broker_limit * 0.005
                        if order.direction == "SELL":
                            corrected_tp = broker_limit - margin
                        else:
                            corrected_tp = broker_limit + margin

                    logger.warning(
                        f"[{order.epic}] Broker SL/TP error ({e}), "
                        f"retrying with corrected SL={corrected_sl:.5f} TP={corrected_tp:.5f}"
                    )
                    try:
                        request_corrected = CreatePositionRequest(
                            epic=order.epic,
                            direction=direction,
                            size=order.size,
                            stop_level=corrected_sl,
                            profit_level=corrected_tp,
                        )
                        confirmation = await self._send_position_request(
                            request_corrected,
                            order,
                        )
                        if confirmation and confirmation.deal_status != "REJECTED":
                            slippage = abs(confirmation.level - order.entry_price)
                            logger.info(
                                f"Live fill (corrected SL/TP): {order.epic} "
                                f"{order.direction} size={order.size:.4f} "
                                f"@ {confirmation.level:.2f}"
                            )
                            # Read back actual stops from broker (corrected_sl/tp are
                            # what we sent, but broker may have applied further adjustments)
                            final_sl = corrected_sl
                            final_tp = corrected_tp
                            if confirmation.deal_id:
                                try:
                                    final_sl, final_tp = await self._read_actual_stops(
                                        confirmation.deal_id,
                                        fallback_sl=corrected_sl,
                                        fallback_tp=corrected_tp,
                                    )
                                except Exception as ex:
                                    logger.debug(f"Could not read actual stops: {ex}")
                            return ExecutionResult(
                                success=True,
                                deal_id=confirmation.deal_id,
                                deal_reference=(
                                    confirmation.deal_reference
                                    if isinstance(
                                        getattr(confirmation, "deal_reference", None), str
                                    )
                                    else None
                                ),
                                fill_price=confirmation.level,
                                slippage=slippage,
                                actual_stop_loss=final_sl,
                                actual_take_profit=final_tp,
                            )
                        if confirmation is None:
                            # Confirm TIMEOUT, not a broker rejection (audit
                            # M1.3): the two-phase create may have filled
                            # server-side. Check before re-submitting — a
                            # blind no-stops retry opened duplicate positions.
                            filled = await self._find_recent_fill(
                                order.epic, order.direction, order.size
                            )
                            if filled is not None:
                                logger.warning(
                                    f"[{order.epic}] Timed-out create actually FILLED "
                                    f"(deal {filled.deal_id}) — adopting, no re-submit"
                                )
                                fill_price = float(filled.level)
                                applied_sl = None
                                applied_tp = None
                                try:
                                    applied_sl, applied_tp = await self._set_stops_after_fill(
                                        deal_id=filled.deal_id,
                                        epic=order.epic,
                                        direction=order.direction,
                                        fill_price=fill_price,
                                        original_sl=order.stop_loss,
                                        original_tp=order.take_profit,
                                        original_entry=order.entry_price,
                                    )
                                    # Read back authoritative values from broker
                                    try:
                                        applied_sl, applied_tp = await self._read_actual_stops(
                                            filled.deal_id,
                                            fallback_sl=applied_sl,
                                            fallback_tp=applied_tp,
                                        )
                                    except Exception as ex:
                                        logger.debug(f"Could not read actual stops: {ex}")
                                except Exception as ex:
                                    logger.warning(
                                        f"[{order.epic}] Failed to set stops on adopted "
                                        f"position {filled.deal_id}: {ex}"
                                    )
                                return ExecutionResult(
                                    success=True,
                                    deal_id=filled.deal_id,
                                    fill_price=fill_price,
                                    slippage=abs(fill_price - order.entry_price),
                                    actual_stop_loss=applied_sl,
                                    actual_take_profit=applied_tp,
                                )
                    except CapitalComError as e2:
                        # Broker-CONFIRMED rejection of the corrected levels —
                        # safe to fall through to the no-stops retry.
                        logger.warning(f"[{order.epic}] Corrected SL/TP create rejected: {e2}")
                    except ValidationError as e2:
                        logger.warning(f"[{order.epic}] Corrected SL/TP request invalid: {e2}")

                # Second attempt: retry without SL/TP entirely, set after fill
                logger.warning(
                    f"[{order.epic}] Corrected SL/TP also failed, retrying without stops"
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
                        applied_sl = None
                        applied_tp = None
                        if confirmation.deal_id:
                            applied_sl, applied_tp = await self._set_stops_after_fill(
                                deal_id=confirmation.deal_id,
                                epic=order.epic,
                                direction=order.direction,
                                fill_price=confirmation.level,
                                original_sl=order.stop_loss,
                                original_tp=order.take_profit,
                                original_entry=order.entry_price,
                            )
                            # Read back authoritative values from broker
                            try:
                                applied_sl, applied_tp = await self._read_actual_stops(
                                    confirmation.deal_id,
                                    fallback_sl=applied_sl,
                                    fallback_tp=applied_tp,
                                )
                            except Exception as ex:
                                logger.debug(f"Could not read actual stops: {ex}")

                        return ExecutionResult(
                            success=True,
                            deal_id=confirmation.deal_id,
                            deal_reference=(
                                confirmation.deal_reference
                                if isinstance(getattr(confirmation, "deal_reference", None), str)
                                else None
                            ),
                            fill_price=confirmation.level,
                            slippage=slippage,
                            actual_stop_loss=applied_sl,
                            actual_take_profit=applied_tp,
                        )
                except Exception:
                    pass  # Fall through to original error
            logger.error(f"Broker error for {order.epic}: {e}")
            parsed = parse_broker_error(str(e), epic=order.epic)
            return ExecutionResult(
                success=False,
                error=parsed.summary,
                error_detail=parsed.to_dict(),
            )

    async def _send_position_request(self, request: CreatePositionRequest, order: ExecutionOrder):
        """Send position request to broker with timeout. Returns None on timeout."""
        try:
            return await asyncio.wait_for(self._broker.create_position(request), timeout=10.0)
        except TimeoutError:
            logger.error(f"Broker API timeout (10s) for {order.epic} {order.direction}")
            return None

    async def _find_recent_fill(self, epic: str, direction: str, size: float):
        """After a create timeout, check whether the order actually filled.

        A 10s confirm timeout does NOT mean the broker rejected the create
        (two-phase POST+confirm). Re-submitting blindly opened duplicate
        positions (audit M1.3). Match on epic+direction+size — the position
        opened by the timed-out request, if any. Returns the broker
        Position or None.
        """
        try:
            positions = await asyncio.wait_for(self._broker.list_positions(), timeout=10.0)
        except Exception as e:
            logger.warning(f"[{epic}] Post-timeout fill check failed: {e}")
            return None
        for pos in positions or []:
            pos_dir = getattr(pos.direction, "value", pos.direction)
            if (
                pos.epic == epic
                and str(pos_dir) == direction
                and abs(float(pos.size) - float(size)) < 1e-9
            ):
                return pos
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
    ) -> tuple[float | None, float | None]:
        """
        Set SL/TP on a broker position AFTER it has been filled.

        Recalculates stop/profit levels relative to the actual fill price
        (not the predicted OHLC price used to compute the original levels).
        This handles the case where broker rejected the initial SL/TP.

        Returns:
            (actual_sl, actual_tp) — the levels actually applied (may be None
            on failure or differ from requested due to broker constraints).
        """
        if original_sl is None and original_tp is None:
            return None, None

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
                    logger.info(
                        f"[{epic}] ✅ SL/TP set on broker: SL={adjusted_sl}, TP={adjusted_tp}"
                    )
                    return adjusted_sl, adjusted_tp
                elif "not-found" in (result.error or ""):
                    logger.debug(f"[{epic}] Deal not yet available (attempt {attempt + 1})")
                    continue  # Retry
                else:
                    logger.warning(
                        f"[{epic}] ⚠️ Failed to set SL/TP on broker ({result.error}). "
                        f"Position {deal_id} will use LOCAL stop management only."
                    )
                    self._update_local_stops(deal_id, adjusted_sl, adjusted_tp)
                    return adjusted_sl, adjusted_tp
            except Exception as e:
                if attempt < max_retries - 1:
                    logger.debug(f"[{epic}] Exception on attempt {attempt + 1}: {e}")
                    continue
                logger.warning(
                    f"[{epic}] ⚠️ All {max_retries} attempts failed to set SL/TP ({e}). "
                    f"Position {deal_id} will use LOCAL stop management only."
                )
                self._update_local_stops(deal_id, adjusted_sl, adjusted_tp)
        return adjusted_sl, adjusted_tp

    async def _read_actual_stops(
        self,
        deal_id: str,
        fallback_sl: float | None = None,
        fallback_tp: float | None = None,
    ) -> tuple[float | None, float | None]:
        """Read the actual SL/TP currently set on the broker for a position.

        Capital.com sometimes adjusts SL/TP values to satisfy minimum-distance
        constraints (rejecting our requested level and applying a slightly
        wider one). This reads the authoritative values from the broker so
        the trailing stop manager and DB stay in sync with reality.

        Args:
            deal_id: Position deal ID (the one returned at creation)
            fallback_sl: Value to return if broker lookup fails
            fallback_tp: Value to return if broker lookup fails

        Returns:
            (actual_sl, actual_tp) — broker-confirmed values, or fallbacks.
        """
        if self._broker is None:
            return fallback_sl, fallback_tp

        try:
            # Step 8 (close-detection v2): match only by exact deal_id.
            # The previous `deal_id in p.deal_id` substring fallback silently
            # paired our Position with broker-rotated dealIds (see memory
            # `project_capital_com_dealid_mutation.md`), so SL/TP reads
            # occasionally landed against a different open position on the
            # same account. Exact equality is the authoritative match; when
            # it fails we return the caller's fallbacks rather than guess.
            positions = await asyncio.wait_for(self._broker.list_positions(), timeout=5.0)
            for p in positions:
                if p.deal_id == deal_id:
                    sl_val = p.stop_level if p.stop_level else fallback_sl
                    tp_val = p.profit_level if p.profit_level else fallback_tp
                    if sl_val != fallback_sl or tp_val != fallback_tp:
                        logger.info(
                            f"[{p.epic}] Broker actual stops differ from requested: "
                            f"SL={sl_val} (req {fallback_sl}), TP={tp_val} (req {fallback_tp})"
                        )
                    return sl_val, tp_val
        except Exception as e:
            logger.debug(f"_read_actual_stops failed: {e}")
        return fallback_sl, fallback_tp

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
                    self._broker.close_position(deal_id), timeout=10.0
                )
            except TimeoutError:
                logger.error(f"Broker API timeout (10s) closing position {deal_id}")
                return ExecutionResult(
                    success=False,
                    deal_id=deal_id,
                    error="Broker API timeout (10 seconds)",
                    error_detail={"timeout_seconds": 10.0},
                )

            return ExecutionResult(
                success=True,
                deal_id=confirmation.deal_id,
                fill_price=confirmation.level,
            )
        except CapitalComError as e:
            logger.error(f"Failed to close position {deal_id}: {e}")
            return ExecutionResult(success=False, deal_id=deal_id, error=str(e))
