"""Tests for market spec pre-fetch service."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.trading.market_spec_prefetch import (
    load_market_specs_from_db,
    prefetch_market_specs,
)


def _make_market_info(min_val, max_val=500.0, name="Test Market"):
    """Create a mock market info response from Capital.com."""
    return {
        "dealingRules": {
            "minDealSize": {"value": min_val, "unit": "UNITS"},
            "maxDealSize": {"value": max_val, "unit": "UNITS"},
        },
        "instrument": {"name": name},
    }


@pytest.fixture
def mock_broker():
    broker = AsyncMock()
    broker.get_market_details = AsyncMock()
    return broker


class TestPrefetchMarketSpecs:
    @pytest.mark.asyncio
    async def test_prefetch_all_success(self, mock_broker):
        """All assets fetched successfully."""
        mock_broker.get_market_details.return_value = _make_market_info(0.01)

        result = await prefetch_market_specs(
            mock_broker, db_session_factory=None, batch_size=5, delay_between_batches=0
        )

        assert len(result) > 0
        for epic, size in result.items():
            assert size == 0.01

    @pytest.mark.asyncio
    async def test_prefetch_partial_failure(self, mock_broker):
        """Some assets fail, others succeed."""
        call_count = 0

        async def _side_effect(epic):
            nonlocal call_count
            call_count += 1
            if call_count % 3 == 0:
                raise Exception("API timeout")
            return _make_market_info(0.5, name=epic)

        mock_broker.get_market_details.side_effect = _side_effect

        result = await prefetch_market_specs(
            mock_broker, db_session_factory=None, batch_size=5, delay_between_batches=0
        )

        # At least some succeeded, but not all
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_prefetch_all_fail(self, mock_broker):
        """All assets fail gracefully."""
        mock_broker.get_market_details.side_effect = Exception("Connection error")

        result = await prefetch_market_specs(
            mock_broker, db_session_factory=None, batch_size=5, delay_between_batches=0
        )

        assert result == {}

    @pytest.mark.asyncio
    async def test_prefetch_with_db_persistence(self, mock_broker):
        """Pre-fetch persists to DB when session factory available."""
        mock_broker.get_market_details.return_value = _make_market_info(0.01)

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()

        mock_repo = AsyncMock()
        mock_repo.bulk_upsert = AsyncMock(return_value=21)

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.database.repositories.market_spec_repository.MarketSpecRepository",
            return_value=mock_repo,
        ):
            result = await prefetch_market_specs(
                mock_broker,
                db_session_factory=mock_factory,
                batch_size=10,
                delay_between_batches=0,
            )

        assert len(result) > 0
        mock_repo.bulk_upsert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_prefetch_missing_min_deal_size(self, mock_broker):
        """Assets without minDealSize.value are excluded from results."""
        mock_broker.get_market_details.return_value = {
            "dealingRules": {"minDealSize": {}, "maxDealSize": {}},
            "instrument": {"name": "No Min"},
        }

        result = await prefetch_market_specs(
            mock_broker, db_session_factory=None, batch_size=5, delay_between_batches=0
        )

        assert result == {}


class TestLoadMarketSpecsFromDb:
    @pytest.mark.asyncio
    async def test_load_no_db(self):
        """Returns empty dict when no DB available."""
        result = await load_market_specs_from_db(None, "DEMO")
        assert result == {}

    @pytest.mark.asyncio
    async def test_load_from_db(self):
        """Loads specs from DB successfully."""
        from decimal import Decimal

        mock_spec1 = MagicMock()
        mock_spec1.epic = "GOLD"
        mock_spec1.min_deal_size = Decimal("0.01")

        mock_spec2 = MagicMock()
        mock_spec2.epic = "BTCUSD"
        mock_spec2.min_deal_size = Decimal("0.1")

        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_repo = AsyncMock()
        mock_repo.get_all_for_environment = AsyncMock(
            return_value=[mock_spec1, mock_spec2]
        )

        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        with patch(
            "src.database.repositories.market_spec_repository.MarketSpecRepository",
            return_value=mock_repo,
        ):
            result = await load_market_specs_from_db(mock_factory, "DEMO")

        assert result == {"GOLD": 0.01, "BTCUSD": 0.1}

    @pytest.mark.asyncio
    async def test_load_db_error(self):
        """Returns empty dict on DB error."""
        mock_factory = MagicMock()
        mock_factory.return_value.__aenter__ = AsyncMock(
            side_effect=Exception("DB down")
        )
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await load_market_specs_from_db(mock_factory, "DEMO")
        assert result == {}


class TestPaperLoopIntegration:
    """Test seed_min_deal_sizes and fallback chain in PaperTradingLoop."""

    @pytest.fixture
    def paper_loop(self):
        from src.execution.execution_engine import ExecutionEngine
        from src.execution.schemas import ExecutionMode
        from src.risk.risk_manager import RiskManager
        from src.risk.schemas import RiskLimits
        from src.strategy.strategy_manager import StrategyManager
        from src.trading.paper_loop import PaperTradingLoop

        service = MagicMock()
        service.has_models = True
        service.get_loaded_models.return_value = {}

        return PaperTradingLoop(
            prediction_service=service,
            strategy_manager=StrategyManager(),
            risk_manager=RiskManager(initial_equity=10000.0, limits=RiskLimits()),
            execution_engine=ExecutionEngine(mode=ExecutionMode.PAPER),
            interval_seconds=1,
            epics=["XAUUSD"],
        )

    def test_seed_min_deal_sizes(self, paper_loop):
        """seed_min_deal_sizes populates the cache."""
        assert paper_loop._min_deal_size_cache == {}
        paper_loop.seed_min_deal_sizes({"GOLD": 0.01, "BTCUSD": 0.1})
        assert paper_loop._min_deal_size_cache == {"GOLD": 0.01, "BTCUSD": 0.1}

    def test_seed_min_deal_sizes_updates(self, paper_loop):
        """seed_min_deal_sizes merges with existing cache."""
        paper_loop.seed_min_deal_sizes({"GOLD": 0.01})
        paper_loop.seed_min_deal_sizes({"BTCUSD": 0.1})
        assert paper_loop._min_deal_size_cache == {"GOLD": 0.01, "BTCUSD": 0.1}

    def test_get_min_deal_size_from_dedicated_cache(self, paper_loop):
        """Fallback to _min_deal_size_cache when no market info."""
        paper_loop._min_deal_size_cache["GOLD"] = 0.01
        result = paper_loop._get_min_deal_size("GOLD")
        assert result == 0.01

    def test_get_min_deal_size_from_market_info_cache(self, paper_loop):
        """Market info cache takes precedence."""
        paper_loop._market_info_cache["GOLD"] = {
            "dealingRules": {"minDealSize": {"value": 0.05}}
        }
        paper_loop._min_deal_size_cache["GOLD"] = 0.01  # Should be ignored
        result = paper_loop._get_min_deal_size("GOLD")
        assert result == 0.05

    def test_get_min_deal_size_none(self, paper_loop):
        """Returns None when no cache data available."""
        result = paper_loop._get_min_deal_size("UNKNOWN_EPIC")
        assert result is None

    def test_get_status_includes_cache_count(self, paper_loop):
        """get_status includes min_deal_sizes_cached field."""
        paper_loop.seed_min_deal_sizes({"GOLD": 0.01, "BTCUSD": 0.1})
        status = paper_loop.get_status()
        assert status["min_deal_sizes_cached"] == 2
