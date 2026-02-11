"""Tests for Backtest API router."""

import pytest


class TestRunBacktest:
    def test_run_backtest(self, client):
        resp = client.post("/api/backtest/run", json={"epic": "XAUUSD"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["epic"] == "XAUUSD"
        assert data["status"] == "completed"
        assert "id" in data

    def test_run_backtest_custom_params(self, client):
        resp = client.post(
            "/api/backtest/run",
            json={
                "epic": "BTCUSD",
                "initial_equity": 50000.0,
                "risk_per_trade": 0.01,
            },
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["epic"] == "BTCUSD"


class TestListRuns:
    def test_list_runs_empty(self, client):
        resp = client.get("/api/backtest/runs")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_runs_after_creation(self, client):
        client.post("/api/backtest/run", json={"epic": "XAUUSD"})
        client.post("/api/backtest/run", json={"epic": "BTCUSD"})
        resp = client.get("/api/backtest/runs")
        runs = resp.json()["data"]
        assert len(runs) == 2


class TestGetRunDetails:
    def test_get_run_details(self, client):
        # Create a run first
        create_resp = client.post("/api/backtest/run", json={"epic": "XAUUSD"})
        run_id = create_resp.json()["data"]["id"]

        resp = client.get(f"/api/backtest/runs/{run_id}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["summary"]["id"] == run_id
        assert "equity_curve" in data
        assert "trades" in data
        assert "metrics" in data

    def test_get_run_not_found(self, client):
        resp = client.get("/api/backtest/runs/nonexistent")
        assert resp.status_code == 404
        assert resp.json()["success"] is False
