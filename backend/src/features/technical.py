"""
Technical indicators module.
Pure Polars/numpy implementation (no ta-lib dependency).
All indicators operate on Polars DataFrames with standard OHLCV columns.
"""

import numpy as np
import polars as pl


class TechnicalIndicators:
    """
    Collection of technical indicators implemented in pure Polars/numpy.

    All methods are static and take a pl.DataFrame with standard
    OHLCV columns (open, high, low, close, volume) as input.
    They return the input DataFrame with additional indicator columns appended.
    """

    # ===== Trend Indicators =====

    @staticmethod
    def add_ema(df: pl.DataFrame, column: str = "close", periods: list[int] | None = None) -> pl.DataFrame:
        """
        Add Exponential Moving Averages.

        Args:
            df: DataFrame with price data
            column: Column to calculate EMA on
            periods: List of EMA periods (default: [8, 21, 50, 200])
        """
        if periods is None:
            periods = [8, 21, 50, 200]

        for period in periods:
            col_name = f"ema_{period}"
            df = df.with_columns(
                pl.col(column).ewm_mean(span=period, ignore_nulls=True).alias(col_name)
            )

        return df

    @staticmethod
    def add_ema_crossovers(df: pl.DataFrame) -> pl.DataFrame:
        """
        Add EMA crossover signals.
        Requires ema_8, ema_21, ema_50, ema_200 columns.
        Returns 1 for bullish cross, -1 for bearish cross, 0 otherwise.
        """
        for fast, slow in [(8, 21), (50, 200)]:
            fast_col = f"ema_{fast}"
            slow_col = f"ema_{slow}"
            cross_col = f"ema_cross_{fast}_{slow}"

            if fast_col not in df.columns or slow_col not in df.columns:
                continue

            df = df.with_columns(
                pl.when(
                    (pl.col(fast_col) > pl.col(slow_col))
                    & (pl.col(fast_col).shift(1) <= pl.col(slow_col).shift(1))
                )
                .then(1)
                .when(
                    (pl.col(fast_col) < pl.col(slow_col))
                    & (pl.col(fast_col).shift(1) >= pl.col(slow_col).shift(1))
                )
                .then(-1)
                .otherwise(0)
                .alias(cross_col)
            )

        return df

    @staticmethod
    def add_macd(
        df: pl.DataFrame,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
        column: str = "close",
    ) -> pl.DataFrame:
        """
        Add MACD (Moving Average Convergence Divergence).

        Adds columns: macd, macd_signal, macd_histogram
        """
        ema_fast = pl.col(column).ewm_mean(span=fast_period, ignore_nulls=True)
        ema_slow = pl.col(column).ewm_mean(span=slow_period, ignore_nulls=True)

        df = df.with_columns((ema_fast - ema_slow).alias("macd"))

        df = df.with_columns(
            pl.col("macd").ewm_mean(span=signal_period, ignore_nulls=True).alias("macd_signal")
        )

        df = df.with_columns((pl.col("macd") - pl.col("macd_signal")).alias("macd_histogram"))

        return df

    @staticmethod
    def add_adx(df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
        """
        Add ADX (Average Directional Index).

        Adds columns: adx, plus_di, minus_di
        """
        # True Range components
        df = df.with_columns(
            [
                (pl.col("high") - pl.col("low")).alias("_tr1"),
                (pl.col("high") - pl.col("close").shift(1)).abs().alias("_tr2"),
                (pl.col("low") - pl.col("close").shift(1)).abs().alias("_tr3"),
            ]
        )

        # True Range = max of the three
        df = df.with_columns(
            pl.max_horizontal("_tr1", "_tr2", "_tr3").alias("_true_range")
        )

        # +DM and -DM
        df = df.with_columns(
            [
                (pl.col("high") - pl.col("high").shift(1)).alias("_up_move"),
                (pl.col("low").shift(1) - pl.col("low")).alias("_down_move"),
            ]
        )

        df = df.with_columns(
            [
                pl.when((pl.col("_up_move") > pl.col("_down_move")) & (pl.col("_up_move") > 0))
                .then(pl.col("_up_move"))
                .otherwise(0.0)
                .alias("_plus_dm"),
                pl.when((pl.col("_down_move") > pl.col("_up_move")) & (pl.col("_down_move") > 0))
                .then(pl.col("_down_move"))
                .otherwise(0.0)
                .alias("_minus_dm"),
            ]
        )

        # Smoothed averages using EWM (Wilder's smoothing = EWM with alpha=1/period)
        df = df.with_columns(
            [
                pl.col("_true_range")
                .ewm_mean(alpha=1.0 / period, ignore_nulls=True)
                .alias("_atr_smooth"),
                pl.col("_plus_dm")
                .ewm_mean(alpha=1.0 / period, ignore_nulls=True)
                .alias("_plus_dm_smooth"),
                pl.col("_minus_dm")
                .ewm_mean(alpha=1.0 / period, ignore_nulls=True)
                .alias("_minus_dm_smooth"),
            ]
        )

        # +DI and -DI (guard against atr_smooth=0)
        df = df.with_columns(
            [
                (100.0 * pl.col("_plus_dm_smooth") / pl.col("_atr_smooth"))
                .fill_nan(0.0)
                .alias("plus_di"),
                (100.0 * pl.col("_minus_dm_smooth") / pl.col("_atr_smooth"))
                .fill_nan(0.0)
                .alias("minus_di"),
            ]
        )

        # DX
        df = df.with_columns(
            (
                100.0
                * (pl.col("plus_di") - pl.col("minus_di")).abs()
                / (pl.col("plus_di") + pl.col("minus_di"))
            )
            .fill_nan(0.0)
            .alias("_dx")
        )

        # ADX = smoothed DX
        df = df.with_columns(
            pl.col("_dx").ewm_mean(alpha=1.0 / period, ignore_nulls=True).alias("adx")
        )

        # Drop temporary columns
        temp_cols = [c for c in df.columns if c.startswith("_")]
        df = df.drop(temp_cols)

        return df

    # ===== Mean Reversion Indicators =====

    @staticmethod
    def add_rsi(df: pl.DataFrame, period: int = 14, column: str = "close") -> pl.DataFrame:
        """
        Add RSI (Relative Strength Index).

        Adds column: rsi_{period}
        """
        col_name = f"rsi_{period}"

        # Price changes
        df = df.with_columns(pl.col(column).diff().alias("_change"))

        # Separate gains and losses
        df = df.with_columns(
            [
                pl.when(pl.col("_change") > 0)
                .then(pl.col("_change"))
                .otherwise(0.0)
                .alias("_gain"),
                pl.when(pl.col("_change") < 0)
                .then(-pl.col("_change"))
                .otherwise(0.0)
                .alias("_loss"),
            ]
        )

        # Wilder's smoothing (EWM with alpha=1/period)
        df = df.with_columns(
            [
                pl.col("_gain")
                .ewm_mean(alpha=1.0 / period, ignore_nulls=True)
                .alias("_avg_gain"),
                pl.col("_loss")
                .ewm_mean(alpha=1.0 / period, ignore_nulls=True)
                .alias("_avg_loss"),
            ]
        )

        # RS and RSI
        df = df.with_columns(
            pl.when(pl.col("_avg_loss") == 0)
            .then(100.0)
            .otherwise(100.0 - (100.0 / (1.0 + pl.col("_avg_gain") / pl.col("_avg_loss"))))
            .alias(col_name)
        )

        # Drop temporary columns
        df = df.drop(["_change", "_gain", "_loss", "_avg_gain", "_avg_loss"])

        return df

    @staticmethod
    def add_bollinger_bands(
        df: pl.DataFrame,
        period: int = 20,
        num_std: float = 2.0,
        column: str = "close",
    ) -> pl.DataFrame:
        """
        Add Bollinger Bands.

        Adds columns: bb_upper, bb_lower, bb_middle, bb_width, bb_pctb
        """
        # Middle band (SMA)
        df = df.with_columns(
            pl.col(column).rolling_mean(window_size=period).alias("bb_middle")
        )

        # Standard deviation
        df = df.with_columns(
            pl.col(column).rolling_std(window_size=period).alias("_bb_std")
        )

        # Upper and lower bands
        df = df.with_columns(
            [
                (pl.col("bb_middle") + num_std * pl.col("_bb_std")).alias("bb_upper"),
                (pl.col("bb_middle") - num_std * pl.col("_bb_std")).alias("bb_lower"),
            ]
        )

        # Bandwidth = (upper - lower) / middle (guard against middle=0)
        df = df.with_columns(
            ((pl.col("bb_upper") - pl.col("bb_lower")) / pl.col("bb_middle"))
            .fill_nan(0.0)
            .alias("bb_width")
        )

        # %B = (close - lower) / (upper - lower)
        df = df.with_columns(
            (
                (pl.col(column) - pl.col("bb_lower"))
                / (pl.col("bb_upper") - pl.col("bb_lower"))
            )
            .fill_nan(0.5)
            .alias("bb_pctb")
        )

        df = df.drop(["_bb_std"])

        return df

    # ===== Volatility Indicators =====

    @staticmethod
    def add_atr(df: pl.DataFrame, period: int = 14) -> pl.DataFrame:
        """
        Add ATR (Average True Range).

        Adds columns: atr_{period}, atr_ratio
        """
        col_name = f"atr_{period}"

        # True Range
        df = df.with_columns(
            [
                (pl.col("high") - pl.col("low")).alias("_tr1"),
                (pl.col("high") - pl.col("close").shift(1)).abs().alias("_tr2"),
                (pl.col("low") - pl.col("close").shift(1)).abs().alias("_tr3"),
            ]
        )

        df = df.with_columns(
            pl.max_horizontal("_tr1", "_tr2", "_tr3").alias("_true_range")
        )

        # ATR using Wilder's smoothing
        df = df.with_columns(
            pl.col("_true_range")
            .ewm_mean(alpha=1.0 / period, ignore_nulls=True)
            .alias(col_name)
        )

        # ATR ratio (normalized volatility, guard against close=0)
        df = df.with_columns(
            (pl.col(col_name) / pl.col("close"))
            .fill_nan(0.0)
            .alias("atr_ratio")
        )

        df = df.drop(["_tr1", "_tr2", "_tr3", "_true_range"])

        return df

    @staticmethod
    def add_historical_volatility(
        df: pl.DataFrame, period: int = 20, column: str = "close"
    ) -> pl.DataFrame:
        """
        Add historical (realized) volatility.

        Adds column: hvol_{period}
        """
        col_name = f"hvol_{period}"

        # Log returns
        df = df.with_columns(
            (pl.col(column) / pl.col(column).shift(1)).log().alias("_log_return")
        )

        # Rolling standard deviation of log returns, annualized
        df = df.with_columns(
            (pl.col("_log_return").rolling_std(window_size=period) * np.sqrt(252)).alias(col_name)
        )

        df = df.drop(["_log_return"])

        return df

    # ===== Volume Indicators =====

    @staticmethod
    def add_obv(df: pl.DataFrame) -> pl.DataFrame:
        """
        Add OBV (On-Balance Volume).

        Adds column: obv
        """
        # Volume direction: +volume if close > prev close, -volume if close < prev close
        df = df.with_columns(
            pl.when(pl.col("close") > pl.col("close").shift(1))
            .then(pl.col("volume"))
            .when(pl.col("close") < pl.col("close").shift(1))
            .then(-pl.col("volume"))
            .otherwise(0)
            .alias("_vol_direction")
        )

        df = df.with_columns(pl.col("_vol_direction").cum_sum().alias("obv"))

        df = df.drop(["_vol_direction"])

        return df

    @staticmethod
    def add_volume_sma_ratio(df: pl.DataFrame, period: int = 20) -> pl.DataFrame:
        """
        Add volume relative to its moving average.

        Adds column: volume_sma_ratio
        """
        df = df.with_columns(
            (pl.col("volume") / pl.col("volume").rolling_mean(window_size=period))
            .fill_nan(1.0)
            .alias("volume_sma_ratio")
        )

        return df

    # ===== Price Action Features =====

    @staticmethod
    def add_returns(df: pl.DataFrame, periods: list[int] | None = None) -> pl.DataFrame:
        """
        Add log returns at different lags.

        Adds columns: returns_{N} for each period
        """
        if periods is None:
            periods = [1, 5, 20]

        for period in periods:
            col_name = f"returns_{period}"
            df = df.with_columns(
                (pl.col("close") / pl.col("close").shift(period)).log().alias(col_name)
            )

        return df

    @staticmethod
    def add_price_action(df: pl.DataFrame) -> pl.DataFrame:
        """
        Add price action features.

        Adds columns: high_low_range, close_position
        """
        # Intraday range normalized by close (guard against close=0)
        df = df.with_columns(
            ((pl.col("high") - pl.col("low")) / pl.col("close"))
            .fill_nan(0.0)
            .alias("high_low_range")
        )

        # Where close is in the high-low range (0=low, 1=high)
        df = df.with_columns(
            (
                (pl.col("close") - pl.col("low"))
                / (pl.col("high") - pl.col("low"))
            )
            .fill_nan(0.5)
            .alias("close_position")
        )

        return df

    # ===== Convenience Methods =====

    @staticmethod
    def add_all_indicators(
        df: pl.DataFrame,
        ema_periods: list[int] | None = None,
        rsi_period: int = 14,
        bb_period: int = 20,
        atr_period: int = 14,
        adx_period: int = 14,
        hvol_period: int = 20,
        return_periods: list[int] | None = None,
        include_volume: bool = True,
    ) -> pl.DataFrame:
        """
        Add all technical indicators to a DataFrame.

        Args:
            df: DataFrame with OHLCV columns
            ema_periods: EMA periods (default: [8, 21, 50, 200])
            rsi_period: RSI period
            bb_period: Bollinger Bands period
            atr_period: ATR period
            adx_period: ADX period
            hvol_period: Historical volatility period
            return_periods: Return lag periods (default: [1, 5, 20])
            include_volume: Include volume indicators (requires volume column)

        Returns:
            DataFrame with all indicator columns added
        """
        ti = TechnicalIndicators

        # Trend
        df = ti.add_ema(df, periods=ema_periods)
        df = ti.add_ema_crossovers(df)
        df = ti.add_macd(df)
        df = ti.add_adx(df, period=adx_period)

        # Mean reversion
        df = ti.add_rsi(df, period=rsi_period)
        df = ti.add_bollinger_bands(df, period=bb_period)

        # Volatility
        df = ti.add_atr(df, period=atr_period)
        df = ti.add_historical_volatility(df, period=hvol_period)

        # Volume (only if column exists and has non-null values)
        if include_volume and "volume" in df.columns:
            has_volume = df["volume"].null_count() < len(df) and df["volume"].sum() > 0
            if has_volume:
                df = ti.add_obv(df)
                df = ti.add_volume_sma_ratio(df)

        # Price action
        df = ti.add_returns(df, periods=return_periods)
        df = ti.add_price_action(df)

        return df
