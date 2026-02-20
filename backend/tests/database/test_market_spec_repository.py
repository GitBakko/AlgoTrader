"""Tests for MarketSpecRepository."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.database.models import MarketSpec
from src.database.repositories.market_spec_repository import MarketSpecRepository


@pytest.fixture
def mock_session():
    """Mock async SQLAlchemy session."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def repo(mock_session):
    """MarketSpecRepository with mocked session."""
    return MarketSpecRepository(mock_session)


def _make_spec(epic="GOLD", environment="DEMO", min_deal_size=0.01):
    """Create a MarketSpec model instance."""
    return MarketSpec(
        id=1,
        epic=epic,
        environment=environment,
        min_deal_size=Decimal(str(min_deal_size)),
        min_deal_size_unit="UNITS",
        max_deal_size=Decimal("500.0"),
        market_name="Gold",
    )


def _mock_scalar_result(value):
    """Mock session.execute() result for scalar_one_or_none()."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _mock_scalars_result(values):
    """Mock session.execute() result for scalars().all()."""
    result = MagicMock()
    scalars_mock = MagicMock()
    scalars_mock.all.return_value = values
    result.scalars.return_value = scalars_mock
    return result


class TestGetByEpic:
    @pytest.mark.asyncio
    async def test_get_by_epic_found(self, repo, mock_session):
        spec = _make_spec()
        mock_session.execute.return_value = _mock_scalar_result(spec)
        result = await repo.get_by_epic("GOLD", "DEMO")
        assert result is spec
        mock_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_epic_not_found(self, repo, mock_session):
        mock_session.execute.return_value = _mock_scalar_result(None)
        result = await repo.get_by_epic("GOLD", "DEMO")
        assert result is None


class TestGetAllForEnvironment:
    @pytest.mark.asyncio
    async def test_get_all_empty(self, repo, mock_session):
        mock_session.execute.return_value = _mock_scalars_result([])
        result = await repo.get_all_for_environment("DEMO")
        assert result == []

    @pytest.mark.asyncio
    async def test_get_all_with_data(self, repo, mock_session):
        specs = [
            _make_spec("GOLD", "DEMO", 0.01),
            _make_spec("BTCUSD", "DEMO", 0.1),
        ]
        mock_session.execute.return_value = _mock_scalars_result(specs)
        result = await repo.get_all_for_environment("DEMO")
        assert len(result) == 2


class TestUpsert:
    @pytest.mark.asyncio
    async def test_upsert_create_new(self, repo, mock_session):
        """No existing spec -> creates new one."""
        mock_session.execute.return_value = _mock_scalar_result(None)
        result = await repo.upsert("GOLD", "DEMO", 0.01)
        assert result.epic == "GOLD"
        assert result.environment == "DEMO"
        assert result.min_deal_size == Decimal("0.01")
        mock_session.add.assert_called_once()
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_update_existing(self, repo, mock_session):
        """Existing spec -> updates in place."""
        existing = _make_spec("GOLD", "DEMO", 0.01)
        mock_session.execute.return_value = _mock_scalar_result(existing)
        result = await repo.upsert("GOLD", "DEMO", 0.05, market_name="Gold Updated")
        assert result.min_deal_size == Decimal("0.05")
        assert result.market_name == "Gold Updated"
        mock_session.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upsert_with_max_deal_size(self, repo, mock_session):
        """Creates spec with max deal size."""
        mock_session.execute.return_value = _mock_scalar_result(None)
        result = await repo.upsert("GOLD", "DEMO", 0.01, max_deal_size=1000.0)
        assert result.max_deal_size == Decimal("1000.0")


class TestBulkUpsert:
    @pytest.mark.asyncio
    async def test_bulk_upsert(self, repo, mock_session):
        """Bulk upsert processes all specs."""
        # Each upsert call triggers an execute (get_by_epic) then flush
        mock_session.execute.return_value = _mock_scalar_result(None)
        specs = [
            {"epic": "GOLD", "min_deal_size": 0.01, "market_name": "Gold"},
            {"epic": "BTCUSD", "min_deal_size": 0.1, "market_name": "Bitcoin"},
        ]
        count = await repo.bulk_upsert(specs, "DEMO")
        assert count == 2
        assert mock_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_bulk_upsert_empty(self, repo, mock_session):
        count = await repo.bulk_upsert([], "DEMO")
        assert count == 0
