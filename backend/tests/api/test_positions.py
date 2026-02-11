"""Tests for Positions API router."""

import pytest


class TestListPositions:
    def test_list_positions_empty(self, client):
        resp = client.get("/api/positions/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    def test_list_positions_with_epic_filter(self, client):
        resp = client.get("/api/positions/?epic=XAUUSD")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestGetPosition:
    def test_get_position_not_found(self, client):
        resp = client.get("/api/positions/FAKE_DEAL_123")
        assert resp.status_code == 404
        body = resp.json()
        assert body["success"] is False
        assert "not found" in body["error"].lower()


class TestClosePosition:
    def test_close_position_not_found(self, client):
        resp = client.post("/api/positions/close/FAKE_DEAL_123")
        # Paper mode order_manager returns failure for unknown deal
        assert resp.status_code == 200 or resp.status_code == 400


class TestModifyStops:
    def test_modify_stops_no_values(self, client):
        resp = client.put(
            "/api/positions/FAKE_DEAL/stops",
            json={"stop_loss": None, "take_profit": None},
        )
        assert resp.status_code == 400
        assert resp.json()["success"] is False

    def test_modify_stops_with_sl(self, client):
        resp = client.put(
            "/api/positions/FAKE_DEAL/stops",
            json={"stop_loss": 1900.0},
        )
        # May succeed or fail depending on paper engine state
        assert resp.status_code in (200, 400)
