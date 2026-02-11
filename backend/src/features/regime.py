"""
Market regime detection module.
Classifies market conditions as trending up, trending down, or ranging.
"""

import polars as pl

from src.features.schemas import MarketRegime


class RegimeDetector:
    """
    Detects market regime using ADX and EMA slope.

    Rules:
    - ADX > adx_threshold + EMA slope > 0 = TRENDING_UP
    - ADX > adx_threshold + EMA slope < 0 = TRENDING_DOWN
    - ADX <= adx_threshold = RANGING
    """

    def __init__(
        self,
        adx_threshold: float = 25.0,
        ema_period: int = 50,
        slope_lookback: int = 5,
    ):
        """
        Args:
            adx_threshold: ADX threshold for trending vs ranging
            ema_period: EMA period for trend direction
            slope_lookback: Bars to look back for slope calculation
        """
        self.adx_threshold = adx_threshold
        self.ema_period = ema_period
        self.slope_lookback = slope_lookback

    def detect(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Add regime column to DataFrame.

        Requires 'adx' and f'ema_{ema_period}' columns.
        Adds 'regime' column with MarketRegime values.
        """
        ema_col = f"ema_{self.ema_period}"

        if "adx" not in df.columns or ema_col not in df.columns:
            raise ValueError(
                f"DataFrame must contain 'adx' and '{ema_col}' columns. "
                "Run TechnicalIndicators.add_adx() and add_ema() first."
            )

        # EMA slope: positive = uptrend, negative = downtrend
        df = df.with_columns(
            (pl.col(ema_col) - pl.col(ema_col).shift(self.slope_lookback)).alias("_ema_slope")
        )

        # Classify regime
        df = df.with_columns(
            pl.when(
                (pl.col("adx") > self.adx_threshold) & (pl.col("_ema_slope") > 0)
            )
            .then(pl.lit(MarketRegime.TRENDING_UP.value))
            .when(
                (pl.col("adx") > self.adx_threshold) & (pl.col("_ema_slope") <= 0)
            )
            .then(pl.lit(MarketRegime.TRENDING_DOWN.value))
            .otherwise(pl.lit(MarketRegime.RANGING.value))
            .alias("regime")
        )

        df = df.drop(["_ema_slope"])

        return df
