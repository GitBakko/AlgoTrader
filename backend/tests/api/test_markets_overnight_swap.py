"""Tests for GET /api/markets/{epic}/overnight-swap (Dashboard v2 §2.2')."""

from unittest.mock import AsyncMock

import pytest

from src.api.dependencies import get_broker_client
from src.api.main import app


@pytest.mark.unit
class TestOvernightSwap:
    def test_static_fallback_when_no_broker(self, client):
        resp = client.get("/api/markets/XAUUSD/overnight-swap")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["epic"] == "XAUUSD"
        assert data["source"] == "static_fallback"
        assert data["long_rate_daily"] < 0  # costs → negative rates
        assert data["short_rate_daily"] < 0
        assert data["weekend_multiplier"] == 3
        assert data["next_charge_utc"].endswith("+00:00")

    def test_broker_rate_preferred_over_static(self, client):
        # Capital.com schema: instrument.overnightFee.{longRate, shortRate}
        # (per-interval percentages). Older test used overnightBuy /
        # overnightSell which the route never reads.
        # Capital.com schema: instrument.overnightFee.{longRate, shortRate}
        # are **percentages** per `swapChargeInterval`. The route exposes a
        # fraction-equivalent (`*_daily = pct / 100`) for legacy clients.
        broker = AsyncMock()
        broker.get_market_details = AsyncMock(return_value={
            "instrument": {
                "overnightFee": {
                    "longRate": -0.0222,
                    "shortRate": -0.0111,
                },
                "currency": "USD",
            },
            "snapshot": {"bid": 1, "offer": 1.01},
        })
        app.dependency_overrides[get_broker_client] = lambda: broker
        try:
            resp = client.get("/api/markets/XAUUSD/overnight-swap")
            assert resp.status_code == 200
            data = resp.json()["data"]
            assert data["source"] == "broker"
            assert data["long_rate_pct"] == pytest.approx(-0.0222)
            assert data["short_rate_pct"] == pytest.approx(-0.0111)
            assert data["long_rate_daily"] == pytest.approx(-0.000222)
            assert data["short_rate_daily"] == pytest.approx(-0.000111)
            assert data["currency"] == "USD"
        finally:
            app.dependency_overrides.pop(get_broker_client, None)

    def test_unknown_epic_uses_generic_fallback(self, client):
        resp = client.get("/api/markets/NOT_IN_TABLE/overnight-swap")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Generic fallback from the endpoint default.
        assert data["long_rate_daily"] == pytest.approx(-0.000015)
        assert data["short_rate_daily"] == pytest.approx(-0.000010)
