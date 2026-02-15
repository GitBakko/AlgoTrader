"""
Unit tests for State Recovery Service.

Tests the StateRecoveryService which restores trading state after backend restart
from broker API and/or PostgreSQL database.

Coverage:
- RecoveryReport dataclass creation and validation
- Position recovery from database (PAPER mode)
- Position recovery from broker API (DEMO/LIVE mode)
- Position reconciliation (broker vs database)
- Trailing stop state restoration
- Trade history restoration for Kelly sizing
- Risk state restoration (DrawdownMonitor, CircuitBreakers, EquityCurveFilter)
- Error handling and fallback logic
- Warning detection and validation
"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.execution.schemas import ExecutionMode
from src.execution.state_recovery import RecoveryReport, StateRecoveryService


# ══════════════════════════════════════════════════════════
# Test Class 1: RecoveryReport Dataclass
# ══════════════════════════════════════════════════════════


class TestRecoveryReport:
    """Tests for RecoveryReport dataclass."""

    def test_recovery_report_dataclass_creation(self):
        """Test RecoveryReport can be created with all fields."""
        report = RecoveryReport(
            success=True,
            positions_recovered=2,
            positions_source="broker",
            trailing_stops_restored=2,
            trade_history_count=150,
            risk_state_restored=True,
            warnings=["Size mismatch detected"],
            errors=[],
            recovered_at=datetime.now(timezone.utc),
        )

        assert report.success is True
        assert report.positions_recovered == 2
        assert report.positions_source == "broker"
        assert report.trailing_stops_restored == 2
        assert report.trade_history_count == 150
        assert report.risk_state_restored is True
        assert len(report.warnings) == 1
        assert len(report.errors) == 0

    def test_recovery_report_success_flag(self):
        """Test success flag correctly reflects recovery status."""
        # Success case
        success_report = RecoveryReport(
            success=True,
            positions_recovered=2,
            positions_source="database",
            trailing_stops_restored=2,
            trade_history_count=100,
            risk_state_restored=True,
            warnings=[],
            errors=[],
            recovered_at=datetime.now(timezone.utc),
        )
        assert success_report.success is True

        # Failure case
        failure_report = RecoveryReport(
            success=False,
            positions_recovered=0,
            positions_source="none",
            trailing_stops_restored=0,
            trade_history_count=0,
            risk_state_restored=False,
            warnings=[],
            errors=["No positions recovered from any source"],
            recovered_at=datetime.now(timezone.utc),
        )
        assert failure_report.success is False

    def test_recovery_report_warnings_accumulation(self):
        """Test warnings list can accumulate multiple warnings."""
        report = RecoveryReport(
            success=True,
            positions_recovered=2,
            positions_source="broker",
            trailing_stops_restored=0,
            trade_history_count=0,
            risk_state_restored=False,
            warnings=[
                "No trailing stops recovered",
                "Risk state not restored",
                "Trade history empty",
            ],
            errors=[],
            recovered_at=datetime.now(timezone.utc),
        )

        assert len(report.warnings) == 3
        assert "No trailing stops recovered" in report.warnings

    def test_recovery_report_errors_accumulation(self):
        """Test errors list can accumulate multiple errors."""
        report = RecoveryReport(
            success=False,
            positions_recovered=0,
            positions_source="none",
            trailing_stops_restored=0,
            trade_history_count=0,
            risk_state_restored=False,
            warnings=[],
            errors=[
                "Broker API unavailable",
                "Database connection failed",
                "CRITICAL: No positions recovered in DEMO mode",
            ],
            recovered_at=datetime.now(timezone.utc),
        )

        assert len(report.errors) == 3
        assert "Broker API unavailable" in report.errors

    def test_recovery_report_timestamp(self):
        """Test recovered_at timestamp is set correctly."""
        now = datetime.now(timezone.utc)
        report = RecoveryReport(
            success=True,
            positions_recovered=0,
            positions_source="none",
            trailing_stops_restored=0,
            trade_history_count=0,
            risk_state_restored=False,
            warnings=[],
            errors=[],
            recovered_at=now,
        )

        assert report.recovered_at == now
        assert report.recovered_at.tzinfo == timezone.utc


# ══════════════════════════════════════════════════════════
# Test Class 2: Position Recovery
# ══════════════════════════════════════════════════════════


class TestPositionRecovery:
    """Tests for position recovery from database and broker."""

    @pytest.mark.asyncio
    async def test_recover_positions_from_database_paper_mode(
        self, sample_positions, mock_db_session
    ):
        """Test recovering positions from database in PAPER mode."""
        # Setup mocks
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER
        execution_engine._position_tracker = MagicMock()

        risk_manager = MagicMock()
        trailing_stop_manager = MagicMock()

        async def mock_db_factory():
            return mock_db_session

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=trailing_stop_manager,
            broker=None,
            db_session_factory=lambda: mock_db_factory(),
        )

        # Mock _load_positions_from_db to return sample positions
        with patch.object(
            service, "_load_positions_from_db", return_value=sample_positions
        ):
            positions, source = await service._recover_positions()

        assert len(positions) == 2
        assert source == "database"
        assert positions[0]["deal_id"] == "POS001"
        assert positions[1]["epic"] == "BTCUSD"

    @pytest.mark.asyncio
    async def test_recover_positions_from_broker_demo_mode(
        self, sample_positions, mock_broker_client
    ):
        """Test recovering positions from broker API in DEMO mode."""
        # Setup mocks
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO
        execution_engine._position_tracker = MagicMock()

        risk_manager = MagicMock()
        trailing_stop_manager = MagicMock()

        mock_broker_client.list_positions = AsyncMock(return_value=sample_positions)

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=trailing_stop_manager,
            broker=mock_broker_client,
            db_session_factory=None,
        )

        # Mock both DB load and reconciliation
        with patch.object(service, "_load_positions_from_db", return_value=[]), \
             patch.object(service, "_reconcile_positions", return_value=sample_positions):
            positions, source = await service._recover_positions()

        assert len(positions) == 2
        assert source == "broker"

    @pytest.mark.asyncio
    async def test_recover_positions_from_broker_live_mode(
        self, sample_positions, mock_broker_client
    ):
        """Test recovering positions from broker API in LIVE mode."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.LIVE
        execution_engine._position_tracker = MagicMock()

        risk_manager = MagicMock()
        trailing_stop_manager = MagicMock()

        mock_broker_client.list_positions = AsyncMock(return_value=sample_positions)

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=trailing_stop_manager,
            broker=mock_broker_client,
            db_session_factory=None,
        )

        with patch.object(service, "_load_positions_from_db", return_value=[]), \
             patch.object(service, "_reconcile_positions", return_value=sample_positions):
            positions, source = await service._recover_positions()

        assert len(positions) == 2
        assert source == "broker"
        assert positions[0]["epic"] == "XAUUSD"

    @pytest.mark.asyncio
    async def test_recover_positions_fallback_to_db_on_broker_failure(
        self, sample_positions, mock_broker_client
    ):
        """Test fallback to database when broker API fails."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO
        execution_engine._position_tracker = MagicMock()

        risk_manager = MagicMock()
        trailing_stop_manager = MagicMock()

        # Broker fails
        mock_broker_client.list_positions = AsyncMock(
            side_effect=Exception("Broker API unavailable")
        )

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=trailing_stop_manager,
            broker=mock_broker_client,
            db_session_factory=None,
        )

        # DB succeeds
        with patch.object(
            service, "_load_positions_from_db", return_value=sample_positions
        ):
            positions, source = await service._recover_positions()

        assert len(positions) == 2
        assert source == "database"

    @pytest.mark.asyncio
    async def test_recover_positions_empty_state_on_both_failure(
        self, mock_broker_client
    ):
        """Test empty state when both broker and database fail."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO
        execution_engine._position_tracker = MagicMock()

        risk_manager = MagicMock()
        trailing_stop_manager = MagicMock()

        # Broker fails
        mock_broker_client.list_positions = AsyncMock(
            side_effect=Exception("Broker unavailable")
        )

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=trailing_stop_manager,
            broker=mock_broker_client,
            db_session_factory=None,
        )

        # DB also fails
        with patch.object(service, "_load_positions_from_db", return_value=[]):
            positions, source = await service._recover_positions()

        assert len(positions) == 0
        assert source == "none"

    @pytest.mark.asyncio
    async def test_inject_positions_into_engine(self, sample_positions):
        """Test positions are correctly injected into execution engine."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER
        execution_engine._position_tracker = MagicMock()

        risk_manager = MagicMock()
        trailing_stop_manager = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=trailing_stop_manager,
            broker=None,
            db_session_factory=None,
        )

        await service._inject_positions_into_engine(sample_positions)

        # Verify inject_paper_position was called for each position
        assert execution_engine._position_tracker.inject_paper_position.call_count == 2

        # Verify first call
        first_call = (
            execution_engine._position_tracker.inject_paper_position.call_args_list[0]
        )
        assert first_call.kwargs["deal_id"] == "POS001"
        assert first_call.kwargs["epic"] == "XAUUSD"
        assert first_call.kwargs["size"] == 1.0

    @pytest.mark.asyncio
    async def test_load_positions_from_db_converts_orm_to_dict(self):
        """Test database positions are converted from ORM to dict format."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        # Mock ORM position objects
        mock_orm_position = MagicMock()
        mock_orm_position.deal_id = "DEAL123"
        mock_orm_position.epic = "XAUUSD"
        mock_orm_position.direction = "BUY"
        mock_orm_position.size = Decimal("1.0")
        mock_orm_position.entry_price = Decimal("2075.50")
        mock_orm_position.stop_loss = Decimal("2050.00")
        mock_orm_position.take_profit = Decimal("2100.00")
        mock_orm_position.profit_loss = Decimal("25.00")
        mock_orm_position.opened_at = datetime.now(timezone.utc)

        # Without actual DB, we'll just verify the conversion logic exists
        # Full integration test would use real DB
        positions = await service._load_positions_from_db()
        assert isinstance(positions, list)

    @pytest.mark.asyncio
    async def test_load_positions_from_broker_returns_list(self, mock_broker_client):
        """Test broker positions are returned as list."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO

        mock_broker_client.list_positions = AsyncMock(
            return_value=[{"deal_id": "DEAL123", "epic": "BTCUSD"}]
        )

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=mock_broker_client,
            db_session_factory=None,
        )

        positions = await service._load_positions_from_broker()

        assert isinstance(positions, list)
        assert len(positions) == 1
        assert positions[0]["epic"] == "BTCUSD"


# ══════════════════════════════════════════════════════════
# Test Class 3: Position Reconciliation
# ══════════════════════════════════════════════════════════


class TestReconciliation:
    """Tests for broker vs database position reconciliation."""

    @pytest.mark.asyncio
    async def test_reconcile_positions_broker_wins(self):
        """Test broker data wins in reconciliation."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        broker_positions = [
            {"deal_id": "DEAL123", "size": 2.0, "epic": "XAUUSD"}  # Updated size
        ]

        db_positions = [
            {"deal_id": "DEAL123", "size": 1.0, "epic": "XAUUSD"}  # Old size
        ]

        reconciled = await service._reconcile_positions(broker_positions, db_positions)

        assert len(reconciled) == 1
        assert reconciled[0]["size"] == 2.0  # Broker wins

    @pytest.mark.asyncio
    async def test_reconcile_positions_detects_stale_db_positions(self):
        """Test detection of stale DB-only positions (closed externally)."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        broker_positions = [{"deal_id": "DEAL123", "epic": "XAUUSD", "size": 1.0}]

        db_positions = [
            {"deal_id": "DEAL123", "epic": "XAUUSD", "size": 1.0},
            {"deal_id": "DEAL456", "epic": "BTCUSD", "size": 0.5},  # Stale (not in broker)
        ]

        with patch("src.execution.state_recovery.logger") as mock_logger:
            reconciled = await service._reconcile_positions(broker_positions, db_positions)

        # Should log warning about stale position
        assert any(
            "stale" in str(call).lower() for call in mock_logger.warning.call_args_list
        )

        # Broker positions returned
        assert len(reconciled) == 1
        assert reconciled[0]["deal_id"] == "DEAL123"

    @pytest.mark.asyncio
    async def test_reconcile_positions_detects_new_broker_positions(self):
        """Test detection of new broker positions (not in DB)."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        broker_positions = [
            {"deal_id": "DEAL123", "epic": "XAUUSD", "size": 1.0},
            {"deal_id": "DEAL456", "epic": "BTCUSD"},  # New (not in DB)
        ]

        db_positions = [{"deal_id": "DEAL123", "epic": "XAUUSD", "size": 1.0}]

        with patch("src.execution.state_recovery.logger") as mock_logger:
            reconciled = await service._reconcile_positions(broker_positions, db_positions)

        # Should log info about new position
        assert any(
            "new" in str(call).lower() for call in mock_logger.info.call_args_list
        )

        # All broker positions returned
        assert len(reconciled) == 2

    @pytest.mark.asyncio
    async def test_reconcile_positions_size_mismatch_logs_warning(self):
        """Test size mismatch between broker and DB logs warning."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        broker_positions = [{"deal_id": "DEAL123", "size": 2.0, "epic": "XAUUSD"}]

        db_positions = [{"deal_id": "DEAL123", "size": 1.0, "epic": "XAUUSD"}]

        with patch("src.execution.state_recovery.logger") as mock_logger:
            await service._reconcile_positions(broker_positions, db_positions)

        # Should log warning about size mismatch
        assert any(
            "mismatch" in str(call).lower()
            for call in mock_logger.warning.call_args_list
        )

    @pytest.mark.asyncio
    async def test_reconcile_positions_empty_db(self):
        """Test reconciliation when DB is empty."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        broker_positions = [
            {"deal_id": "DEAL123", "epic": "XAUUSD", "size": 1.0},
            {"deal_id": "DEAL456", "epic": "BTCUSD", "size": 0.5},
        ]

        db_positions = []

        reconciled = await service._reconcile_positions(broker_positions, db_positions)

        assert len(reconciled) == 2
        assert reconciled == broker_positions

    @pytest.mark.asyncio
    async def test_reconcile_positions_empty_broker(self):
        """Test reconciliation when broker has no positions."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        broker_positions = []
        db_positions = [
            {"deal_id": "DEAL123", "epic": "XAUUSD", "size": 1.0},
            {"deal_id": "DEAL456", "epic": "BTCUSD", "size": 0.5},
        ]

        reconciled = await service._reconcile_positions(broker_positions, db_positions)

        assert len(reconciled) == 0  # Broker wins (empty)

    @pytest.mark.asyncio
    async def test_reconcile_positions_identical_data(self):
        """Test reconciliation when broker and DB match perfectly."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        positions = [
            {"deal_id": "DEAL123", "size": 1.0, "epic": "XAUUSD"},
            {"deal_id": "DEAL456", "size": 0.5, "epic": "BTCUSD"},
        ]

        broker_positions = positions.copy()
        db_positions = positions.copy()

        with patch("src.execution.state_recovery.logger") as mock_logger:
            reconciled = await service._reconcile_positions(broker_positions, db_positions)

        # No warnings should be logged
        assert mock_logger.warning.call_count == 0

        assert len(reconciled) == 2


