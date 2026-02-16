"""Tests for Strategy API router."""

import pytest


class TestStrategyConfig:
    def test_get_config(self, client):
        resp = client.get("/api/strategy/config")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 21  # Expanded asset coverage (21 total assets)
        epics = {c["epic"] for c in data}
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

    def test_config_has_expected_fields(self, client):
        data = client.get("/api/strategy/config").json()["data"]
        cfg = data[0]
        assert "min_confidence" in cfg
        assert "counter_trend_penalty" in cfg
        assert "stop_multiplier" in cfg
        assert "risk_reward_ratio" in cfg

    def test_update_config(self, client):
        new_cfg = {
            "epic": "XAUUSD",
            "min_confidence": 0.75,
            "counter_trend_penalty": 0.4,
            "stop_multiplier": 2.0,
            "risk_reward_ratio": 2.5,
            "overbought_rsi": 75.0,
            "oversold_rsi": 25.0,
        }
        resp = client.put("/api/strategy/config", json=new_cfg)
        assert resp.status_code == 200
        assert resp.json()["data"]["updated"] is True

    def test_update_config_unsupported_epic(self, client):
        new_cfg = {
            "epic": "INVALID",
            "min_confidence": 0.7,
            "counter_trend_penalty": 0.5,
            "stop_multiplier": 1.5,
            "risk_reward_ratio": 2.0,
            "overbought_rsi": 70.0,
            "oversold_rsi": 30.0,
        }
        resp = client.put("/api/strategy/config", json=new_cfg)
        assert resp.status_code == 400


class TestAllocation:
    def test_get_allocation(self, client):
        resp = client.get("/api/strategy/allocation")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "weights" in data
        weights = data["weights"]
        assert "XAUUSD" in weights
        assert "BTCUSD" in weights
        assert "US500" in weights


class TestRiskLimits:
    def test_get_risk_limits(self, client):
        resp = client.get("/api/strategy/risk-limits")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "max_risk_per_trade" in data
        assert "max_daily_drawdown" in data

    def test_update_risk_limits(self, client):
        new_limits = {
            "max_risk_per_trade": 0.03,
            "max_daily_drawdown": 0.06,
            "max_total_drawdown": 0.20,
            "max_position_pct": 0.10,
            "max_correlated_exposure": 0.60,
        }
        resp = client.put("/api/strategy/risk-limits", json=new_limits)
        assert resp.status_code == 200
        assert resp.json()["data"]["updated"] is True

        # Verify the update persisted
        resp2 = client.get("/api/strategy/risk-limits")
        data = resp2.json()["data"]
        assert data["max_risk_per_trade"] == 0.03
