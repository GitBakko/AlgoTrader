"""Tests for Markets API router."""

import pytest


class TestSearchMarkets:
    def test_search_all_markets(self, client):
        resp = client.get("/api/markets/search")
        assert resp.status_code == 200
        data = resp.json()["data"]
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

    def test_search_by_keyword(self, client):
        resp = client.get("/api/markets/search?q=gold")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["epic"] == "XAUUSD"

    def test_search_no_results(self, client):
        resp = client.get("/api/markets/search?q=forex")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


class TestMarketInfo:
    def test_get_market_info(self, client):
        resp = client.get("/api/markets/XAUUSD/info")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["epic"] == "XAUUSD"
        assert "name" in data

    def test_get_unknown_market_info(self, client):
        resp = client.get("/api/markets/UNKNOWN/info")
        assert resp.status_code == 404
        assert resp.json()["success"] is False


class TestMarketPrices:
    def test_get_prices_empty(self, client):
        resp = client.get("/api/markets/XAUUSD/prices")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
