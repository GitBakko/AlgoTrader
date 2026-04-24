"""Per-epic OU (Ornstein-Uhlenbeck) half-life estimation for mean-reversion.

Mean-reverting strategies benefit from a per-asset exit horizon keyed to
how fast the underlying actually reverts, rather than a fixed global
``MR_MAX_HOLD_HOURS``. This module fits an AR(1) model to the residual
of ``close - SMA(lookback)`` and derives the half-life from the AR
coefficient:

    theta     = AR(1) slope  (0 < theta < 1 → mean-reverting)
    half_life = -ln(2) / ln(theta)

Returns the half-life in **bars**; callers convert to hours using the
candle resolution. A 24h in-memory cache avoids recomputing on every
tick. Recomputation is triggered on stale entries or when the caller
passes ``force=True``.

References: Avellaneda-Lee (2010), Chan (2013), Leung-Li (2015). Math
mirrors the existing ``cointegration._half_life`` used by the pairs
strategy — kept separate so changes to one cannot unintentionally break
the other.

See memory ``project_mr_pending_improvements.md`` (Fix #3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import numpy as np

CACHE_TTL_HOURS = 24
DEFAULT_LOOKBACK_BARS = 30
MIN_SAMPLE_BARS = 60


@dataclass(frozen=True)
class _CacheEntry:
    """Cached per-epic half-life computation."""

    half_life_bars: float | None
    computed_at: datetime


_cache: dict[str, _CacheEntry] = {}


def compute_ou_halflife_bars(
    prices: np.ndarray | list[float],
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
) -> float | None:
    """Estimate OU half-life in bars from a close-price series.

    Returns ``None`` when the fit fails or the series is not
    mean-reverting in the sampled window (``theta`` outside ``(0, 1)``).

    Args:
        prices: Close prices, ordered oldest → newest.
        lookback_bars: SMA window used to de-trend. Should be comfortably
            smaller than ``len(prices)``; the residual series used for
            the AR(1) fit has length ``len(prices) - lookback_bars + 1``.
    """
    arr = np.asarray(prices, dtype=float)
    if arr.size < max(lookback_bars * 2, MIN_SAMPLE_BARS):
        return None
    if not np.isfinite(arr).all():
        return None

    # De-trend via SMA(lookback). valid-mode convolution aligns to
    # ``arr[lookback-1:]`` so both series are of equal length.
    kernel = np.ones(lookback_bars) / lookback_bars
    sma = np.convolve(arr, kernel, mode="valid")
    aligned = arr[lookback_bars - 1:]
    residual = aligned - sma

    if residual.size < 30:
        return None

    y = residual[1:]
    x = residual[:-1]
    x_mat = np.column_stack([np.ones(len(x)), x])
    try:
        coeffs, *_ = np.linalg.lstsq(x_mat, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    theta = float(coeffs[1])

    if theta <= 0.0 or theta >= 1.0:
        return None

    half_life = -np.log(2) / np.log(theta)
    return max(1.0, float(half_life))


def get_halflife_hours(
    epic: str,
    prices: np.ndarray | list[float],
    bar_hours: float,
    *,
    lookback_bars: int = DEFAULT_LOOKBACK_BARS,
    force: bool = False,
    now: datetime | None = None,
) -> float | None:
    """Return cached per-epic half-life in hours, recomputing on TTL miss.

    Args:
        epic: Asset identifier used as cache key.
        prices: Close-price series for the fit when (re)computing.
        bar_hours: Candle resolution used to convert bars → hours
            (e.g. ``4.0`` for 4h bars, ``1.0`` for 1h).
        lookback_bars: SMA lookback for de-trending.
        force: Ignore cache and recompute.
        now: Injection hook for tests.

    Returns:
        Half-life in hours, or ``None`` when the fit doesn't detect
        mean reversion (caller should fall back to the global cap).
    """
    now = now or datetime.now(UTC)
    cached = _cache.get(epic)
    if not force and cached is not None:
        age = now - cached.computed_at
        if age < timedelta(hours=CACHE_TTL_HOURS):
            if cached.half_life_bars is None:
                return None
            return cached.half_life_bars * bar_hours

    hl_bars = compute_ou_halflife_bars(prices, lookback_bars=lookback_bars)
    _cache[epic] = _CacheEntry(half_life_bars=hl_bars, computed_at=now)
    if hl_bars is None:
        return None
    return hl_bars * bar_hours


def clear_cache() -> None:
    """Flush every cached entry. Test helper / admin utility."""
    _cache.clear()
