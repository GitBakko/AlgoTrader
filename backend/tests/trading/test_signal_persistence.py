"""Integration tests for signal audit trail persistence."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock


class TestSignalRepositoryAuditMethods:
    """Tests for new SignalRepository methods needed by the audit trail."""

    @pytest.mark.asyncio
    async def test_create_from_audit_returns_id(self):
        """create_from_audit() should INSERT and return the new signal ID."""
        from src.database.repositories.signal_repository import SignalRepository
        from src.database.models import Signal

        mock_session = AsyncMock()
        repo = SignalRepository(mock_session)

        # Mock the add + flush + refresh cycle
        async def mock_flush():
            pass

        async def mock_refresh(obj):
            obj.id = 42  # Simulate DB-assigned ID

        mock_session.flush = mock_flush
        mock_session.refresh = mock_refresh
        mock_session.add = MagicMock()

        features = {"version": 1, "votes": {"ema": {"value": 1}}}
        signal_id = await repo.create_from_audit(
            epic="XAUUSD", direction="BUY", confidence=0.67,
            entry_price=2047.5, stop_loss=2035.0, take_profit=2060.0,
            status="EXECUTED", features=features,
        )

        assert signal_id == 42
        mock_session.add.assert_called_once()
        added_signal = mock_session.add.call_args[0][0]
        assert isinstance(added_signal, Signal)
        assert added_signal.epic == "XAUUSD"
        assert added_signal.features == features
        assert added_signal.model_version == "scalp_score_v1"

    @pytest.mark.asyncio
    async def test_create_from_audit_rejected_signal(self):
        """create_from_audit() with REJECTED status should store rejection reason in features."""
        from src.database.repositories.signal_repository import SignalRepository

        mock_session = AsyncMock()
        repo = SignalRepository(mock_session)

        async def mock_flush():
            pass

        async def mock_refresh(obj):
            obj.id = 99

        mock_session.flush = mock_flush
        mock_session.refresh = mock_refresh
        mock_session.add = MagicMock()

        features = {
            "version": 1,
            "votes": {"ema": {"value": 1}},
            "rejection_reason": "Confidence too low",
        }
        signal_id = await repo.create_from_audit(
            epic="BTCUSD", direction="SELL", confidence=0.20,
            entry_price=50000.0, stop_loss=None, take_profit=None,
            status="REJECTED", features=features,
        )

        assert signal_id == 99
        added = mock_session.add.call_args[0][0]
        assert added.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_get_history_by_epic(self):
        """get_history_by_epic() should return lightweight signal list."""
        from src.database.repositories.signal_repository import SignalRepository

        mock_session = AsyncMock()
        repo = SignalRepository(mock_session)

        mock_result = MagicMock()
        mock_result.all.return_value = [
            MagicMock(
                id=42, direction="BUY", confidence=Decimal("0.6700"),
                status="EXECUTED",
                generated_at=datetime(2026, 3, 11, 14, 23),
                rejection_reason=None, position_pnl=Decimal("14.40"),
                position_status="OPEN",
            ),
        ]
        mock_session.execute.return_value = mock_result

        history = await repo.get_history_by_epic("XAUUSD", limit=10, offset=0)
        assert len(history) == 1
        assert history[0]["id"] == 42
        assert history[0]["direction"] == "BUY"

    @pytest.mark.asyncio
    async def test_count_by_epic(self):
        """count_by_epic() should return signal count."""
        from src.database.repositories.signal_repository import SignalRepository

        mock_session = AsyncMock()
        repo = SignalRepository(mock_session)

        mock_result = MagicMock()
        mock_result.scalar.return_value = 15
        mock_session.execute.return_value = mock_result

        count = await repo.count_by_epic("XAUUSD")
        assert count == 15