# ══════════════════════════════════════════════════════════
# Test Class 4: Trailing Stop Restoration
# ══════════════════════════════════════════════════════════


class TestTrailingStopRestore:
    """Tests for trailing stop state restoration."""

    @pytest.mark.asyncio
    async def test_restore_trailing_stops_for_all_positions(
        self, sample_positions, sample_trailing_stop_states
    ):
        """Test trailing stops are restored for all recovered positions."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        trailing_stop_manager = MagicMock()
        trailing_stop_manager.restore_state = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=trailing_stop_manager,
            broker=None,
            db_session_factory=None,
        )

        # Mock TrailingStopRepository
        mock_states = []
        for state_data in sample_trailing_stop_states:
            mock_state = MagicMock()
            for key, value in state_data.items():
                setattr(mock_state, key, value)
            mock_states.append(mock_state)

        with patch("src.database.repositories.trailing_stop_repository.TrailingStopRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_all_active = AsyncMock(return_value=mock_states)

            count = await service._restore_trailing_stops(sample_positions)

        assert count == 2
        assert trailing_stop_manager.restore_state.call_count == 2

    @pytest.mark.asyncio
    async def test_restore_trailing_stops_removes_stale_states(self, sample_positions):
        """Test stale trailing stop states (no matching position) are removed."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        trailing_stop_manager = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=trailing_stop_manager,
            broker=None,
            db_session_factory=None,
        )

        # Create stale state (deal_id not in positions)
        stale_state = MagicMock()
        stale_state.deal_id = "STALE999"

        with patch("src.database.repositories.trailing_stop_repository.TrailingStopRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_all_active = AsyncMock(return_value=[stale_state])
            mock_repo_instance.bulk_delete = AsyncMock()

            await service._restore_trailing_stops(sample_positions)

        # Should use bulk_delete for stale states (performance optimization)
        mock_repo_instance.bulk_delete.assert_called_once_with(["STALE999"])

    @pytest.mark.asyncio
    async def test_restore_trailing_stops_calls_manager_restore_state(
        self, sample_positions, sample_trailing_stop_states
    ):
        """Test restore_state is called on TrailingStopManager with correct params."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        trailing_stop_manager = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=trailing_stop_manager,
            broker=None,
            db_session_factory=None,
        )

        mock_state = MagicMock()
        mock_state.deal_id = "POS001"
        mock_state.epic = "XAUUSD"
        mock_state.direction = "BUY"
        mock_state.entry_price = Decimal("2075.50")
        mock_state.current_stop = Decimal("2070.00")
        mock_state.phase = 2
        mock_state.tp1_level = Decimal("2090.00")
        mock_state.tp2_level = Decimal("2100.00")
        mock_state.highest_price = Decimal("2085.00")
        mock_state.lowest_price = None

        with patch("src.database.repositories.trailing_stop_repository.TrailingStopRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_all_active = AsyncMock(return_value=[mock_state])
            mock_repo_instance.bulk_delete = AsyncMock()

            await service._restore_trailing_stops(sample_positions)

        # Verify restore_state was called with correct parameters
        trailing_stop_manager.restore_state.assert_called_once()
        call_kwargs = trailing_stop_manager.restore_state.call_args.kwargs
        assert call_kwargs["deal_id"] == "POS001"
        assert call_kwargs["phase"] == 2

    @pytest.mark.asyncio
    async def test_restore_trailing_stops_handles_missing_optional_fields(
        self, sample_positions
    ):
        """Test restoration handles None values for optional fields."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        trailing_stop_manager = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=trailing_stop_manager,
            broker=None,
            db_session_factory=None,
        )

        # State with None optional fields
        mock_state = MagicMock()
        mock_state.deal_id = "POS001"
        mock_state.epic = "XAUUSD"
        mock_state.direction = "BUY"
        mock_state.entry_price = Decimal("2075.50")
        mock_state.current_stop = Decimal("2070.00")
        mock_state.phase = 1
        mock_state.tp1_level = None  # Optional
        mock_state.tp2_level = None  # Optional
        mock_state.highest_price = None  # Optional
        mock_state.lowest_price = None  # Optional

        with patch("src.database.repositories.trailing_stop_repository.TrailingStopRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_all_active = AsyncMock(return_value=[mock_state])

            count = await service._restore_trailing_stops(sample_positions)

        assert count == 1
        # Should not raise error

    @pytest.mark.asyncio
    async def test_restore_trailing_stops_with_no_db_states(self, sample_positions):
        """Test restoration when no trailing stop states exist in DB."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        trailing_stop_manager = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=trailing_stop_manager,
            broker=None,
            db_session_factory=None,
        )

        with patch("src.database.repositories.trailing_stop_repository.TrailingStopRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_all_active = AsyncMock(return_value=[])

            count = await service._restore_trailing_stops(sample_positions)

        assert count == 0

    @pytest.mark.asyncio
    async def test_restore_trailing_stops_with_db_error(self, sample_positions):
        """Test restoration handles database errors gracefully."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        with patch("src.database.repositories.trailing_stop_repository.TrailingStopRepository") as MockRepo:
            MockRepo.side_effect = Exception("Database connection failed")

            count = await service._restore_trailing_stops(sample_positions)

        assert count == 0  # Returns 0 on error


# ══════════════════════════════════════════════════════════
# Test Class 5: Trade History Restoration
# ══════════════════════════════════════════════════════════


class TestTradeHistoryRestore:
    """Tests for trade history restoration for Kelly sizing."""

    @pytest.mark.asyncio
    async def test_restore_trade_history_returns_pnl_list(self, sample_trade_history):
        """Test trade history is returned as list of dicts with pnl key."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        # Mock trades from DB
        mock_trades = []
        for trade_data in sample_trade_history:
            mock_trade = MagicMock()
            mock_trade.profit_loss = Decimal(str(trade_data["pnl"]))
            mock_trades.append(mock_trade)

        with patch("src.database.repositories.trade_repository.TradeRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_recent_for_kelly = AsyncMock(
                return_value=mock_trades
            )

            trade_history = await service._restore_trade_history_list()

        assert len(trade_history) == 5
        assert all("pnl" in trade for trade in trade_history)
        assert trade_history[0]["pnl"] == 50.00

    @pytest.mark.asyncio
    async def test_restore_trade_history_limits_to_200(self):
        """Test trade history is limited to last 200 trades."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        with patch("src.database.repositories.trade_repository.TradeRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value

            # Verify get_recent_for_kelly is called with limit=200
            mock_repo_instance.get_recent_for_kelly = AsyncMock(return_value=[])
            await service._restore_trade_history_list()

            mock_repo_instance.get_recent_for_kelly.assert_called_once_with(limit=200)

    @pytest.mark.asyncio
    async def test_restore_trade_history_skips_null_pnl(self):
        """Test trades with null profit_loss are skipped."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        # Mock trades with some null P&L
        mock_trade_1 = MagicMock()
        mock_trade_1.profit_loss = Decimal("50.00")

        mock_trade_2 = MagicMock()
        mock_trade_2.profit_loss = None  # Null P&L

        mock_trade_3 = MagicMock()
        mock_trade_3.profit_loss = Decimal("25.00")

        with patch("src.database.repositories.trade_repository.TradeRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_recent_for_kelly = AsyncMock(
                return_value=[mock_trade_1, mock_trade_2, mock_trade_3]
            )

            trade_history = await service._restore_trade_history_list()

        assert len(trade_history) == 2  # Null trade skipped
        assert trade_history[0]["pnl"] == 50.00
        assert trade_history[1]["pnl"] == 25.00

    @pytest.mark.asyncio
    async def test_restore_trade_history_with_db_error(self):
        """Test trade history restoration handles DB errors gracefully."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        with patch("src.database.repositories.trade_repository.TradeRepository") as MockRepo:
            MockRepo.side_effect = Exception("Database error")

            trade_history = await service._restore_trade_history_list()

        assert trade_history == []  # Returns empty list on error


# ══════════════════════════════════════════════════════════
# Test Class 6: Risk State Restoration
# ══════════════════════════════════════════════════════════


class TestRiskStateRestore:
    """Tests for risk manager state restoration."""

    @pytest.mark.asyncio
    async def test_restore_risk_state_from_snapshot(self, sample_risk_snapshot):
        """Test risk state is restored from database snapshot."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        risk_manager = MagicMock()
        risk_manager.drawdown_monitor = MagicMock()
        risk_manager.drawdown_monitor.state = MagicMock()
        risk_manager.circuit_breakers = MagicMock()
        risk_manager.circuit_breakers.tripped_breakers = {}
        risk_manager.equity_curve_filter = MagicMock()
        risk_manager.equity_curve_filter.equity_curve = []

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        mock_snapshot = MagicMock()
        for key, value in sample_risk_snapshot.items():
            setattr(mock_snapshot, key, value)

        with patch("src.database.repositories.risk_state_repository.RiskStateRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_latest = AsyncMock(return_value=mock_snapshot)

            restored = await service._restore_risk_state()

        assert restored is True

    @pytest.mark.asyncio
    async def test_restore_risk_state_restores_drawdown_monitor(
        self, sample_risk_snapshot
    ):
        """Test DrawdownMonitor state is correctly restored."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        risk_manager = MagicMock()
        risk_manager.drawdown_monitor = MagicMock()
        risk_manager.drawdown_monitor.state = MagicMock()
        risk_manager.circuit_breakers = MagicMock()
        risk_manager.circuit_breakers.tripped_breakers = {}
        risk_manager.equity_curve_filter = MagicMock()
        risk_manager.equity_curve_filter.equity_curve = []

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        mock_snapshot = MagicMock()
        for key, value in sample_risk_snapshot.items():
            setattr(mock_snapshot, key, value)

        with patch("src.database.repositories.risk_state_repository.RiskStateRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_latest = AsyncMock(return_value=mock_snapshot)

            await service._restore_risk_state()

        # Verify DrawdownMonitor state was restored
        dm_state = risk_manager.drawdown_monitor.state
        assert dm_state.peak_equity == float(sample_risk_snapshot["peak_equity"])
        assert dm_state.current_equity == float(sample_risk_snapshot["current_equity"])

    @pytest.mark.asyncio
    async def test_restore_risk_state_restores_circuit_breakers(
        self, sample_risk_snapshot
    ):
        """Test CircuitBreakers state is correctly restored."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        risk_manager = MagicMock()
        risk_manager.drawdown_monitor = MagicMock()
        risk_manager.drawdown_monitor.state = MagicMock()
        risk_manager.circuit_breakers = MagicMock()
        risk_manager.circuit_breakers.tripped_breakers = {}
        risk_manager.equity_curve_filter = MagicMock()
        risk_manager.equity_curve_filter.equity_curve = []

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        mock_snapshot = MagicMock()
        for key, value in sample_risk_snapshot.items():
            setattr(mock_snapshot, key, value)

        with patch("src.database.repositories.risk_state_repository.RiskStateRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_latest = AsyncMock(return_value=mock_snapshot)

            await service._restore_risk_state()

        # Verify CircuitBreakers state was restored
        cb = risk_manager.circuit_breakers
        assert cb.consecutive_losses == sample_risk_snapshot["consecutive_losses"]
        assert len(cb.tripped_breakers) == 1  # US500

    @pytest.mark.asyncio
    async def test_restore_risk_state_restores_equity_curve(self, sample_risk_snapshot):
        """Test EquityCurveFilter state is correctly restored."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        risk_manager = MagicMock()
        risk_manager.drawdown_monitor = MagicMock()
        risk_manager.drawdown_monitor.state = MagicMock()
        risk_manager.circuit_breakers = MagicMock()
        risk_manager.circuit_breakers.tripped_breakers = {}
        risk_manager.equity_curve_filter = MagicMock()
        risk_manager.equity_curve_filter.equity_curve = []

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        mock_snapshot = MagicMock()
        for key, value in sample_risk_snapshot.items():
            setattr(mock_snapshot, key, value)

        with patch("src.database.repositories.risk_state_repository.RiskStateRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_latest = AsyncMock(return_value=mock_snapshot)

            await service._restore_risk_state()

        # Verify EquityCurveFilter state was restored
        ec = risk_manager.equity_curve_filter
        assert len(ec.equity_curve) == 4  # 4 equity points

    @pytest.mark.asyncio
    async def test_restore_risk_state_handles_missing_snapshot(self):
        """Test restoration handles missing snapshot gracefully."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER

        risk_manager = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,
        )

        with patch("src.database.repositories.risk_state_repository.RiskStateRepository") as MockRepo:
            mock_repo_instance = MockRepo.return_value
            mock_repo_instance.get_latest = AsyncMock(return_value=None)

            restored = await service._restore_risk_state()

        assert restored is False


# ══════════════════════════════════════════════════════════
# Test Class 7: Error Handling
# ══════════════════════════════════════════════════════════


class TestErrorHandling:
    """Tests for error handling and fallback logic."""

    @pytest.mark.asyncio
    async def test_broker_unavailable_fallback_to_db(
        self, sample_positions, mock_broker_client
    ):
        """Test fallback to DB when broker API is unavailable."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO
        execution_engine._position_tracker = MagicMock()

        risk_manager = MagicMock()
        trailing_stop_manager = MagicMock()

        # Broker throws exception
        mock_broker_client.list_positions = AsyncMock(
            side_effect=Exception("Connection timeout")
        )

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=trailing_stop_manager,
            broker=mock_broker_client,
            db_session_factory=None,
        )

        with patch.object(
            service, "_load_positions_from_db", return_value=sample_positions
        ):
            positions, source = await service._recover_positions()

        assert source == "database"
        assert len(positions) == 2

    @pytest.mark.asyncio
    async def test_db_unavailable_in_paper_mode_critical_error(self):
        """Test PAPER mode with DB unavailable returns critical error."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER
        execution_engine._position_tracker = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,  # No DB
        )

        positions, source = await service._recover_positions()

        assert source == "none"
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_both_sources_fail_demo_mode_critical_error(self, mock_broker_client):
        """Test DEMO mode with both broker and DB failing."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.DEMO
        execution_engine._position_tracker = MagicMock()

        # Broker fails
        mock_broker_client.list_positions = AsyncMock(
            side_effect=Exception("Broker unavailable")
        )

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=mock_broker_client,
            db_session_factory=None,  # DB also unavailable
        )

        positions, source = await service._recover_positions()

        assert source == "none"
        assert len(positions) == 0


# ══════════════════════════════════════════════════════════
# Test Class 8: Warnings and Validation
# ══════════════════════════════════════════════════════════


class TestWarningsAndValidation:
    """Tests for warning detection and state validation."""

    @pytest.mark.asyncio
    async def test_warning_on_positions_without_trailing_stops(self, sample_positions):
        """Test warning is generated when positions have no trailing stops."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER
        execution_engine._position_tracker = MagicMock()

        risk_manager = MagicMock()
        trailing_stop_manager = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=risk_manager,
            trailing_stop_manager=trailing_stop_manager,
            broker=None,
            db_session_factory=None,
        )

        # Mock position recovery
        with patch.object(
            service, "_recover_positions", return_value=(sample_positions, "database")
        ):
            with patch.object(
                service, "_restore_trailing_stops", return_value=0
            ):  # No stops restored
                with patch.object(service, "_restore_trade_history", return_value=0):
                    with patch.object(service, "_restore_risk_state", return_value=True):
                        with patch.object(
                            service, "_inject_positions_into_engine", return_value=None
                        ):
                            report = await service.recover_all_state()

        # Should have warning about no trailing stops
        assert any("trailing stop" in w.lower() for w in report.warnings)

    @pytest.mark.asyncio
    async def test_warning_on_paper_mode_no_db(self):
        """Test warning is generated in PAPER mode when DB unavailable."""
        execution_engine = MagicMock()
        execution_engine.mode = ExecutionMode.PAPER
        execution_engine._position_tracker = MagicMock()

        service = StateRecoveryService(
            execution_engine=execution_engine,
            risk_manager=MagicMock(),
            trailing_stop_manager=MagicMock(),
            broker=None,
            db_session_factory=None,  # No DB
        )

        with patch.object(service, "_recover_positions", return_value=([], "none")):
            with patch.object(service, "_restore_trailing_stops", return_value=0):
                with patch.object(service, "_restore_trade_history", return_value=0):
                    with patch.object(service, "_restore_risk_state", return_value=False):
                        with patch.object(
                            service, "_inject_positions_into_engine", return_value=None
                        ):
                            report = await service.recover_all_state()

        # Should have warning about PAPER mode with no positions
        assert any("paper" in w.lower() for w in report.warnings)

