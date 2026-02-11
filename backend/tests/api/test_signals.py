"""Tests for Signals API router."""

import pytest


class TestListSignals:
    def test_list_signals_empty(self, client):
        resp = client.get("/api/signals/")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["data"] == []

    def test_list_signals_with_epic_filter(self, client):
        resp = client.get("/api/signals/?epic=XAUUSD")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestGenerateSignal:
    def test_generate_default_signal(self, client):
        resp = client.get("/api/signals/generate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        assert data["epic"] == "XAUUSD"
        assert "direction" in data
        assert "confidence" in data
        assert "timestamp" in data

    def test_generate_signal_custom_params(self, client):
        resp = client.get(
            "/api/signals/generate?epic=BTCUSD&confidence=0.9&signal_class=2"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["epic"] == "BTCUSD"

    def test_generate_signal_stores_in_history(self, client):
        # Generate a signal
        client.get("/api/signals/generate?epic=XAUUSD")
        # Check history
        resp = client.get("/api/signals/")
        signals = resp.json()["data"]
        assert len(signals) >= 1
        assert signals[0]["epic"] == "XAUUSD"

    def test_generate_hold_signal(self, client):
        # signal_class=1 is HOLD, should return HOLD direction
        resp = client.get("/api/signals/generate?signal_class=1&confidence=0.9")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["direction"] == "HOLD"
