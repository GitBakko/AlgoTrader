"""Tests for POST /api/trading/emergency-stop endpoint."""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from src.api.main import app
from src.execution.schemas import ExecutionResult


def _make_mock_loop(running: bool, positions: list[dict] | None = None):
    """Create a mock paper loop with configurable state."""
    loop = MagicMock()
    type(loop).is_running = PropertyMock(return_value=running)

    if positions is None:
        positions = []
    loop.get_positions_async = AsyncMock(return_value=positions)
    loop.get_paper_positions = MagicMock(return_value=positions)

    engine = MagicMock()
    engine.close_position = AsyncMock(
        return_value=ExecutionResult(success=True, deal_id="DEAL-001")
    )
    loop.execution_engine = engine

    return loop


@pytest.mark.unit
class TestEmergencyStop:
    """Tests for the emergency stop endpoint."""

    def test_emergency_stop_halts_and_closes(self, client):
        """Emergency stop: stops loop + closes all positions."""
        positions = [
            {"deal_id": "DEAL-001", "epic": "XAUUSD", "direction": "BUY", "size": 0.5},
            {"deal_id": "DEAL-002", "epic": "BTCUSD", "direction": "SELL", "size": 0.1},
        ]
        mock_loop = _make_mock_loop(running=True, positions=positions)
        app.state.paper_loop = mock_loop

        resp = client.post("/api/trading/emergency-stop")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["loop_stopped"] is True
        assert "DEAL-001" in data["positions_closed"]
        assert "DEAL-002" in data["positions_closed"]
        assert len(data["errors"]) == 0

        mock_loop.stop.assert_called_once()
        assert mock_loop.execution_engine.close_position.await_count == 2

    def test_emergency_stop_loop_not_running(self, client):
        """Emergency stop when loop already stopped — still closes positions."""
        positions = [
            {"deal_id": "DEAL-003", "epic": "US500", "direction": "BUY", "size": 1.0},
        ]
        mock_loop = _make_mock_loop(running=False, positions=positions)
        app.state.paper_loop = mock_loop

        resp = client.post("/api/trading/emergency-stop")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["loop_stopped"] is True
        assert "DEAL-003" in data["positions_closed"]
        mock_loop.stop.assert_not_called()

    def test_emergency_stop_no_loop(self, client):
        """Emergency stop returns error if loop not initialized."""
        app.state.paper_loop = None

        resp = client.post("/api/trading/emergency-stop")

        assert resp.status_code == 503
        body = resp.json()
        assert body["success"] is False

    def test_emergency_stop_close_failure(self, client):
        """Close failure is captured in errors array."""
        positions = [
            {"deal_id": "DEAL-004", "epic": "XAUUSD", "direction": "BUY", "size": 0.5},
        ]
        mock_loop = _make_mock_loop(running=True, positions=positions)
        mock_loop.execution_engine.close_position = AsyncMock(
            return_value=ExecutionResult(
                success=False, deal_id="DEAL-004", error="BrokerRejected"
            )
        )
        app.state.paper_loop = mock_loop

        resp = client.post("/api/trading/emergency-stop")

        data = resp.json()["data"]
        assert len(data["positions_closed"]) == 0
        assert len(data["errors"]) == 1
        assert "BrokerRejected" in data["errors"][0]
