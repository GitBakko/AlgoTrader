"""Unit tests for the pure logic in scripts/shap_analysis.py.

Targets the bugs that made the original script wrong:
  * multiclass SHAP aggregation across list / (n,f,c) / (n,c,f) / (n,f) shapes
  * deterministic ranking + cumulative pruning boundary
  * real redundancy clustering
  * thematic grouping (no dead 'structure' group, tf/zscore stripping)
"""

import sys
from pathlib import Path

import numpy as np
import pytest

# backend/ on path so `scripts` namespace package imports.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts import shap_analysis as sa  # noqa: E402


# ── classify_feature ─────────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "name,expected",
    [
        ("ema_8", "trend"),
        ("ema_50_zscore", "trend"),
        ("4h_ema_50", "trend"),  # tf prefix stripped
        ("macd_signal", "trend"),
        ("rsi_14", "momentum"),
        ("return_5", "momentum"),
        ("returns_1_zscore", "momentum"),  # plural form (real feature name)
        ("1d_returns_1_zscore", "momentum"),  # tf + plural
        ("atr_14", "volatility"),
        ("bb_width", "volatility"),
        ("high_low_range_zscore", "volatility"),
        ("close_position_zscore", "price_action"),
        ("vwap_distance", "volume"),
        ("obv", "volume"),
        ("regime_trending_up", "regime"),
        ("bos_signal", "structure"),  # NOT trend (dead-group bug fixed)
        ("choch_signal", "structure"),
        ("hour_sin", "session"),
        ("sil_fear_greed", "sil_macro"),
        ("vix_level", "sil_macro"),
        ("corr_BTCUSD_ETHUSD", "cross_asset"),
        ("lead_lag_US500", "cross_asset"),
        ("news_sentiment", "sentiment"),
        ("totally_unknown_xyz", "other"),
    ],
)
def test_classify_feature(name, expected):
    assert sa.classify_feature(name) == expected


# ── aggregate_mean_abs_shap ──────────────────────────────────────────────────
def test_aggregate_list_of_class_arrays():
    n, f, c = 10, 4, 3
    rng = np.random.default_rng(0)
    arrs = [rng.normal(size=(n, f)) for _ in range(c)]
    glob, per_class = sa.aggregate_mean_abs_shap(arrs, f)
    assert glob.shape == (f,)
    assert per_class.shape == (f, c)
    expected = np.mean([np.abs(a).mean(axis=0) for a in arrs], axis=0)
    np.testing.assert_allclose(glob, expected)


def test_aggregate_3d_ndarray_nfc():
    """shap>=0.41 multiclass shape (n, f, c) — the case the old script broke on."""
    n, f, c = 8, 5, 3
    rng = np.random.default_rng(1)
    arr = rng.normal(size=(n, f, c))
    glob, per_class = sa.aggregate_mean_abs_shap(arr, f)
    assert glob.shape == (f,)  # MUST be 1D, not (f, c)
    assert per_class.shape == (f, c)
    np.testing.assert_allclose(glob, np.abs(arr).mean(axis=0).mean(axis=1))


def test_aggregate_3d_transposed_ncf():
    """Some versions emit (n, c, f) — must be detected and transposed."""
    n, f, c = 8, 5, 3
    rng = np.random.default_rng(2)
    arr_ncf = rng.normal(size=(n, c, f))
    glob, per_class = sa.aggregate_mean_abs_shap(arr_ncf, f)
    assert glob.shape == (f,)
    assert per_class.shape == (f, c)


def test_aggregate_2d_single_output():
    n, f = 8, 6
    arr = np.random.default_rng(3).normal(size=(n, f))
    glob, per_class = sa.aggregate_mean_abs_shap(arr, f)
    assert glob.shape == (f,)
    assert per_class is None


# ── build_ranking ────────────────────────────────────────────────────────────
def test_build_ranking_order_and_cumulative():
    names = ["a", "b", "c", "d"]
    mean_abs = np.array([1.0, 4.0, 2.0, 3.0])  # b>d>c>a
    ranking = sa.build_ranking(names, mean_abs, prune_threshold=0.7)
    assert [r["feature"] for r in ranking] == ["b", "d", "c", "a"]
    assert ranking[-1]["cumulative_pct"] == pytest.approx(100.0)
    # total=10 -> b=40,d=30 -> cum 70 keep; c pushes to 90 -> drop
    assert ranking[0]["keep"] and ranking[1]["keep"]
    assert not ranking[2]["keep"] and not ranking[3]["keep"]


def test_build_ranking_zero_total_safe():
    ranking = sa.build_ranking(["a", "b"], np.array([0.0, 0.0]), 0.85)
    assert all(r["pct_of_total"] == 0.0 for r in ranking)


# ── find_redundant_clusters ──────────────────────────────────────────────────
def test_redundant_clusters_detects_collinear_pair():
    rng = np.random.default_rng(4)
    base = rng.normal(size=200)
    X = np.column_stack(
        [
            base,  # f0
            base * 2.0 + 1e-6,  # f1  ~ perfectly correlated with f0
            rng.normal(size=200),  # f2  independent
            np.zeros(200),  # f3  constant -> never clusters
        ]
    )
    clusters = sa.find_redundant_clusters(X, ["f0", "f1", "f2", "f3"], corr_threshold=0.9)
    assert len(clusters) == 1
    assert set(clusters[0]) == {"f0", "f1"}


def test_redundant_clusters_none_when_independent():
    X = np.random.default_rng(5).normal(size=(300, 5))
    clusters = sa.find_redundant_clusters(X, [f"f{i}" for i in range(5)], corr_threshold=0.9)
    assert clusters == []


# ── group_distribution ───────────────────────────────────────────────────────
def test_group_distribution_sums_to_100():
    names = ["ema_8", "rsi_14", "atr_14", "corr_x"]
    ranking = sa.build_ranking(names, np.array([4.0, 3.0, 2.0, 1.0]), 0.85)
    dist = sa.group_distribution(ranking)
    assert sum(dist.values()) == pytest.approx(100.0, abs=0.05)
    assert dist["trend"] == pytest.approx(40.0, abs=0.05)
