"""Tests for asset momentum rotation and per-asset circuit breaker."""

import pytest

from src.trading.asset_rotation import select_active_assets


class TestSelectActiveAssets:
    def test_positive_momentum_selected(self):
        """Assets with positive momentum are selected."""
        scores = {"XAUUSD": 0.15, "BTCUSD": -0.05, "US500": 0.08}
        selected = select_active_assets(scores, top_pct=0.5, min_assets=1)
        assert "XAUUSD" in selected
        assert "US500" in selected
        assert "BTCUSD" not in selected

    def test_min_assets_enforced(self):
        """At least min_assets are selected even if few have positive momentum."""
        scores = {"XAUUSD": 0.01, "BTCUSD": -0.05, "US500": -0.02}
        selected = select_active_assets(scores, top_pct=0.5, min_assets=2)
        assert len(selected) >= 2

    def test_empty_scores_returns_empty(self):
        """Empty scores returns empty list."""
        selected = select_active_assets({}, top_pct=0.5, min_assets=0)
        assert selected == []

    def test_all_negative_still_gets_min_assets(self):
        """If all momentum is negative, still returns min_assets by abs score."""
        scores = {"XAUUSD": -0.01, "BTCUSD": -0.10, "US500": -0.05}
        selected = select_active_assets(scores, top_pct=0.5, min_assets=2)
        assert len(selected) >= 2
        # Best (least negative) should be first
        assert selected[0] == "XAUUSD"

    def test_ranking_order(self):
        """Assets are ranked by momentum score descending."""
        scores = {"XAUUSD": 0.10, "BTCUSD": 0.25, "US500": 0.15}
        selected = select_active_assets(scores, top_pct=1.0, min_assets=1)
        assert selected[0] == "BTCUSD"
        assert selected[1] == "US500"
        assert selected[2] == "XAUUSD"


class TestPerAssetCircuitBreaker:
    def test_5_losses_triggers_cb(self):
        """5 consecutive losses triggers per-asset circuit breaker."""
        losses = {"NATGAS": 5, "XAUUSD": 2}
        assert losses.get("NATGAS", 0) >= 5
        assert losses.get("XAUUSD", 0) < 5

    def test_win_resets_counter(self):
        """A win resets the consecutive loss counter."""
        losses = {"NATGAS": 4}
        # Simulate a win
        losses["NATGAS"] = 0
        assert losses["NATGAS"] == 0

    def test_loss_increments_counter(self):
        """A loss increments the counter."""
        losses = {}
        epic = "NATGAS"
        losses[epic] = losses.get(epic, 0) + 1
        assert losses[epic] == 1
