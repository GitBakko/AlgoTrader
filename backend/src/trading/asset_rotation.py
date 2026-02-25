"""
Asset momentum rotation.
Selects tradeable assets based on rolling momentum score.
Only assets with positive momentum and in the top 50% are traded.
"""

import polars as pl
from loguru import logger

from src.utils.constants import TRADABLE_ASSETS


def compute_momentum_scores(
    data_access,
    lookback_days: int = 63,
    skip_recent_days: int = 5,
) -> dict[str, float]:
    """
    Compute risk-adjusted momentum for each tradeable asset.

    Uses (lookback - skip_recent) days of returns, skipping the most recent
    days to avoid short-term reversal effect.

    Returns: dict of {epic: momentum_score}
    """
    scores = {}
    for epic in TRADABLE_ASSETS:
        try:
            df = data_access.get_candles(epic, "1d", limit=lookback_days + skip_recent_days + 5)
            if df.is_empty() or len(df) < 20:
                continue

            # Calculate daily returns
            df = df.sort("timestamp")
            df = df.with_columns(
                (pl.col("close") / pl.col("close").shift(1) - 1).alias("return")
            ).drop_nulls("return")

            returns = df["return"].to_list()

            if len(returns) < 20:
                continue

            # Skip most recent days (reversal effect), use prior lookback days
            if len(returns) > skip_recent_days:
                momentum_window = returns[:-skip_recent_days] if skip_recent_days > 0 else returns
                momentum_window = momentum_window[-lookback_days:]
            else:
                momentum_window = returns

            if not momentum_window:
                continue

            # Momentum = cumulative return
            cum_return = 1.0
            for r in momentum_window:
                cum_return *= (1 + r)
            momentum = cum_return - 1.0

            # Volatility for risk-adjustment
            mean_r = sum(momentum_window) / len(momentum_window)
            vol = (sum((r - mean_r) ** 2 for r in momentum_window) / len(momentum_window)) ** 0.5

            # Risk-adjusted momentum
            scores[epic] = momentum / max(vol, 1e-8)

        except Exception as e:
            logger.warning(f"Momentum calc failed for {epic}: {e}")

    return scores


def select_active_assets(
    momentum_scores: dict[str, float],
    top_pct: float = 0.75,
    min_assets: int = 10,
) -> list[str]:
    """
    Select top assets by risk-adjusted momentum.
    Only includes assets with positive momentum.

    Returns: list of epics to trade
    """
    # Filter: only positive momentum
    positive = {k: v for k, v in momentum_scores.items() if v > 0}

    # Rank by score descending
    ranked = sorted(positive.items(), key=lambda x: x[1], reverse=True)

    # Take top N%
    n_select = max(min_assets, int(len(TRADABLE_ASSETS) * top_pct))
    selected = [epic for epic, _ in ranked[:n_select]]

    # If fewer than min_assets have positive momentum, include top by absolute score
    if len(selected) < min_assets:
        all_ranked = sorted(momentum_scores.items(), key=lambda x: x[1], reverse=True)
        for epic, _ in all_ranked:
            if epic not in selected:
                selected.append(epic)
            if len(selected) >= min_assets:
                break

    return selected
