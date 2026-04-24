"""Tests for GET /api/trading/performance/delta (Dashboard v2 Phase 4 §A)."""

from unittest.mock import AsyncMock

import pytest

from src.api.dependencies import get_position_repo
from src.api.main import app


def _stats(trade_count: int, win_rate: float, wins: int = 0, losses: int = 0) -> dict:
    return {
        "trade_count": trade_count,
        "win_rate": win_rate,
        "win_count": wins,
        "loss_count": losses,
    }


@pytest.fixture
def repo_stub(client):
    """Repo that returns distinct stats for current vs previous window."""
    repo = AsyncMock()
    # Current window → higher WR, previous → lower. delta_pp = +5pp.
    repo.get_performance_stats = AsyncMock(
        side_effect=[
            _stats(trade_count=200, win_rate=0.50, wins=100, losses=100),
            _stats(trade_count=150, win_rate=0.45, wins=68, losses=82),
        ]
    )
    app.dependency_overrides[get_position_repo] = lambda: repo
    yield repo
    app.dependency_overrides.pop(get_position_repo, None)


@pytest.mark.unit
class TestPerformanceDelta:
    def test_returns_delta_for_preset_tf(self, client, repo_stub):
        resp = client.get("/api/trading/performance/delta", params={"tf": "30D"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["timeframe"] == "30D"
        assert data["source"] == "database"
        assert data["n_current"] == 200
        assert data["n_previous"] == 150
        assert data["win_rate_current"] == 0.5
        assert data["win_rate_previous"] == 0.45
        assert data["delta_pp"] == 5.0
        assert data["wins_current"] == 100
        assert data["losses_current"] == 100
        # Both windows were queried.
        assert repo_stub.get_performance_stats.await_count == 2

    def test_prev_window_retro_shifted(self, client, repo_stub):
        resp = client.get("/api/trading/performance/delta", params={"tf": "7D"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        # prev_to must equal date_from (contiguous retro-shift).
        assert data["prev_to"] == data["date_from"]

    def test_custom_requires_from_and_to(self, client, repo_stub):
        resp = client.get("/api/trading/performance/delta", params={"tf": "CUSTOM"})
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_custom_range_accepted(self, client, repo_stub):
        resp = client.get(
            "/api/trading/performance/delta",
            params={"tf": "CUSTOM", "from": "2026-04-01", "to": "2026-04-21"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["timeframe"] == "CUSTOM"
        assert data["date_from"] == "2026-04-01"
        assert data["date_to"] == "2026-04-21"

    def test_unknown_timeframe_rejected(self, client, repo_stub):
        resp = client.get("/api/trading/performance/delta", params={"tf": "42Y"})
        assert resp.status_code == 400

    def test_no_db_returns_empty_payload(self, client):
        resp = client.get("/api/trading/performance/delta", params={"tf": "7D"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["source"] == "none"
        assert data["n_current"] == 0
        assert data["n_previous"] == 0
        assert data["win_rate_current"] is None
        assert data["delta_pp"] is None

    def test_previous_empty_delta_null(self, client):
        """When previous window has 0 trades, delta_pp must be null."""
        repo = AsyncMock()
        repo.get_performance_stats = AsyncMock(
            side_effect=[
                _stats(trade_count=200, win_rate=0.55, wins=110, losses=90),
                {"trade_count": 0},  # previous period yields the "no data" shape
            ]
        )
        app.dependency_overrides[get_position_repo] = lambda: repo
        try:
            resp = client.get("/api/trading/performance/delta", params={"tf": "30D"})
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["n_current"] == 200
            assert data["n_previous"] == 0
            assert data["win_rate_current"] == 0.55
            assert data["win_rate_previous"] is None
            assert data["delta_pp"] is None
        finally:
            app.dependency_overrides.pop(get_position_repo, None)

    def test_current_empty_delta_null(self, client):
        repo = AsyncMock()
        repo.get_performance_stats = AsyncMock(
            side_effect=[
                {"trade_count": 0},
                _stats(trade_count=50, win_rate=0.42, wins=21, losses=29),
            ]
        )
        app.dependency_overrides[get_position_repo] = lambda: repo
        try:
            resp = client.get("/api/trading/performance/delta", params={"tf": "30D"})
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["n_current"] == 0
            assert data["win_rate_current"] is None
            assert data["delta_pp"] is None
        finally:
            app.dependency_overrides.pop(get_position_repo, None)
