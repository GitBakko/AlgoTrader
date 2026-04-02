"""Tests for mean reversion target builder."""

import numpy as np
import polars as pl

from src.models.mr_target_builder import MRTargetBuilder


def _make_df(
    close: list[float],
    bb_middle: list[float],
    vwap_z_score: list[float] | None = None,
    bb_pctb: list[float] | None = None,
) -> pl.DataFrame:
    """Helper to build a synthetic DataFrame for MR target tests."""
    data: dict = {"close": close, "bb_middle": bb_middle}
    if vwap_z_score is not None:
        data["vwap_z_score"] = vwap_z_score
    if bb_pctb is not None:
        data["bb_pctb"] = bb_pctb
    return pl.DataFrame(data)


class TestMRTargetBuilder:
    """Tests for MRTargetBuilder."""

    def test_extreme_reversion_labeled_good(self):
        """z > 2, price returns to mean within horizon -> target=1."""
        n = 30
        close = [100.0] * n
        bb_middle = [100.0] * n
        vwap_z = [0.0] * n

        # Bar 5: extreme above mean (z=2.5), price at 110, mean at 100
        close[5] = 110.0
        vwap_z[5] = 2.5

        # Bar 8: price reverts to mean
        close[8] = 100.0

        df = _make_df(close, bb_middle, vwap_z_score=vwap_z)
        builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12)
        result = builder.build_targets(df)

        assert result["target"][5] == 1.0  # GOOD_SETUP

    def test_extreme_no_reversion_labeled_bad(self):
        """z > 2, price stays above mean for entire horizon -> target=0."""
        n = 30
        close = [120.0] * n  # Always above mean
        bb_middle = [100.0] * n
        vwap_z = [0.0] * n

        # Bar 5: extreme above mean
        vwap_z[5] = 2.5

        df = _make_df(close, bb_middle, vwap_z_score=vwap_z)
        builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12)
        result = builder.build_targets(df)

        assert result["target"][5] == 0.0  # BAD_SETUP

    def test_non_extreme_is_nan(self):
        """z < threshold -> target=NaN (not a setup, excluded)."""
        n = 30
        close = [100.0] * n
        bb_middle = [100.0] * n
        vwap_z = [1.0] * n  # Below threshold of 2.0

        df = _make_df(close, bb_middle, vwap_z_score=vwap_z)
        builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12)
        result = builder.build_targets(df)

        # All targets should be NaN (no setups)
        targets = result["target"].to_numpy()
        assert np.all(np.isnan(targets))

    def test_buy_setup_reversion(self):
        """z < -2, price returns up to mean -> target=1."""
        n = 30
        close = [90.0] * n  # Start below mean
        bb_middle = [100.0] * n
        vwap_z = [0.0] * n

        # Bar 3: extreme below mean (z=-2.5)
        close[3] = 90.0
        vwap_z[3] = -2.5

        # Bar 7: price reverts up to mean
        close[7] = 100.0

        df = _make_df(close, bb_middle, vwap_z_score=vwap_z)
        builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12)
        result = builder.build_targets(df)

        assert result["target"][3] == 1.0  # GOOD_SETUP (buy side)

    def test_class_distribution(self):
        """get_class_distribution returns correct counts."""
        n = 30
        close = [100.0] * n
        bb_middle = [100.0] * n
        vwap_z = [0.0] * n

        # Bar 2: good setup (z=2.5, reverts at bar 5)
        close[2] = 110.0
        vwap_z[2] = 2.5
        close[5] = 100.0

        # Bar 10: bad setup (z=3.0, never reverts)
        vwap_z[10] = 3.0
        for i in range(10, min(23, n)):
            close[i] = 115.0  # Stays above mean

        df = _make_df(close, bb_middle, vwap_z_score=vwap_z)
        builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12)
        result = builder.build_targets(df)

        dist = builder.get_class_distribution(result)
        assert dist["total_bars"] == n
        assert dist["good_setups"] >= 1
        assert dist["bad_setups"] >= 1
        assert dist["setup_bars"] == dist["good_setups"] + dist["bad_setups"]
        assert 0 < dist["reversion_rate"] < 1

    def test_horizon_respected(self):
        """Reversion on bar beyond horizon -> target=0."""
        n = 30
        close = [120.0] * n  # Above mean for all bars
        bb_middle = [100.0] * n
        vwap_z = [0.0] * n

        # Bar 2: extreme above mean
        vwap_z[2] = 2.5

        # Reversion happens on bar 15 (= bar 2 + 13), beyond horizon of 12
        close[15] = 100.0

        df = _make_df(close, bb_middle, vwap_z_score=vwap_z)
        builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12)
        result = builder.build_targets(df)

        assert result["target"][2] == 0.0  # BAD — too late

    def test_z_score_target_column_added(self):
        """build_targets adds z_score_target column."""
        n = 30
        close = [100.0] * n
        bb_middle = [100.0] * n
        vwap_z = [1.5] * n

        df = _make_df(close, bb_middle, vwap_z_score=vwap_z)
        builder = MRTargetBuilder()
        result = builder.build_targets(df)

        assert "z_score_target" in result.columns
        assert "target" in result.columns

    def test_bb_pctb_z_score(self):
        """Uses bb_pctb when vwap_z_score not available."""
        n = 30
        close = [100.0] * n
        bb_middle = [100.0] * n
        # bb_pctb=1.0 -> z = (1.0 - 0.5) * 4 = 2.0 (at threshold)
        # bb_pctb=1.2 -> z = (1.2 - 0.5) * 4 = 2.8 (above threshold)
        bb_pctb = [0.5] * n
        bb_pctb[5] = 1.2  # z = 2.8

        close[5] = 110.0
        close[8] = 100.0  # Reverts

        df = _make_df(close, bb_middle, bb_pctb=bb_pctb)
        builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12)
        result = builder.build_targets(df)

        assert result["target"][5] == 1.0  # GOOD_SETUP via bb_pctb

    def test_empty_distribution_without_target(self):
        """get_class_distribution returns empty dict without target column."""
        df = pl.DataFrame({"close": [100.0, 101.0]})
        builder = MRTargetBuilder()
        assert builder.get_class_distribution(df) == {}

    def test_fallback_sma_when_mean_column_missing(self):
        """Falls back to 20-SMA when mean_column not in DataFrame."""
        n = 40
        # Flat price so SMA == close
        close = [100.0] * n
        vwap_z = [0.0] * n
        vwap_z[5] = 2.5

        # No bb_middle column -> fallback to SMA
        df = pl.DataFrame({"close": close, "vwap_z_score": vwap_z})
        builder = MRTargetBuilder(z_threshold=2.0, horizon_bars=12)
        result = builder.build_targets(df)

        # Should still run without error; bar 5 is a setup
        # Since close == SMA at bar 5, close[5]=100 <= mean ~100 -> reverts immediately
        assert result["target"][5] == 1.0
