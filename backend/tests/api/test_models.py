"""Tests for Models API router."""

import pytest


class TestListModels:
    def test_list_models(self, client):
        resp = client.get("/api/models/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert len(data) == 21  # Expanded asset coverage (21 total assets)
        epics = {m["epic"] for m in data}
        assert epics == {
            # Crypto
            "BTCUSD", "ETHUSD", "SOLUSD", "DOGUSD", "DASHUSD", "ICPUSD", "BNBUSD",
            # Metals
            "XAUUSD", "XAGUSD", "COPPER", "PLATINUM",
            # Indices
            "US500", "DE40", "NAS100",
            # Commodities/Energy
            "WTIUSD", "NATGAS",
            # Forex
            "EURUSD", "GBPUSD", "USDJPY",
            # Stocks
            "NVDA", "TSLA",
        }


class TestModelMetrics:
    def test_get_metrics(self, client):
        resp = client.get("/api/models/xgboost-xauusd-v1/metrics")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["model_id"] == "xgboost-xauusd-v1"
        assert "accuracy" in data
        assert "f1_score" in data

    def test_get_metrics_not_found(self, client):
        resp = client.get("/api/models/nonexistent/metrics")
        assert resp.status_code == 404


class TestModelVersions:
    def test_get_versions(self, client):
        resp = client.get("/api/models/xgboost-xauusd-v1/versions")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["version"] == "1.0.0"

    def test_get_versions_not_found(self, client):
        resp = client.get("/api/models/nonexistent/versions")
        assert resp.status_code == 404
