"""
Mean Reversion Target Builder.

For each bar where the price is at an extreme (|z_score| > threshold),
looks ahead N bars to determine if the price reverted to the mean.

Target:
  1 (GOOD_SETUP): price returned to mean within horizon
  0 (BAD_SETUP): price kept extending or didn't revert in time
  NaN: not an extreme setup (excluded from training)
"""

import numpy as np
import polars as pl
from loguru import logger


class MRTargetBuilder:
    """Build binary targets for mean reversion quality scoring."""

    def __init__(
        self,
        z_threshold: float = 2.0,
        horizon_bars: int = 12,
        mean_column: str = "bb_middle",
    ):
        self.z_threshold = z_threshold
        self.horizon_bars = horizon_bars
        self.mean_column = mean_column

    def _compute_z_score(self, df: pl.DataFrame) -> pl.Series:
        """Compute composite z-score from BB %B and VWAP z-score."""
        bb_z = (df["bb_pctb"] - 0.5) * 4 if "bb_pctb" in df.columns else pl.Series([0.0] * len(df))
        vwap_z = df["vwap_z_score"] if "vwap_z_score" in df.columns else pl.Series([0.0] * len(df))

        # Use whichever has larger magnitude
        if isinstance(bb_z, pl.Series) and isinstance(vwap_z, pl.Series):
            bb_arr = bb_z.to_numpy()
            vwap_arr = vwap_z.to_numpy()
            composite = np.where(np.abs(vwap_arr) > np.abs(bb_arr), vwap_arr, bb_arr)
            return pl.Series("z_score", composite)
        return vwap_z

    def build_targets(self, df: pl.DataFrame) -> pl.DataFrame:
        """Build mean reversion quality targets.

        For each bar where |z_score| > threshold:
          - Look ahead `horizon_bars`
          - If close price crosses the mean within horizon: target = 1 (GOOD)
          - Otherwise: target = 0 (BAD)

        Bars where |z_score| <= threshold: target = NaN (not a setup)

        Args:
            df: DataFrame with 'close', 'bb_pctb' or 'vwap_z_score',
                and mean_column ('bb_middle' or 'vwap')

        Returns:
            DataFrame with 'target' and 'z_score_target' columns added
        """
        n = len(df)
        z_scores = self._compute_z_score(df)
        close = df["close"].to_numpy()

        # Get mean values
        if self.mean_column in df.columns:
            mean_vals = df[self.mean_column].to_numpy()
        else:
            # Fallback: 20-period SMA
            mean_vals = np.convolve(close, np.ones(20) / 20, mode="same")

        targets = np.full(n, np.nan)
        z_arr = z_scores.to_numpy()

        for i in range(n - self.horizon_bars):
            z = z_arr[i]
            if abs(z) < self.z_threshold:
                continue  # Not a setup

            # Look ahead
            is_sell_setup = z > self.z_threshold  # Price above mean
            reverted = False

            for j in range(1, self.horizon_bars + 1):
                future_close = close[i + j]
                future_mean = mean_vals[i + j]

                if is_sell_setup and future_close <= future_mean:
                    reverted = True
                    break
                elif not is_sell_setup and future_close >= future_mean:
                    reverted = True
                    break

            targets[i] = 1.0 if reverted else 0.0

        result = df.with_columns(
            [
                pl.Series("target", targets),
                z_scores.alias("z_score_target"),
            ]
        )

        # Stats
        valid = ~np.isnan(targets)
        if valid.sum() > 0:
            good = (targets[valid] == 1).sum()
            bad = (targets[valid] == 0).sum()
            logger.info(
                f"MR targets: {valid.sum()} setups "
                f"({good} good/{bad} bad, "
                f"reversion rate {good / valid.sum() * 100:.1f}%)"
            )
        else:
            logger.warning("MR targets: no valid setups found")

        return result

    def get_class_distribution(self, df: pl.DataFrame) -> dict:
        """Return distribution of target classes."""
        if "target" not in df.columns:
            return {}
        targets = df["target"].to_numpy()
        valid = ~np.isnan(targets)
        return {
            "total_bars": len(df),
            "setup_bars": int(valid.sum()),
            "good_setups": (int((targets[valid] == 1).sum()) if valid.sum() > 0 else 0),
            "bad_setups": (int((targets[valid] == 0).sum()) if valid.sum() > 0 else 0),
            "reversion_rate": (float((targets[valid] == 1).mean()) if valid.sum() > 0 else 0),
        }
