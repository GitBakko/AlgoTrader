"""
State Recovery Service for MANTIS AI.
Restores trading state after backend restart from PostgreSQL and/or broker API.

Recovery Strategy:
- PAPER mode: PostgreSQL → Empty state + WARNING
- DEMO/LIVE mode: Broker API → PostgreSQL fallback → Empty state + WARNING
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from loguru import logger

from src.broker.client import CapitalComClient
from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.risk.risk_manager import RiskManager
from src.risk.trailing_stop_manager import TrailingStopManager
from src.utils.config import get_settings


@dataclass
class RecoveryReport:
    """Report of state recovery operation."""

    success: bool
    positions_recovered: int
    positions_source: str  # "broker", "database", "none"
    trailing_stops_restored: int
    trade_history_count: int
    risk_state_restored: bool
    warnings: list[str]
    errors: list[str]
    recovered_at: datetime


class StateRecoveryService:
    """
    Service for recovering trading state after restart.

    Restores:
    - Open positions (from broker API or PostgreSQL)
    - Trailing stop states (phase, TP levels, prices)
    - Trade history (for Kelly criterion)
    - Risk manager state (drawdown monitor, circuit breakers, equity curve)
    """

    def __init__(
        self,
        execution_engine: ExecutionEngine,
        risk_manager: RiskManager,
        trailing_stop_manager: TrailingStopManager,
        broker: CapitalComClient | None = None,
        db_session_factory=None,
        paper_loop=None,
    ):
        self.execution_engine = execution_engine
        self.risk_manager = risk_manager
        self.trailing_stop_manager = trailing_stop_manager
        self.broker = broker
        self.db_session_factory = db_session_factory
        self.paper_loop = paper_loop
        self.mode = execution_engine.mode

    async def recover_all_state(self) -> RecoveryReport:
        """
        Main recovery orchestrator.

        Returns:
            RecoveryReport with recovery results and any warnings/errors
        """
        logger.bind(event="RECOVERY_START", mode=self.mode.value).info("🔄 Starting state recovery")
        warnings = []
        errors = []

        # Step 1: Recover positions
        positions, positions_source = await self._recover_positions()
        logger.bind(
            event="RECOVERY_POSITIONS",
            count=len(positions),
            source=positions_source,
        ).info(f"Recovered {len(positions)} positions from {positions_source}")

        # Step 2: Restore trailing stops for recovered positions
        trailing_stops_count = await self._restore_trailing_stops(positions)
        logger.bind(
            event="RECOVERY_TRAILING_STOPS",
            count=trailing_stops_count,
        ).info(f"Restored {trailing_stops_count} trailing stop states")

        # Step 3: Restore trade history for Kelly sizing
        trade_history_count = await self._restore_trade_history()
        logger.bind(
            event="RECOVERY_TRADE_HISTORY",
            count=trade_history_count,
        ).info(f"Restored {trade_history_count} trades for Kelly sizing")

        # Step 4: Restore risk manager state
        risk_restored = await self._restore_risk_state()
        logger.bind(
            event="RECOVERY_RISK_STATE",
            restored=risk_restored,
        ).info(f"Risk state restored: {risk_restored}")

        # Validation & warnings
        if self.mode == ExecutionMode.PAPER and positions_source == "none":
            warnings.append("PAPER mode: No positions recovered (database unavailable)")
        elif self.mode in (ExecutionMode.DEMO, ExecutionMode.LIVE) and positions_source == "none":
            errors.append("CRITICAL: No positions recovered in DEMO/LIVE mode!")

        if len(positions) > 0 and trailing_stops_count == 0:
            warnings.append("Open positions exist but no trailing stops recovered")

        if not risk_restored:
            warnings.append("Risk state not restored, using fresh state")

        success = positions_source != "none" or self.mode == ExecutionMode.PAPER

        report = RecoveryReport(
            success=success,
            positions_recovered=len(positions),
            positions_source=positions_source,
            trailing_stops_restored=trailing_stops_count,
            trade_history_count=trade_history_count,
            risk_state_restored=risk_restored,
            warnings=warnings,
            errors=errors,
            recovered_at=datetime.now(UTC),
        )

        if errors:
            logger.bind(
                event="RECOVERY_FAILURE",
                errors=errors,
                warnings=warnings,
            ).error(f"❌ Recovery completed with errors: {errors}")
        elif warnings:
            logger.bind(
                event="RECOVERY_WARNING",
                warnings=warnings,
            ).warning(f"⚠️  Recovery completed with warnings: {warnings}")
        else:
            logger.bind(
                event="RECOVERY_COMPLETE",
                positions=len(positions),
                trailing_stops=trailing_stops_count,
                trade_history=trade_history_count,
                risk_restored=risk_restored,
            ).success("✅ State recovery completed successfully")

        return report

    async def _recover_positions(self) -> tuple[list[dict], str]:
        """
        Recover open positions from broker API or database.

        Recovery strategy by mode:
        - PAPER: Try PostgreSQL → Empty (with warning)
        - DEMO/LIVE: Try Broker API → Try PostgreSQL → Empty (with error)

        Returns:
            Tuple of (positions_list, source_name)
        """
        if self.mode == ExecutionMode.PAPER:
            # PAPER mode: only use database
            positions = await self._load_positions_from_db()
            if positions:
                await self._inject_positions_into_engine(positions)
                return positions, "database"
            logger.warning("No positions in database (PAPER mode)")
            return [], "none"

        # DEMO/LIVE mode: try broker first, fallback to database
        # Load DB positions once (used for reconciliation or as fallback)
        db_positions = await self._load_positions_from_db()

        if self.broker:
            try:
                broker_positions = await self._load_positions_from_broker()
                if broker_positions:
                    # Reconcile with database if available
                    reconciled = await self._reconcile_positions(broker_positions, db_positions)
                    await self._inject_positions_into_engine(reconciled)
                    return reconciled, "broker"
            except Exception as e:
                logger.warning(f"Broker position recovery failed: {e}")

        # Broker failed or unavailable, use cached database positions
        if db_positions:
            logger.warning("Using database positions (broker unavailable)")
            await self._inject_positions_into_engine(db_positions)
            return db_positions, "database"

        logger.error("No positions recovered from any source!")
        return [], "none"

    async def _load_positions_from_broker(self) -> list[dict]:
        """
        Load open positions from Capital.com API with exponential backoff retry.

        Retries on transient errors (connection, timeout) up to 3 times.
        Fails fast on non-retryable errors (authentication, invalid request).

        Returns:
            List of position dicts or empty list on failure
        """
        if not self.broker:
            return []

        import asyncio

        import aiohttp

        for attempt in range(3):
            try:
                positions = await self.broker.list_positions()
                if attempt > 0:
                    logger.info(f"Broker position recovery succeeded on attempt {attempt + 1}/3")
                logger.debug(f"Loaded {len(positions)} positions from broker")
                return positions

            except (TimeoutError, aiohttp.ClientError) as e:
                # Retryable errors (connection, timeout)
                if attempt == 2:  # Last attempt
                    logger.error(f"Broker positions fetch failed after 3 attempts: {e}")
                    return []

                wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                logger.warning(
                    f"Broker fetch failed (attempt {attempt + 1}/3), "
                    f"retrying in {wait_time}s: {e}"
                )
                await asyncio.sleep(wait_time)

            except Exception as e:
                # Non-retryable errors (authentication, invalid request, etc.)
                logger.error(f"Broker positions fetch failed (non-retryable): {e}")
                return []

        return []  # Should never reach here, but for safety

    async def _load_positions_from_db(self) -> list[dict]:
        """Load open positions from PostgreSQL."""
        if not self.db_session_factory:
            return []

        try:
            from src.database.repositories import PositionRepository

            async with self.db_session_factory() as session:
                repo = PositionRepository(session)
                db_positions = await repo.get_open_positions()

                # Convert ORM models to dicts matching broker format
                positions = []
                for pos in db_positions:
                    positions.append(
                        {
                            "deal_id": pos.deal_id,
                            "epic": pos.epic,
                            "direction": pos.direction,
                            "size": float(pos.size),
                            "level": float(pos.entry_price),
                            "stop_loss": float(pos.stop_loss) if pos.stop_loss else None,
                            "take_profit": float(pos.take_profit) if pos.take_profit else None,
                            "unrealized_pnl": float(pos.profit_loss) if pos.profit_loss else 0.0,
                            "created_at": pos.opened_at.isoformat(),
                        }
                    )

                logger.debug(f"Loaded {len(positions)} positions from database")
                return positions
        except Exception as e:
            logger.error(f"Database positions fetch failed: {e}")
            return []

    async def _reconcile_positions(
        self, broker_positions: list[dict], db_positions: list[dict]
    ) -> list[dict]:
        """
        Reconcile broker and database positions.

        Strategy:
        - Broker data wins (more recent)
        - Log discrepancies (size mismatches, missing positions)
        - Auto-close stale DB-only positions
        - Update DB sizes to match broker

        Args:
            broker_positions: Positions from broker API
            db_positions: Positions from database

        Returns:
            Reconciled position list (broker-based)
        """
        broker_ids = {p["deal_id"] for p in broker_positions}
        db_ids = {p["deal_id"] for p in db_positions}

        # Positions in DB but not in broker (closed externally)
        stale_ids = db_ids - broker_ids
        if stale_ids and self.db_session_factory:
            logger.warning(
                f"Found {len(stale_ids)} stale positions in DB (not in broker): {stale_ids}"
            )

            # Auto-close stale positions
            try:
                from src.database.repositories import PositionRepository

                async with self.db_session_factory() as session:
                    repo = PositionRepository(session)
                    for deal_id in stale_ids:
                        await repo.mark_as_closed(deal_id, close_reason="EXTERNAL")
                        logger.info(f"Auto-closed stale position {deal_id} in DB")
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to auto-close stale positions: {e}")

        # Positions in broker but not in DB (opened externally or recovery gap)
        new_ids = broker_ids - db_ids
        if new_ids:
            logger.info(f"Found {len(new_ids)} new positions in broker (not in DB): {new_ids}")

        # Check for size mismatches on shared positions and update DB
        db_by_id = {p["deal_id"]: p for p in db_positions}
        size_updates = []

        for broker_pos in broker_positions:
            deal_id = broker_pos["deal_id"]
            if deal_id in db_by_id:
                db_pos = db_by_id[deal_id]
                if abs(broker_pos["size"] - db_pos["size"]) > 0.0001:
                    logger.warning(
                        f"Size mismatch for {deal_id}: broker={broker_pos['size']}, "
                        f"db={db_pos['size']} (updating DB to match broker)"
                    )
                    size_updates.append((deal_id, broker_pos["size"]))

        # Update sizes in DB
        if size_updates and self.db_session_factory:
            try:
                from src.database.repositories import PositionRepository

                async with self.db_session_factory() as session:
                    repo = PositionRepository(session)
                    for deal_id, new_size in size_updates:
                        await repo.update_size(deal_id, new_size)
                        logger.info(f"Updated position {deal_id} size in DB to {new_size}")
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to update position sizes: {e}")

        return broker_positions  # Broker wins

    async def _inject_positions_into_engine(self, positions: list[dict]) -> None:
        """
        Inject recovered positions into ExecutionEngine.

        Args:
            positions: List of position dicts to inject
        """
        for pos in positions:
            self.execution_engine._position_tracker.inject_paper_position(
                deal_id=pos["deal_id"],
                epic=pos["epic"],
                direction=pos["direction"],
                size=pos["size"],
                entry_price=pos["level"],
                stop_loss=pos.get("stop_loss"),
                take_profit=pos.get("take_profit"),
            )
        logger.info(f"Injected {len(positions)} positions into ExecutionEngine")

    async def _restore_trailing_stops(self, positions: list[dict]) -> int:
        """
        Restore trailing stop states for recovered positions.

        Args:
            positions: List of recovered positions

        Returns:
            Number of trailing stops restored
        """
        if not self.db_session_factory:
            return 0

        try:
            from src.database.repositories import TrailingStopRepository

            async with self.db_session_factory() as session:
                repo = TrailingStopRepository(session)
                states = await repo.get_all_active()

                # Filter to only positions that still exist
                position_ids = {p["deal_id"] for p in positions}
                restored_count = 0

                # Collect stale states for bulk deletion (performance optimization)
                stale_deal_ids = [
                    state.deal_id for state in states if state.deal_id not in position_ids
                ]

                if stale_deal_ids:
                    # Bulk delete stale states (avoids N+1 query)
                    await repo.bulk_delete(stale_deal_ids)
                    logger.debug(f"Removed {len(stale_deal_ids)} stale trailing stops")

                # Restore valid trailing stop states
                for state in states:
                    if state.deal_id in position_ids:
                        # Restore trailing stop state
                        self.trailing_stop_manager.restore_state(
                            deal_id=state.deal_id,
                            epic=state.epic,
                            direction=state.direction,
                            entry_price=float(state.entry_price),
                            current_stop=float(state.current_stop),
                            phase=state.phase,
                            tp1_level=float(state.tp1_level) if state.tp1_level else None,
                            tp2_level=float(state.tp2_level) if state.tp2_level else None,
                            highest_price=(
                                float(state.highest_price) if state.highest_price else None
                            ),
                            lowest_price=float(state.lowest_price) if state.lowest_price else None,
                        )
                        restored_count += 1

                await session.commit()
                logger.debug(f"Restored {restored_count} trailing stop states")
                return restored_count

        except Exception as e:
            logger.error(f"Trailing stop restoration failed: {e}")
            return 0

    async def _restore_trade_history(self) -> int:
        """
        Restore recent trade history for Kelly criterion.

        Returns:
            Number of trades restored
        """
        trade_history = await self._restore_trade_history_list()
        return len(trade_history)

    async def _restore_trade_history_list(self) -> list[dict]:
        """
        Restore recent trade history as a list.

        Returns:
            List of trade dicts with 'pnl' key
        """
        if not self.db_session_factory:
            return []

        try:
            from src.database.repositories import TradeRepository

            async with self.db_session_factory() as session:
                repo = TradeRepository(session)
                trades = await repo.get_recent_for_kelly(limit=200)

                # Convert to simple P&L list (matches _trade_history format)
                trade_history = []
                for trade in trades:
                    if trade.profit_loss is not None:
                        trade_history.append({"pnl": float(trade.profit_loss)})

                logger.debug(f"Restored {len(trade_history)} trades for Kelly sizing")
                return trade_history

        except Exception as e:
            logger.error(f"Trade history restoration failed: {e}")
            return []

    async def _restore_risk_state(self) -> bool:
        """
        Restore RiskManager internal state from latest snapshot.

        Returns:
            True if state was restored, False otherwise
        """
        if not self.db_session_factory:
            return False

        try:
            from src.database.repositories import RiskStateRepository

            async with self.db_session_factory() as session:
                repo = RiskStateRepository(session)
                snapshot = await repo.get_latest()

                if not snapshot:
                    logger.warning("No risk state snapshot found")
                    return False

                # Restore DrawdownMonitor state (access _state directly,
                # .state property returns a model_copy() which would be discarded)
                dm = self.risk_manager.drawdown_monitor
                dm._state.peak_equity = float(snapshot.peak_equity)
                dm._state.current_equity = float(snapshot.current_equity)

                # FIX: If snapshot is from a previous day, reset daily_start to current equity
                # to prevent stale daily P&L from tripping circuit breakers on restart
                from datetime import datetime

                snapshot_date = (
                    snapshot.snapshot_at.strftime("%Y-%m-%d") if snapshot.snapshot_at else ""
                )
                today = datetime.now(UTC).strftime("%Y-%m-%d")
                if snapshot_date != today:
                    dm._state.daily_start_equity = float(snapshot.current_equity)
                    logger.info(
                        f"Daily start equity reset to current ({snapshot.current_equity:.2f}) — "
                        f"snapshot from {snapshot_date}, today is {today}"
                    )
                else:
                    dm._state.daily_start_equity = float(snapshot.daily_start_equity)

                # Restore CircuitBreaker state (_consecutive_losses is private)
                cb = self.risk_manager.circuit_breakers
                cb._consecutive_losses = snapshot.consecutive_losses

                # Restore tripped breakers: {breaker_type: reason_string}
                import time as _time

                from src.risk.circuit_breakers import CircuitBreakerType

                for breaker_type_str, reason in snapshot.tripped_breakers.items():
                    try:
                        cb_type = CircuitBreakerType(breaker_type_str)
                        with cb._lock:
                            cb._tripped[cb_type] = reason
                            cb._tripped_at[cb_type] = _time.monotonic()
                    except Exception as e:
                        logger.warning(f"Failed to restore breaker {breaker_type_str}: {e}")

                # Restore EquityCurveFilter state (_equity_points is the internal deque)
                ec = self.risk_manager.equity_curve_filter
                ec._equity_points.clear()
                ec._equity_points.extend(snapshot.equity_curve_points)

                logger.info(
                    f"Restored risk state: peak_equity={snapshot.peak_equity}, "
                    f"daily_start={snapshot.daily_start_equity}, "
                    f"current={snapshot.current_equity}, "
                    f"consecutive_losses={snapshot.consecutive_losses}"
                )
                return True

        except Exception as e:
            logger.error(f"Risk state restoration failed: {e}")
            return False

    async def reinject_orphans(self) -> int:
        """For each Position in DB with status='OPEN' that the broker no
        longer reports, insert a PendingClose into
        paper_loop._pending_close_detections so the three-tier close
        detection picks it up within the reconciliation timeout window.

        An orphan arises when the backend was down while the broker closed
        the position — the DB still shows OPEN but the broker has no record.

        Returns:
            Number of orphans re-injected (0 on any error or guard condition).
        """
        from sqlalchemy import select

        from src.database.models import Position
        from src.trading.paper_loop import PendingClose

        # Guard: needs both broker and paper_loop to do anything useful
        if self.paper_loop is None:
            logger.warning("reinject_orphans: paper_loop not wired, skipping")
            return 0

        if not self.db_session_factory:
            logger.warning("reinject_orphans: no db_session_factory, skipping")
            return 0

        # Step 1: fetch broker's live positions
        try:
            broker_positions = await self.broker.list_positions() if self.broker else []
        except Exception as e:
            logger.warning(f"reinject_orphans: broker.list_positions() failed: {e}")
            return 0

        broker_deal_ids = {
            getattr(p, "deal_id", None)
            for p in broker_positions
            if getattr(p, "deal_id", None) is not None
        }

        # Step 2: fetch all DB-OPEN positions opened within max age
        max_age_days = get_settings().orphan_reinject_max_age_days
        cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=max_age_days)

        try:
            async with self.db_session_factory() as session:
                stmt = select(Position).where(
                    Position.status == "OPEN",
                    Position.opened_at >= cutoff,
                )
                db_open = (await session.execute(stmt)).scalars().all()
        except Exception as e:
            logger.error(f"reinject_orphans: DB query failed: {e}")
            return 0

        # Step 3: filter to orphans (DB=OPEN but broker has no record)
        pending_map = self.paper_loop._pending_close_detections
        orphans = [
            p
            for p in db_open
            if p.deal_id not in broker_deal_ids
            and p.deal_id not in pending_map  # skip already-queued
        ]

        if not orphans:
            logger.info(
                f"reinject_orphans: no orphans to reinject "
                f"(cutoff={cutoff.isoformat()}, {max_age_days} days)"
            )
            return 0

        now = datetime.now(UTC)
        for p in orphans:
            pending_map[p.deal_id] = PendingClose(
                deal_id=p.deal_id,
                deal_reference=p.deal_reference,  # populated for new rows post-migration
                epic=p.epic,
                direction=p.direction,
                size=float(p.size or 0),
                entry_price=float(p.entry_price or 0),
                prev_pos={
                    "deal_id": p.deal_id,
                    "epic": p.epic,
                    "direction": p.direction,
                    "size": float(p.size or 0),
                    "level": float(p.entry_price or 0),
                    "opened_at": p.opened_at,
                },
                first_seen=now,
                retry_count=0,
            )
            logger.warning(
                f"[{p.epic}] Orphan position {p.deal_id} re-injected at startup "
                f"for close reconciliation (DB=OPEN but broker missing)"
            )

        return len(orphans)

    async def rehydrate_pending_closes(self) -> int:
        """Restore the close-detection retry queue from the
        ``pending_close_detections`` table so the 10-minute reconciliation
        timeout survives backend restarts.

        Without this step, a pending close queued on the previous backend
        instance is silently forgotten, and the next time the broker
        reports the position as missing it is re-queued with
        ``retry_count=0 / first_seen=now`` — the timeout clock restarts
        from zero indefinitely. That exact silent failure produced
        tonight's DE40 UNRECONCILED record.

        Returns:
            Number of pending-close rows rehydrated (0 on any error or
            guard condition).
        """
        if self.paper_loop is None:
            logger.warning("rehydrate_pending_closes: paper_loop not wired, skipping")
            return 0
        if not self.db_session_factory:
            logger.warning("rehydrate_pending_closes: no db_session_factory, skipping")
            return 0

        # Local imports — avoids a circular dependency with paper_loop which
        # also imports from state_recovery indirectly via ExecutionEngine.
        from src.database.repositories.pending_close_repository import (
            PendingCloseRepository,
        )
        from src.trading.paper_loop import PendingClose

        try:
            async with self.db_session_factory() as session:
                repo = PendingCloseRepository(session)
                rows = await repo.list_all()
        except Exception as exc:  # noqa: BLE001
            logger.error(f"rehydrate_pending_closes: DB query failed: {exc}")
            return 0

        if not rows:
            logger.info("rehydrate_pending_closes: no persisted pending closes")
            return 0

        pending_map = self.paper_loop._pending_close_detections
        restored = 0
        for row in rows:
            # Do not overwrite an entry the running process has already
            # created in-memory — should not happen during boot but is the
            # safe behavior if called again later.
            if row.deal_id in pending_map:
                continue
            first_seen = row.first_seen
            if first_seen.tzinfo is None:
                first_seen = first_seen.replace(tzinfo=UTC)
            pending_map[row.deal_id] = PendingClose(
                deal_id=row.deal_id,
                deal_reference=row.deal_reference,
                epic=row.epic,
                direction=row.direction,
                size=float(row.size or 0),
                entry_price=float(row.entry_price or 0),
                prev_pos=dict(row.prev_pos or {}),
                first_seen=first_seen,
                retry_count=int(row.retry_count or 0),
            )
            restored += 1
            logger.warning(
                f"[{row.epic}] Rehydrated pending close {row.deal_id} "
                f"(retry_count={row.retry_count}, "
                f"first_seen={first_seen.isoformat()}) — reconciliation "
                f"timeout continues from where the previous process left off"
            )

        if restored:
            logger.info(
                f"rehydrate_pending_closes: restored {restored} pending " f"close(s) from DB"
            )
        return restored
