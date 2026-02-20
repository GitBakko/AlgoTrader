"""Tests for Export API router (GET /api/export/positions/csv)."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.dependencies import get_position_repo
from src.api.main import app


def _make_position(**overrides):
    """Create a mock position object with sensible defaults."""
    p = MagicMock()
    p.deal_id = overrides.get("deal_id", "DEAL_001")
    p.epic = overrides.get("epic", "GOLD")
    p.direction = overrides.get("direction", "BUY")
    p.size = overrides.get("size", 0.5)
    p.entry_price = overrides.get("entry_price", 2050.0)
    p.current_price = overrides.get("current_price", 2060.0)
    p.profit_loss = overrides.get("profit_loss", 5.0)
    p.stop_loss = overrides.get("stop_loss", 2040.0)
    p.take_profit = overrides.get("take_profit", 2070.0)
    p.close_reason = overrides.get("close_reason", "TP")
    p.opened_at = overrides.get("opened_at", datetime(2026, 2, 19, 10, 0, 0))
    p.closed_at = overrides.get("closed_at", datetime(2026, 2, 19, 12, 0, 0))
    return p


@pytest.fixture
def mock_position_repo():
    """Mock PositionRepository with get_closed_positions."""
    repo = AsyncMock()
    repo.get_closed_positions = AsyncMock(return_value=([], 0))
    return repo


@pytest.fixture
def export_client(client, mock_position_repo):
    """Client with position repo override."""
    app.dependency_overrides[get_position_repo] = lambda: mock_position_repo
    yield client


class TestExportPositionsCSV:
    def test_export_csv_empty(self, export_client, mock_position_repo):
        """No positions → CSV with headers only."""
        mock_position_repo.get_closed_positions.return_value = ([], 0)
        resp = export_client.get("/api/export/positions/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "Content-Disposition" in resp.headers
        assert "attachment" in resp.headers["Content-Disposition"]

        content = resp.text
        # BOM + header row
        lines = content.strip().split("\n")
        assert len(lines) == 1  # header only
        assert "Deal ID" in lines[0]
        assert "Epic" in lines[0]
        assert "P&L" in lines[0]

    def test_export_csv_with_data(self, export_client, mock_position_repo):
        """Positions → CSV with header + data rows."""
        positions = [
            _make_position(deal_id="D1", epic="GOLD", profit_loss=10.0, close_reason="TP"),
            _make_position(deal_id="D2", epic="BTCUSD", profit_loss=-5.0, close_reason="SL"),
        ]
        mock_position_repo.get_closed_positions.return_value = (positions, 2)

        resp = export_client.get("/api/export/positions/csv")
        assert resp.status_code == 200
        content = resp.text
        lines = content.strip().split("\n")
        assert len(lines) == 3  # header + 2 data rows
        assert "GOLD" in lines[1]
        assert "BTCUSD" in lines[2]
        assert "10.0" in lines[1]
        assert "-5.0" in lines[2]

    def test_export_csv_with_filters(self, export_client, mock_position_repo):
        """Query params forwarded to repo."""
        mock_position_repo.get_closed_positions.return_value = ([], 0)

        resp = export_client.get(
            "/api/export/positions/csv",
            params={
                "date_from": "2026-02-01T00:00:00",
                "date_to": "2026-02-19T23:59:59",
                "epic": "GOLD",
                "close_reason": "SL",
            },
        )
        assert resp.status_code == 200
        mock_position_repo.get_closed_positions.assert_awaited_once()
        call_kwargs = mock_position_repo.get_closed_positions.call_args.kwargs
        assert call_kwargs["epic"] == "GOLD"
        assert call_kwargs["close_reason"] == "SL"
        assert call_kwargs["date_from"] == datetime.fromisoformat("2026-02-01T00:00:00")
        assert call_kwargs["date_to"] == datetime.fromisoformat("2026-02-19T23:59:59")

    def test_export_csv_when_repo_none(self, client):
        """No DB → return empty CSV with headers (graceful degradation)."""
        app.dependency_overrides[get_position_repo] = lambda: None
        resp = client.get("/api/export/positions/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        content = resp.text
        lines = content.strip().split("\n")
        assert len(lines) == 1  # header only
        assert "Deal ID" in lines[0]

    def test_export_csv_content_disposition(self, export_client, mock_position_repo):
        """Filename follows mantis_positions_YYYYMMDD_HHMMSS.csv pattern."""
        mock_position_repo.get_closed_positions.return_value = ([], 0)
        resp = export_client.get("/api/export/positions/csv")
        assert resp.status_code == 200
        cd = resp.headers["Content-Disposition"]
        assert "mantis_positions_" in cd
        assert ".csv" in cd

    def test_export_csv_duration_calculation(self, export_client, mock_position_repo):
        """Duration is calculated as (closed_at - opened_at) in minutes."""
        pos = _make_position(
            opened_at=datetime(2026, 2, 19, 10, 0, 0),
            closed_at=datetime(2026, 2, 19, 12, 30, 0),
        )
        mock_position_repo.get_closed_positions.return_value = ([pos], 1)

        resp = export_client.get("/api/export/positions/csv")
        content = resp.text
        lines = content.strip().split("\n")
        assert len(lines) == 2
        # 2.5 hours = 150 minutes
        assert "150" in lines[1]
