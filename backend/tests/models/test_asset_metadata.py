"""Tests for ML asset-class window calibration."""

import pytest

from src.models.asset_metadata import (
    AssetWindowSpec,
    compute_walk_forward_windows,
    get_asset_class,
    get_window_spec,
)


class TestAssetClassMapping:
    @pytest.mark.parametrize(
        "epic,expected",
        [
            # Crypto (24/7)
            ("BTCUSD", "crypto"),
            ("ETHUSD", "crypto"),
            ("SOLUSD", "crypto"),
            ("BNBUSD", "crypto"),
            # Forex (24/5)
            ("USDJPY", "forex"),
            ("EURUSD", "forex"),
            # Indices
            ("US500", "indices"),
            ("DE40", "indices"),
            ("NAS100", "indices"),
            # Commodities
            ("XAUUSD", "commodities"),
            ("WTIUSD", "commodities"),
            ("COPPER", "commodities"),
            ("PLATINUM", "commodities"),
            # Stocks (CFD with extended hours)
            ("NVDA", "stocks"),
            ("TSLA", "stocks"),
        ],
    )
    def test_known_epics_map_correctly(self, epic, expected):
        assert get_asset_class(epic) == expected

    def test_unknown_epic_falls_back_to_crypto(self):
        assert get_asset_class("UNKNOWN_EPIC") == "crypto"


class TestWindowSpec:
    def test_each_class_has_distinct_density(self):
        densities = {
            cls: get_window_spec(epic).bars_per_calendar_day
            for cls, epic in [
                ("crypto", "BTCUSD"),
                ("forex", "USDJPY"),
                ("indices", "US500"),
                ("commodities", "XAUUSD"),
                ("stocks", "NVDA"),
            ]
        }
        # Crypto strictly densest, stocks strictly sparsest.
        assert densities["crypto"] > densities["forex"]
        assert densities["stocks"] < densities["forex"]

    def test_calendar_day_defaults_match_legacy(self):
        spec = get_window_spec("BTCUSD")
        assert spec.train_calendar_days == 252
        assert spec.val_calendar_days == 63
        assert spec.test_calendar_days == 21
        assert spec.step_calendar_days == 21


class TestComputeWalkForwardWindows:
    def test_btcusd_1h_matches_legacy_default(self):
        # The legacy hard-coded default (train=6048/val=1512/test=504) was
        # calibrated to 24h × 252d for crypto. New computation must produce
        # the same numbers — otherwise existing crypto/index/commodity
        # models would drift unexpectedly on next retrain.
        w = compute_walk_forward_windows("BTCUSD", "1h")
        assert w["train_window"] == 6048
        assert w["val_window"] == 1512
        assert w["test_window"] == 504
        assert w["step_size"] == 504

    def test_nvda_1h_produces_stock_friendly_windows(self):
        # The 2026-05-08 fold-collapse incident: orchestrator default
        # 6048/1512/504 left only ~498 residual samples after one fold,
        # collapsing 25 → 1. The fix lands when stocks compute < 3000
        # train samples on 1h, so the residual fits multiple step-sized
        # folds in a typical ~8500-bar history.
        w = compute_walk_forward_windows("NVDA", "1h")
        assert w["train_window"] < 3000
        assert w["val_window"] < 800
        assert w["test_window"] < 300
        assert w["step_size"] < 300

        # Validate the calendar-time coverage is preserved (train ≈ 252d).
        # 252 × 10.5 = 2646 — allow tight tolerance for rounding.
        assert 2500 <= w["train_window"] <= 2800

    def test_4h_timeframe_scales_down(self):
        w_1h = compute_walk_forward_windows("BTCUSD", "1h")
        w_4h = compute_walk_forward_windows("BTCUSD", "4h")
        # 4h has 1/4 the bars per day → windows should shrink ~4×.
        assert w_4h["train_window"] == w_1h["train_window"] // 4
        assert w_4h["val_window"] == w_1h["val_window"] // 4

    def test_unknown_timeframe_raises(self):
        with pytest.raises(ValueError, match="Unknown timeframe"):
            compute_walk_forward_windows("BTCUSD", "13min")

    def test_all_outputs_at_least_one(self):
        # On daily bars even short calendar windows could round to zero.
        # The function must clamp to >= 1 to keep the splitter happy.
        w = compute_walk_forward_windows("BTCUSD", "1d")
        for v in w.values():
            assert v >= 1


class TestFoldCountStability:
    """Regression check on the underlying motivation: the number of
    walk-forward folds the splitter can produce, given a typical history,
    must be in a healthy range (>= 5) for every asset class.

    Uses the WalkForwardSplitter's count logic directly.
    """

    @pytest.mark.parametrize(
        "epic,n_samples_observed",
        [
            ("BTCUSD", 19327),
            ("XAUUSD", 13206),
            ("US500", 13206),  # similar density, similar history depth
            ("USDJPY", 13206),
            ("NVDA", 8569),
            ("TSLA", 8569),
        ],
    )
    def test_at_least_five_folds_for_realistic_history(
        self, epic, n_samples_observed
    ):
        from src.models.walk_forward import WalkForwardSplitter

        w = compute_walk_forward_windows(epic, "1h")
        s = WalkForwardSplitter(
            train_window=w["train_window"],
            val_window=w["val_window"],
            test_window=w["test_window"],
            step_size=w["step_size"],
            purge_gap=5,
            embargo=2,
        )
        n_folds = s.get_n_splits(n_samples_observed)
        assert n_folds >= 5, (
            f"{epic} would only get {n_folds} folds with "
            f"{n_samples_observed} samples — fold-collapse regression"
        )
