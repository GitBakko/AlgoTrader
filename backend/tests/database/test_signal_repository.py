"""Tests for SignalRepository."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.repositories.signal_repository import SignalRepository


@pytest.fixture
def mock_session():
    """Mock async SQLAlchemy session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo(mock_session):
    return SignalRepository(mock_session)


class TestCreateFromAudit:
    @pytest.mark.asyncio
    async def test_persists_passed_timeframe(self, repo, mock_session):
        """The loop's real decision resolution must be persisted, not hardcoded.

        Regression guard for the mislabel bug: signals were always written with
        timeframe="15min" even after the loop moved to 4h.
        """
        await repo.create_from_audit(
            epic="BTCUSD",
            direction="BUY",
            confidence=0.62,
            entry_price=60000.0,
            stop_loss=59000.0,
            take_profit=61000.0,
            status="EXECUTED",
            features={},
            timeframe="4h",
            model_version="ScalpScore",
        )
        mock_session.add.assert_called_once()
        persisted = mock_session.add.call_args.args[0]
        assert persisted.timeframe == "4h"
        assert persisted.model_version == "ScalpScore"
        assert persisted.epic == "BTCUSD"
        assert persisted.direction == "BUY"

    @pytest.mark.asyncio
    async def test_timeframe_defaults_to_15min_for_legacy_callers(self, repo, mock_session):
        await repo.create_from_audit(
            epic="ETHUSD",
            direction="SELL",
            confidence=0.5,
            entry_price=3000.0,
            stop_loss=3030.0,
            take_profit=2970.0,
            status="REJECTED",
            features={},
        )
        persisted = mock_session.add.call_args.args[0]
        assert persisted.timeframe == "15min"
        assert persisted.model_version == "unknown"
