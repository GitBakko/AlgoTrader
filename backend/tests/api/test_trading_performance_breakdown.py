"""Tests for GET /api/trading/performance/breakdown (Dashboard v2 §2.1)."""

from unittest.mock import AsyncMock

import pytest

from src.api.dependencies import get_position_repo
from src.api.main import app


def _sample_days() -> list[dict]:
    return [
        {
            "date": "2026-04-20",
            "buy":  {"tp": 3, "sl": 1, "going": 0, "pnl": 120.0},
            "sell": {"tp": 1, "sl": 2, "going": 1, "pnl": -40.0},
        },
        {
            "date": "2026-04-21",
            "buy":  {"tp": 0, "sl": 0, "going": 1, "pnl": 0.0},
            "sell": {"tp": 0, "sl": 0, "going": 0, "pnl": 0.0},
        },
    ]


@pytest.fixture
def repo_stub(client):
    repo = AsyncMock()
    repo.get_breakdown_by_day = AsyncMock(return_value=_sample_days())
    app.dependency_overrides[get_position_repo] = lambda: repo
    yield repo
    app.dependency_overrides.pop(get_position_repo, None)


@pytest.mark.unit
class TestPerformanceBreakdown:
    def test_returns_days_for_preset_timeframe(self, client, repo_stub):
        resp = client.get("/api/trading/performance/breakdown", params={"tf": "30D"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["timeframe"] == "30D"
        assert data["source"] == "database"
        assert len(data["days"]) == 2
        day = data["days"][0]
        assert set(day.keys()) >= {"date", "buy", "sell"}
        assert set(day["buy"].keys()) == {"tp", "sl", "going", "pnl"}
        assert set(day["sell"].keys()) == {"tp", "sl", "going", "pnl"}

    def test_custom_requires_from_and_to(self, client, repo_stub):
        resp = client.get("/api/trading/performance/breakdown", params={"tf": "CUSTOM"})
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_custom_range_passed_through(self, client, repo_stub):
        resp = client.get(
            "/api/trading/performance/breakdown",
            params={"tf": "CUSTOM", "from": "2026-04-01", "to": "2026-04-21"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["timeframe"] == "CUSTOM"
        # Repository received the resolved UTC datetimes.
        repo_stub.get_breakdown_by_day.assert_awaited_once()

    def test_unknown_timeframe_rejected(self, client, repo_stub):
        resp = client.get("/api/trading/performance/breakdown", params={"tf": "42Y"})
        assert resp.status_code == 400

    def test_no_db_returns_empty_days(self, client):
        # No repo override → default fixture sets it to None.
        resp = client.get("/api/trading/performance/breakdown", params={"tf": "7D"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["days"] == []
        assert data["source"] == "none"
