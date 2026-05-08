"""Asset metadata for ML training calibration.

Anchors walk-forward window sizes to each asset's natural trading
density (`bars_per_calendar_day`), so the calendar-time coverage of
train/val/test windows stays consistent across markets that trade at
very different rates (24/7 crypto vs ~6.5h/day stocks).

Background — fold-collapse incident 2026-05-08:
The TrainingOrchestrator hard-coded windows in 1h-bars
(train=6048, val=1512, test=504) sized for 24/7 crypto. NVDA + TSLA
have ~10.5 bars per calendar day on 1h (CFD extended-hours), so the
same bar windows demand ~5 calendar years of history; only ~498
residual bars were left after one fold (vs 8071 minimum), collapsing
walk-forward from 25 → 1 fold. Test metrics regressed (NVDA f1 -0.07,
TSLA f1 -0.085). Calibrating windows to calendar-days × asset density
keeps fold count stable across asset classes without manual per-epic
overrides in the orchestrator.
"""

from dataclasses import dataclass

from src.utils.constants import (
    COMMODITY_ASSETS,
    CRYPTO_ASSETS,
    FOREX_ASSETS,
    INDEX_ASSETS,
    STOCK_ASSETS,
)


@dataclass(frozen=True)
class AssetWindowSpec:
    """Walk-forward window calibration for an asset class.

    All windows are expressed in calendar days; `bars_per_calendar_day`
    converts to the bar count needed by `WalkForwardSplitter`. Defaults
    match the historical `train=252d / val=63d / test=21d / step=21d`
    convention (~10 folds across ~3yrs of data on 24/7 markets).
    """

    bars_per_calendar_day: float
    train_calendar_days: int = 252
    val_calendar_days: int = 63
    test_calendar_days: int = 21
    step_calendar_days: int = 21


# Empirically-measured bars-per-calendar-day on 1h bars from production
# parquet files (samples / calendar-day-range across the full history).
# Values rounded to a stable approximation; the splitter is robust to
# small drift since folds use floor-division logic.
#
# - crypto      ~24.0  (24/7 markets)
# - forex       ~17.0  (24/5 ≈ 24 × 5/7)
# - indices     ~17.0  (CFD indices trade ~24/5 on most brokers)
# - commodities ~17.0  (24/5 with brief daily breaks)
# - stocks      ~10.5  (CFD with extended hours; cash-equity ~6.5/day
#                       observed at ~10.6 in NVDA/TSLA history due to
#                       Capital.com extended-hour CFD coverage)
_ASSET_CLASS_SPECS: dict[str, AssetWindowSpec] = {
    "crypto": AssetWindowSpec(bars_per_calendar_day=24.0),
    "forex": AssetWindowSpec(bars_per_calendar_day=17.0),
    "indices": AssetWindowSpec(bars_per_calendar_day=17.0),
    "commodities": AssetWindowSpec(bars_per_calendar_day=17.0),
    "stocks": AssetWindowSpec(bars_per_calendar_day=10.5),
}

# Default for unknown epics — assume 24/7 (most aggressive sample
# density), so folds err on the side of sufficient history rather
# than fold-collapse on a misclassification.
_DEFAULT_SPEC = _ASSET_CLASS_SPECS["crypto"]


# Bars-per-hour relative to the 1h baseline. Used to scale
# `bars_per_calendar_day` for non-1h timeframes.
_TIMEFRAME_FACTOR: dict[str, float] = {
    "1min": 60.0,
    "5min": 12.0,
    "15min": 4.0,
    "30min": 2.0,
    "1h": 1.0,
    "2h": 0.5,
    "4h": 0.25,
    "1d": 1.0 / 24.0,
    "day": 1.0 / 24.0,
}


def get_asset_class(epic: str) -> str:
    """Resolve epic → asset class slug. Falls back to ``"crypto"`` (24/7)
    for unknown epics so window sizing leans toward more data, never less."""
    if epic in CRYPTO_ASSETS:
        return "crypto"
    if epic in FOREX_ASSETS:
        return "forex"
    if epic in INDEX_ASSETS:
        return "indices"
    if epic in COMMODITY_ASSETS:
        return "commodities"
    if epic in STOCK_ASSETS:
        return "stocks"
    return "crypto"


def get_window_spec(epic: str) -> AssetWindowSpec:
    """Resolve walk-forward window spec for an epic."""
    return _ASSET_CLASS_SPECS.get(get_asset_class(epic), _DEFAULT_SPEC)


def compute_walk_forward_windows(
    epic: str, timeframe: str = "1h"
) -> dict[str, int]:
    """Compute walk-forward window sizes in bars for ``epic`` + ``timeframe``.

    Anchored on calendar days × `bars_per_calendar_day`, so the
    calendar-time coverage of train/val/test/step windows is consistent
    across asset classes.

    Returns:
        Dict with keys ``train_window``, ``val_window``, ``test_window``,
        ``step_size`` — directly consumable by ``WalkForwardSplitter``.

    Raises:
        ValueError: if ``timeframe`` is unrecognized.
    """
    spec = get_window_spec(epic)
    factor = _TIMEFRAME_FACTOR.get(timeframe.strip().lower())
    if factor is None:
        raise ValueError(
            f"Unknown timeframe '{timeframe}'. Supported: "
            f"{sorted(_TIMEFRAME_FACTOR)}"
        )

    bpd = spec.bars_per_calendar_day * factor
    return {
        "train_window": max(1, int(round(spec.train_calendar_days * bpd))),
        "val_window": max(1, int(round(spec.val_calendar_days * bpd))),
        "test_window": max(1, int(round(spec.test_calendar_days * bpd))),
        "step_size": max(1, int(round(spec.step_calendar_days * bpd))),
    }
