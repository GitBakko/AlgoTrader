"""Tests for System API router."""

import pytest


class TestSystemSettings:
    def test_get_settings(self, client):
        resp = client.get("/api/system/settings")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert "app_name" in data
        assert "app_version" in data
        assert "environment" in data
        assert "trading_enabled" in data
        assert "paper_trading" in data

    def test_settings_values(self, client):
        data = client.get("/api/system/settings").json()["data"]
        assert data["app_name"] == "AlgoTrader AI"
        assert isinstance(data["paper_trading"], bool)


class TestRiskStatus:
    def test_get_risk_status(self, client):
        resp = client.get("/api/system/risk-status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["peak_equity"] == 10000.0
        assert data["current_equity"] == 10000.0
        assert data["circuit_breaker_active"] is False
        assert data["current_drawdown_pct"] == 0.0


class TestSystemEvents:
    def test_get_events_empty(self, client):
        resp = client.get("/api/system/events")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
