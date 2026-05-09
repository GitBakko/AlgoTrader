"""Tests for Models API router."""

import pytest


class TestListModels:
    def test_list_models(self, client):
        """Endpoint returns the registered ML models. The list reflects
        the current asset universe (Phase 14 promotion), so this test
        asserts the universe matches `ALL_ASSETS` rather than the
        legacy hard-coded 21-asset snapshot."""
        from src.utils.constants import ALL_ASSETS

        resp = client.get("/api/models/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        epics = {m["epic"] for m in data}
        # Live universe — all assets present in `ALL_ASSETS` should have
        # a registered model entry. Subset check is forgiving if model
        # versioning DB returns extras from older Phase iterations.
        assert epics >= set(ALL_ASSETS), (
            f"Missing assets: {set(ALL_ASSETS) - epics}"
        )


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
