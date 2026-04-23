"""Tests for GET /api/models/current (Dashboard v2 §2.4)."""

from unittest.mock import MagicMock, PropertyMock

import pytest

from src.api.dependencies import get_prediction_service
from src.api.main import app


def _make_prediction_service(loaded: dict | None):
    svc = MagicMock()
    type(svc).has_models = PropertyMock(return_value=bool(loaded))
    svc.get_loaded_models = MagicMock(return_value=loaded or {})
    return svc


@pytest.mark.unit
class TestModelsCurrent:
    def test_empty_when_no_service(self, client):
        resp = client.get("/api/models/current")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data == {"count": 0, "by_epic": {}, "primary": None}

    def test_returns_loaded_models(self, client):
        app.dependency_overrides[get_prediction_service] = lambda: _make_prediction_service({
            "XAUUSD": {
                "model_id": "xgb-gold-v2-3",
                "model_type": "xgboost",
                "num_features": 412,
                "created_at": "2026-04-20T10:00:00+00:00",
                "version": "2.3",
            },
            "BTCUSD": {
                "model_id": "xgb-btc-v2-1",
                "model_type": "xgboost",
                "num_features": 412,
                "created_at": "2026-04-18T10:00:00+00:00",
                "version": "2.1",
            },
        })
        try:
            resp = client.get("/api/models/current")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["count"] == 2
            assert set(data["by_epic"].keys()) == {"XAUUSD", "BTCUSD"}
            # Primary picks the latest created_at.
            assert data["primary"]["epic"] == "XAUUSD"
            assert data["primary"]["version"] == "2.3"
        finally:
            app.dependency_overrides.pop(get_prediction_service, None)
