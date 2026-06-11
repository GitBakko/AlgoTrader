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
            model_version="scalp_score_v1",
        )

        assert signal_id == 42
        mock_session.add.assert_called_once()
        added_signal = mock_session.add.call_args[0][0]
        assert isinstance(added_signal, Signal)
        assert added_signal.epic == "XAUUSD"
        assert added_signal.features == features
        # model_version is a pass-through of the producing strategy since the
        # hardcoded "scalp_score_v1" mislabel was fixed; callers omitting it
        # get "unknown".
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


class TestPersistSignalAudit:
    """Tests for PaperTradingLoop._persist_signal_audit helper."""

    def _make_loop(self, signal_repo_factory=None):
        from src.trading.paper_loop import PaperTradingLoop
        return PaperTradingLoop(
            prediction_service=MagicMock(),
            strategy_manager=MagicMock(),
            risk_manager=MagicMock(),
            execution_engine=MagicMock(mode=MagicMock(value="PAPER")),
            signal_repo_factory=signal_repo_factory,
        )

    @pytest.mark.asyncio
    async def test_persist_returns_none_without_factory(self):
        """Without signal_repo_factory, _persist_signal_audit returns None."""
        loop = self._make_loop(signal_repo_factory=None)
        result = await loop._persist_signal_audit(
            epic="XAUUSD", direction="BUY", confidence=0.6,
            entry_price=2050.0, stop_loss=2040.0, take_profit=2060.0,
            status="EXECUTED", features={"version": 1},
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_persist_calls_create_from_audit(self):
        """With factory, _persist_signal_audit creates repo and calls create_from_audit."""
        mock_session = AsyncMock()
        mock_repo_instance = AsyncMock()
        mock_repo_instance.create_from_audit.return_value = 77

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def fake_factory():
            yield mock_session

        # Patch SignalRepository inside the method
        import src.trading.paper_loop as plmod
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else None

        loop = self._make_loop(signal_repo_factory=fake_factory)

        # We need to patch the SignalRepository class that gets imported inside
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                "src.database.repositories.signal_repository.SignalRepository.__init__",
                lambda self, session: setattr(self, 'session', session) or None,
            )
            mp.setattr(
                "src.database.repositories.signal_repository.SignalRepository.create_from_audit",
                mock_repo_instance.create_from_audit,
            )

            result = await loop._persist_signal_audit(
                epic="XAUUSD", direction="BUY", confidence=0.6,
                entry_price=2050.0, stop_loss=2040.0, take_profit=2060.0,
                status="EXECUTED", features={"version": 1},
            )

        assert result == 77
        mock_repo_instance.create_from_audit.assert_called_once()

    @pytest.mark.asyncio
    async def test_persist_swallows_exceptions(self):
        """_persist_signal_audit should never raise — best-effort only."""
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def broken_factory():
            raise RuntimeError("DB is down")
            yield  # noqa: unreachable

        loop = self._make_loop(signal_repo_factory=broken_factory)
        result = await loop._persist_signal_audit(
            epic="XAUUSD", direction="BUY", confidence=0.6,
            entry_price=2050.0, stop_loss=2040.0, take_profit=2060.0,
            status="EXECUTED", features={"version": 1},
        )
        assert result is None  # No crash, returns None
