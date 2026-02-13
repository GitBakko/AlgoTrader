"""
Keltner Channel indicator.
EMA-based channel with ATR bands, used for true squeeze detection.
"""

import polars as pl


class KeltnerChannel:
    """
    Keltner Channel: EMA center line with ATR-based upper/lower bands.

    KC Upper = EMA(close, period) + multiplier * ATR(period)
    KC Lower = EMA(close, period) - multiplier * ATR(period)
    """

    @staticmethod
    def add_keltner(
        df: pl.DataFrame,
        ema_period: int = 20,
        atr_period: int = 14,
        multiplier: float = 1.5,
    ) -> pl.DataFrame:
        """
        Add Keltner Channel to DataFrame.

        Args:
            df: DataFrame with 'close', 'high', 'low' columns
            ema_period: EMA period for center line
            atr_period: ATR period for band width
            multiplier: ATR multiplier for band distance

        Returns:
            DataFrame with kc_upper, kc_middle, kc_lower columns added.
        """
        # Center line = EMA
        kc_middle_name = "kc_middle"
        if kc_middle_name not in df.columns:
            df = df.with_columns(
                pl.col("close").ewm_mean(span=ema_period, ignore_nulls=True)
                .alias(kc_middle_name)
            )

        # ATR (simplified inline to avoid dependency on TechnicalIndicators)
        atr_col = f"_kc_atr_{atr_period}"
        if atr_col not in df.columns:
            df = df.with_columns([
                (pl.col("high") - pl.col("low")).alias("_kc_tr1"),
                (pl.col("high") - pl.col("close").shift(1)).abs().alias("_kc_tr2"),
                (pl.col("low") - pl.col("close").shift(1)).abs().alias("_kc_tr3"),
            ])
            df = df.with_columns(
                pl.max_horizontal("_kc_tr1", "_kc_tr2", "_kc_tr3").alias("_kc_tr")
            )
            df = df.with_columns(
                pl.col("_kc_tr").ewm_mean(span=atr_period, ignore_nulls=True)
                .alias(atr_col)
            )
            df = df.drop(["_kc_tr1", "_kc_tr2", "_kc_tr3", "_kc_tr"])

        # Upper and lower bands
        df = df.with_columns([
            (pl.col(kc_middle_name) + multiplier * pl.col(atr_col)).alias("kc_upper"),
            (pl.col(kc_middle_name) - multiplier * pl.col(atr_col)).alias("kc_lower"),
        ])

        # Clean up temp ATR column
        df = df.drop([atr_col])

        return df

    @staticmethod
    def add_true_squeeze(
        df: pl.DataFrame,
        bb_period: int = 20,
        bb_std: float = 2.0,
        kc_ema_period: int = 20,
        kc_atr_period: int = 14,
        kc_multiplier: float = 1.5,
    ) -> pl.DataFrame:
        """
        Add true squeeze detection (BB inside KC).

        Squeeze = BB upper < KC upper AND BB lower > KC lower.
        This is more reliable than simple bandwidth-based squeeze detection.

        Args:
            df: DataFrame with OHLC columns
            bb_period: Bollinger Bands period
            bb_std: Bollinger Bands std deviation
            kc_ema_period: Keltner Channel EMA period
            kc_atr_period: Keltner Channel ATR period
            kc_multiplier: Keltner Channel ATR multiplier

        Returns:
            DataFrame with squeeze_on, squeeze_off, squeeze_momentum columns.
        """
        # Ensure BB columns exist
        if "bb_upper" not in df.columns:
            from src.features.technical import TechnicalIndicators
            df = TechnicalIndicators.add_bollinger_bands(df, period=bb_period, num_std=bb_std)

        # Ensure KC columns exist
        if "kc_upper" not in df.columns:
            df = KeltnerChannel.add_keltner(
                df,
                ema_period=kc_ema_period,
                atr_period=kc_atr_period,
                multiplier=kc_multiplier,
            )

        # True squeeze: BB inside KC
        df = df.with_columns(
            pl.when(
                (pl.col("bb_upper") < pl.col("kc_upper"))
                & (pl.col("bb_lower") > pl.col("kc_lower"))
            )
            .then(1)
            .otherwise(0)
            .alias("squeeze_on")
        )

        # Squeeze release: was squeeze, now not
        df = df.with_columns(
            pl.when(
                (pl.col("squeeze_on") == 0)
                & (pl.col("squeeze_on").shift(1) == 1)
            )
            .then(1)
            .otherwise(0)
            .alias("squeeze_off")
        )

        # Momentum direction at squeeze release (MACD histogram direction)
        if "macd_histogram" in df.columns:
            df = df.with_columns(
                pl.when(pl.col("squeeze_off") == 1)
                .then(
                    pl.when(pl.col("macd_histogram") > 0).then(1).otherwise(-1)
                )
                .otherwise(0)
                .alias("squeeze_momentum")
            )
        else:
            df = df.with_columns(pl.lit(0).alias("squeeze_momentum"))

        return df
