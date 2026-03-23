"""Tests for signal audit trail API endpoints."""
import pytest
from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_signal(
    id=1, epic="XAUUSD", direction="BUY", confidence=0.67,
    status="EXECUTED", position_id=None, features=None,
):
    """Create a mock Signal model object."""
    s = MagicMock()
    s.id = id
    s.epic = epic
    s.direction = direction
    s.confidence = Decimal(str(confidence))
    s.status = status
    s.generated_at = datetime(2026, 3, 11, 14, 30)
    s.predicted_price = Decimal("2047.50")
    s.stop_loss_price = Decimal("2035.00")
    s.take_profit_price = Decimal("2060.00")
    s.position_id = position_id
    s.features = features or {"version": 1, "votes": {"ema": {"value": 1}}}
    return s


class TestGetSignalAudit:
    """GET /api/signals/audit/{signal_id}"""

    @pytest.mark.asyncio
    async def test_returns_signal_with_features(self):
        from src.api.routers.signals import get_signal_audit
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = _mock_signal(id=42, features={"version": 1})

        result = await get_signal_audit(signal_id=42, signal_repo=mock_repo)
        assert result["success"] is True
        assert result["data"]["id"] == 42
        assert result["data"]["features"]["version"] == 1
        mock_repo.get_by_id.assert_called_once_with(42)

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(self):
        from src.api.routers.signals import get_signal_audit
        mock_repo = AsyncMock()
        mock_repo.get_by_id.return_value = None

        result = await get_signal_audit(signal_id=999, signal_repo=mock_repo)
        assert result.status_code == 404

    @pytest.mark.asyncio
    async def test_returns_503_without_db(self):
        from src.api.routers.signals import get_signal_audit
        result = await get_signal_audit(signal_id=1, signal_repo=None)
        assert result.status_code == 503


class TestGetSignalByPosition:
    """GET /api/signals/audit/position/{deal_id}"""

    @pytest.mark.asyncio
    async def test_returns_signal_for_deal_id(self):
        from src.api.routers.signals import get_signal_by_position
        mock_repo = AsyncMock()
        mock_repo.get_by_position_deal_id.return_value = _mock_signal(
            id=10, position_id=5,
        )

        result = await get_signal_by_position(deal_id="DEAL-123", signal_repo=mock_repo)
        assert result["success"] is True
        assert result["data"]["id"] == 10
        assert result["data"]["position_id"] == 5
        mock_repo.get_by_position_deal_id.assert_called_once_with("DEAL-123")

    @pytest.mark.asyncio
    async def test_returns_404_when_no_signal(self):
        from src.api.routers.signals import get_signal_by_position
        mock_repo = AsyncMock()
        mock_repo.get_by_position_deal_id.return_value = None
        mock_repo.get_latest_by_epic.return_value = None

        result = await get_signal_by_position(deal_id="NONE", signal_repo=mock_repo)
        # error_response returns JSONResponse with status_code attribute
        assert result.status_code == 404


class TestGetSignalHistory:
    """GET /api/signals/audit/history/{epic}"""

    @pytest.mark.asyncio
    async def test_returns_paginated_history(self):
        from src.api.routers.signals import get_signal_history
        mock_repo = AsyncMock()
        mock_repo.get_history_by_epic.return_value = [
            {"id": 1, "direction": "BUY", "confidence": 0.67, "status": "EXECUTED"},
        ]
        mock_repo.count_by_epic.return_value = 25

        result = await get_signal_history(
            epic="XAUUSD", limit=10, offset=0, signal_repo=mock_repo,
        )
        assert result["success"] is True
        assert len(result["data"]["items"]) == 1
        assert result["data"]["total"] == 25
        assert result["data"]["limit"] == 10

    @pytest.mark.asyncio
    async def test_returns_503_without_db(self):
        from src.api.routers.signals import get_signal_history
        result = await get_signal_history(
            epic="XAUUSD", limit=10, offset=0, signal_repo=None,
        )
        assert result.status_code == 503
