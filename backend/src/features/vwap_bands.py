"""
Rolling VWAP with standard deviation bands.
Used for mean-reversion strategies in ranging markets.
"""

import polars as pl


class VWAPBands:
    """
    Rolling VWAP with SD bands for mean-reversion analysis.

    VWAP = cumulative(TP * volume) / cumulative(volume)
    SD = rolling standard deviation of close - VWAP
    Upper = VWAP + N * SD, Lower = VWAP - N * SD
    """

    @staticmethod
    def add_vwap_bands(
        df: pl.DataFrame,
        vwap_period: int = 50,
        sd_period: int = 20,
        num_sd: list[float] | None = None,
    ) -> pl.DataFrame:
        """
        Add rolling VWAP with SD bands.

        Uses a rolling window (default 50 bars) instead of cumulative VWAP
        to keep the indicator responsive to recent price/volume action.
        For 15-min bars, 50 bars ≈ 12.5 hours of trading.

        Args:
            df: DataFrame with close, high, low, volume columns
            vwap_period: Rolling window for VWAP calculation (bars)
            sd_period: Rolling window for SD calculation
            num_sd: SD multiples for bands (default: [1, 2, 3])

        Returns:
            DataFrame with vwap_rolling, vwap_sd, vwap_upper_N, vwap_lower_N,
            vwap_z_score columns added.
        """
        if num_sd is None:
            num_sd = [1.0, 2.0, 3.0]

        if "volume" not in df.columns:
            return df

        has_volume = df["volume"].null_count() < len(df) and df["volume"].sum() > 0
        if not has_volume:
            return df

        # Typical price
        tp = (pl.col("high") + pl.col("low") + pl.col("close")) / 3.0

        # Rolling VWAP: sum(TP * volume) / sum(volume) over window
        df = df.with_columns([
            (tp * pl.col("volume")).alias("_tp_vol"),
        ])

        df = df.with_columns([
            pl.col("_tp_vol")
            .rolling_sum(window_size=vwap_period)
            .alias("_tp_vol_roll"),
            pl.col("volume")
            .rolling_sum(window_size=vwap_period)
            .alias("_vol_roll"),
        ])

        df = df.with_columns(
            pl.when(pl.col("_vol_roll") > 0)
            .then(pl.col("_tp_vol_roll") / pl.col("_vol_roll"))
            .otherwise(pl.col("close"))
            .fill_nan(pl.col("close"))
            .alias("vwap_rolling")
        )

        # Deviation from VWAP
        df = df.with_columns(
            (pl.col("close") - pl.col("vwap_rolling")).alias("_vwap_dev")
        )

        # Rolling SD of deviation
        df = df.with_columns(
            pl.col("_vwap_dev")
            .rolling_std(window_size=sd_period)
            .fill_null(0.0)
            .alias("vwap_sd")
        )

        # Z-score: how far close is from VWAP in SD units
        # When SD=0 (flat price), z-score is 0 (no statistical deviation)
        df = df.with_columns(
            pl.when(pl.col("vwap_sd") > 0)
            .then(pl.col("_vwap_dev") / pl.col("vwap_sd"))
            .otherwise(0.0)
            .fill_nan(0.0)
            .alias("vwap_z_score")
        )

        # SD bands
        for n in num_sd:
            suffix = str(n).replace(".", "")
            df = df.with_columns([
                (pl.col("vwap_rolling") + n * pl.col("vwap_sd"))
                .alias(f"vwap_upper_{suffix}"),
                (pl.col("vwap_rolling") - n * pl.col("vwap_sd"))
                .alias(f"vwap_lower_{suffix}"),
            ])

        # Cleanup
        df = df.drop(["_tp_vol", "_tp_vol_roll", "_vol_roll", "_vwap_dev"])

        return df
