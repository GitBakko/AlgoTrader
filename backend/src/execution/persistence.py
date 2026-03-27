"""
Execution persistence: saves trade executions to PostgreSQL.
Creates Position + Trade records in the database after successful execution.
Graceful: if no DB session available, logs and skips.
"""

from datetime import UTC, datetime
from decimal import Decimal

from loguru import logger

from src.database.models import Position, Trade
from src.execution.schemas import ExecutionResult
from src.strategy.schemas import TradingSignal


class ExecutionPersistence:
    """Persists execution results to the database."""

    @staticmethod
    async def persist_execution(
        session,
        signal: TradingSignal,
        result: ExecutionResult,
        position_size: float,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> Position | None:
        """
        Create Position + Trade records from an execution result.

        Args:
            session: AsyncSession (or None to skip persistence)
            signal: Original trading signal
            result: Execution result with fill details
            position_size: Approved position size
            stop_loss: Stop loss level
            take_profit: Take profit level

        Returns:
            Created Position or None if no DB
        """
        if session is None:
            logger.debug("No DB session, skipping execution persistence")
            return None

        if not result.success or not result.deal_id:
            return None

        now = datetime.now(UTC)

        # Create Position record
        position = Position(
            deal_id=result.deal_id,
            epic=signal.epic,
            direction=signal.direction.value,
            size=Decimal(str(position_size)),
            entry_price=Decimal(str(result.fill_price or signal.entry_price)),
            current_price=Decimal(str(result.fill_price or signal.entry_price)),
            stop_loss=Decimal(str(stop_loss)) if stop_loss else None,
            take_profit=Decimal(str(take_profit)) if take_profit else None,
            status="OPEN",
            opened_at=now,
        )

        session.add(position)
        await session.flush()
        await session.refresh(position)

        # Create Trade record (OPEN action)
        trade = Trade(
            position_id=position.id,
            deal_reference=result.deal_id,
            trade_type="OPEN",
            epic=signal.epic,
            direction=signal.direction.value,
            size=Decimal(str(position_size)),
            price=Decimal(str(result.fill_price or signal.entry_price)),
            executed_at=now,
        )

        session.add(trade)
        await session.flush()

        logger.info(
            f"Persisted: Position {position.id} + Trade for "
            f"{signal.epic} {signal.direction.value} @ {result.fill_price}"
        )

        # Publish trade event via Redis (fire-and-forget)
        try:
            from src.api.websocket import ws_manager
            from src.utils.event_bus import event_bus

            trade_event = {
                "type": "trade_opened",
                "deal_id": result.deal_id,
                "epic": signal.epic,
                "direction": signal.direction.value,
                "size": position_size,
                "fill_price": result.fill_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "timestamp": now.isoformat(),
            }
            await event_bus.publish(f"trade:{signal.epic}", trade_event)
            await ws_manager.broadcast("trades", trade_event)
        except Exception as e:
            logger.debug(f"Event publish after trade failed: {e}")

        return position
