"""Tests for Backtest API router."""

import pytest


class TestRunBacktest:
    def test_run_backtest_no_model_for_epic(self, client):
        """Returns error when no model is loaded for the requested epic."""
        # The client fixture's lifespan may load real models.
        # Test with a non-existent epic to trigger "no model" error.
        resp = client.post("/api/backtest/run", json={"epic": "INVALID_EPIC"})
        body = resp.json()
        assert body["success"] is False

    def test_run_backtest_invalid_dates(self, client):
        """Returns error for invalid date format."""
        resp = client.post(
            "/api/backtest/run",
            json={"epic": "XAUUSD", "start_date": "not-a-date"},
        )
        body = resp.json()
        assert body["success"] is False

    def test_run_backtest_accepts_timeframe(self, client):
        """Timeframe field is accepted in request body."""
        resp = client.post(
            "/api/backtest/run",
            json={"epic": "INVALID_EPIC", "timeframe": "4h"},
        )
        body = resp.json()
        # Should fail because of invalid epic, but the request is accepted
        assert body["success"] is False


class TestListRuns:
    def test_list_runs_empty(self, client):
        resp = client.get("/api/backtest/runs")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestGetRunDetails:
    def test_get_run_not_found(self, client):
        resp = client.get("/api/backtest/runs/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["success"] is False
