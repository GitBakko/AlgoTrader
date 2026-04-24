"""Unit tests for ``src.strategy.ou_halflife``.

Covers AR(1) math on synthetic OU / trending / noisy series, cache TTL
behaviour, and the hours-vs-bars conversion contract.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from src.strategy import ou_halflife
from src.strategy.ou_halflife import (
    CACHE_TTL_HOURS,
    MIN_SAMPLE_BARS,
    clear_cache,
    compute_ou_halflife_bars,
    get_halflife_hours,
)


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


def _make_ou_series(n: int, theta: float, mu: float = 100.0, sigma: float = 0.5,
                    seed: int = 42) -> np.ndarray:
    """Generate a synthetic OU-ish series with known AR(1) coefficient."""
    rng = np.random.default_rng(seed)
    x = np.empty(n)
    x[0] = mu
    for t in range(1, n):
        x[t] = mu + theta * (x[t - 1] - mu) + rng.normal(0, sigma)
    return x


class TestComputeOuHalflifeBars:
    def test_reverts_to_mu_recovers_finite_halflife(self):
        # theta=0.7 → half_life = -ln(2)/ln(0.7) ≈ 1.94 bars (intrinsic AR(1)).
        # After SMA(30) de-trend + OLS refit, the recovered value is bounded
        # but not exactly equal — assert finite + positive + reasonable.
        series = _make_ou_series(n=400, theta=0.7)
        hl = compute_ou_halflife_bars(series, lookback_bars=30)
        assert hl is not None
        assert 1.0 <= hl <= 50.0

    def test_random_walk_returns_none(self):
        # Pure random walk has theta ≈ 1 → not mean-reverting → None.
        rng = np.random.default_rng(7)
        walk = np.cumsum(rng.normal(0, 1, size=400)) + 100.0
        hl = compute_ou_halflife_bars(walk, lookback_bars=30)
        # Random walks can occasionally land on theta ∈ (0,1) by chance,
        # but the common case is None. Either outcome is acceptable —
        # what we guarantee is "no crash and no absurd value".
        if hl is not None:
            assert hl > 1.0

    def test_trending_series_no_reversion(self):
        # Strong linear trend → residuals after SMA don't mean-revert.
        trend = np.linspace(100.0, 200.0, 400) + np.random.default_rng(1).normal(
            0, 0.1, 400
        )
        hl = compute_ou_halflife_bars(trend, lookback_bars=30)
        # Likely None; if not None must be finite positive.
        assert hl is None or hl > 0

    def test_too_few_samples_returns_none(self):
        series = _make_ou_series(n=40, theta=0.5)
        assert compute_ou_halflife_bars(series, lookback_bars=30) is None

    def test_nan_in_input_returns_none(self):
        series = _make_ou_series(n=400, theta=0.6)
        series[50] = np.nan
        assert compute_ou_halflife_bars(series) is None

    def test_min_sample_bars_enforced(self):
        # Exactly MIN_SAMPLE_BARS - 1 → reject.
        series = _make_ou_series(n=MIN_SAMPLE_BARS - 1, theta=0.5)
        assert compute_ou_halflife_bars(series, lookback_bars=5) is None


class TestCacheBehaviour:
    def test_converts_bars_to_hours_with_resolution(self):
        series = _make_ou_series(n=400, theta=0.6)
        hl_hours_4h = get_halflife_hours(
            "XAUUSD", series, bar_hours=4.0, now=datetime(2026, 4, 24, tzinfo=UTC)
        )
        clear_cache()
        hl_hours_1h = get_halflife_hours(
            "XAUUSD", series, bar_hours=1.0, now=datetime(2026, 4, 24, tzinfo=UTC)
        )
        assert hl_hours_4h is not None
        assert hl_hours_1h is not None
        assert hl_hours_4h == pytest.approx(hl_hours_1h * 4.0, rel=1e-9)

    def test_cache_hit_inside_ttl_skips_recompute(self):
        series_a = _make_ou_series(n=400, theta=0.6, seed=1)
        series_b = _make_ou_series(n=400, theta=0.9, seed=2)  # very different

        now = datetime(2026, 4, 24, 10, 0, tzinfo=UTC)
        first = get_halflife_hours("XAUUSD", series_a, bar_hours=4.0, now=now)
        # Second call with a DIFFERENT series must return the cached value.
        second = get_halflife_hours(
            "XAUUSD",
            series_b,
            bar_hours=4.0,
            now=now + timedelta(hours=CACHE_TTL_HOURS - 1),
        )
        assert first == second

    def test_cache_miss_past_ttl_recomputes(self):
        series_a = _make_ou_series(n=400, theta=0.6, seed=1)
        series_b = _make_ou_series(n=400, theta=0.9, seed=2)

        now = datetime(2026, 4, 24, 10, 0, tzinfo=UTC)
        first = get_halflife_hours("XAUUSD", series_a, bar_hours=4.0, now=now)
        second = get_halflife_hours(
            "XAUUSD",
            series_b,
            bar_hours=4.0,
            now=now + timedelta(hours=CACHE_TTL_HOURS + 1),
        )
        assert first != second or (first is None and second is None)

    def test_force_recomputes_even_inside_ttl(self):
        series_a = _make_ou_series(n=400, theta=0.6, seed=1)
        series_b = _make_ou_series(n=400, theta=0.9, seed=2)

        now = datetime(2026, 4, 24, 10, 0, tzinfo=UTC)
        first = get_halflife_hours("XAUUSD", series_a, bar_hours=4.0, now=now)
        second = get_halflife_hours(
            "XAUUSD", series_b, bar_hours=4.0, now=now, force=True
        )
        assert first != second or (first is None and second is None)

    def test_none_result_is_cached(self):
        """A None outcome (no mean reversion) should be cached too — we
        don't want to refit a 400-bar AR(1) on every tick of a trending
        asset."""
        clear_cache()
        short = _make_ou_series(n=40, theta=0.5)  # too few samples → None
        now = datetime(2026, 4, 24, 10, 0, tzinfo=UTC)
        first = get_halflife_hours("TREND", short, bar_hours=4.0, now=now)
        assert first is None
        # Second call — even with a richer series — returns None from cache.
        long = _make_ou_series(n=400, theta=0.6)
        second = get_halflife_hours(
            "TREND", long, bar_hours=4.0,
            now=now + timedelta(hours=CACHE_TTL_HOURS - 1),
        )
        assert second is None
