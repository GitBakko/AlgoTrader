"""Tests for Dashboard API router."""

import pytest


class TestDashboardOverview:
    def test_overview_returns_success(self, client):
        resp = client.get("/api/dashboard/overview")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert "equity" in data
        assert "daily_pnl" in data
        assert "open_positions_count" in data
        assert "circuit_breaker_active" in data

    def test_overview_default_values(self, client):
        resp = client.get("/api/dashboard/overview")
        data = resp.json()["data"]
        assert data["equity"] == 10000.0
        assert data["open_positions_count"] == 0
        assert data["circuit_breaker_active"] is False
        assert data["trading_mode"] == "paper"


class TestEquityCurve:
    def test_equity_curve_returns_list(self, client):
        resp = client.get("/api/dashboard/equity-curve")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_equity_curve_point_structure(self, client):
        resp = client.get("/api/dashboard/equity-curve")
        point = resp.json()["data"][0]
        assert "date" in point
        assert "equity" in point
        assert "drawdown_pct" in point

    def test_equity_curve_days_param(self, client):
        resp = client.get("/api/dashboard/equity-curve?days=7")
        assert resp.status_code == 200


class TestRecentTrades:
    def test_recent_trades_returns_list(self, client):
        resp = client.get("/api/dashboard/recent-trades")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)

    def test_recent_trades_limit_param(self, client):
        resp = client.get("/api/dashboard/recent-trades?limit=5")
        assert resp.status_code == 200
