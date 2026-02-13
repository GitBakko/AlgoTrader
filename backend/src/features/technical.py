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

    # ===== Advanced Indicators =====

    @staticmethod
    def add_stochastic_rsi(
        df: pl.DataFrame,
        rsi_period: int = 14,
        stoch_period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3,
    ) -> pl.DataFrame:
        """
        Add Stochastic RSI (StochRSI).

        Applies stochastic oscillator formula to RSI values.
        More sensitive to overbought/oversold than standard RSI.

        Adds columns: stoch_rsi_k, stoch_rsi_d
        """
        rsi_col = f"rsi_{rsi_period}"

        # Ensure RSI exists
        if rsi_col not in df.columns:
            df = TechnicalIndicators.add_rsi(df, period=rsi_period)

        # StochRSI = (RSI - RSI_min) / (RSI_max - RSI_min)
        df = df.with_columns(
            [
                pl.col(rsi_col).rolling_min(window_size=stoch_period).alias("_rsi_min"),
                pl.col(rsi_col).rolling_max(window_size=stoch_period).alias("_rsi_max"),
            ]
        )

        df = df.with_columns(
            (
                (pl.col(rsi_col) - pl.col("_rsi_min"))
                / (pl.col("_rsi_max") - pl.col("_rsi_min"))
            )
            .fill_nan(0.5)
            .alias("_stoch_rsi_raw")
        )

        # %K = SMA of raw StochRSI
        df = df.with_columns(
            pl.col("_stoch_rsi_raw")
            .rolling_mean(window_size=smooth_k)
            .alias("stoch_rsi_k")
        )

        # %D = SMA of %K
        df = df.with_columns(
            pl.col("stoch_rsi_k")
            .rolling_mean(window_size=smooth_d)
            .alias("stoch_rsi_d")
        )

        df = df.drop(["_rsi_min", "_rsi_max", "_stoch_rsi_raw"])

        return df

    @staticmethod
    def add_bollinger_squeeze(
        df: pl.DataFrame,
        bb_period: int = 20,
        squeeze_threshold: float = 0.03,
    ) -> pl.DataFrame:
        """
        Detect Bollinger Band squeeze (low volatility -> pending breakout).

        Squeeze = bb_width < threshold (bandwidth contracting).
        Adds columns: bb_squeeze (1=squeeze, 0=normal), bb_squeeze_duration
        """
        if "bb_width" not in df.columns:
            df = TechnicalIndicators.add_bollinger_bands(df, period=bb_period)

        # Squeeze detection
        df = df.with_columns(
            pl.when(pl.col("bb_width") < squeeze_threshold)
            .then(1)
            .otherwise(0)
            .alias("bb_squeeze")
        )

        # Squeeze duration (consecutive bars in squeeze)
        squeeze_vals = df["bb_squeeze"].to_numpy()
        duration = np.zeros(len(squeeze_vals), dtype=np.int32)
        count = 0
        for i in range(len(squeeze_vals)):
            if squeeze_vals[i] == 1:
                count += 1
            else:
                count = 0
            duration[i] = count

        df = df.with_columns(
            pl.Series("bb_squeeze_duration", duration)
        )

        return df

    @staticmethod
    def add_rsi_divergence(
        df: pl.DataFrame,
        lookback: int = 14,
        rsi_period: int = 14,
    ) -> pl.DataFrame:
        """
        Detect RSI divergence (price vs RSI disagreement).

        Bullish divergence: price makes lower low but RSI makes higher low
        Bearish divergence: price makes higher high but RSI makes lower high

        Adds column: rsi_divergence (+1=bullish, -1=bearish, 0=none)
        """
        rsi_col = f"rsi_{rsi_period}"
        if rsi_col not in df.columns:
            df = TechnicalIndicators.add_rsi(df, period=rsi_period)

        # Rolling min/max over lookback period
        df = df.with_columns(
            [
                pl.col("close").rolling_min(window_size=lookback).alias("_price_min"),
                pl.col("close").rolling_max(window_size=lookback).alias("_price_max"),
                pl.col(rsi_col).rolling_min(window_size=lookback).alias("_rsi_min"),
                pl.col(rsi_col).rolling_max(window_size=lookback).alias("_rsi_max"),
            ]
        )

        # Price change and RSI change vs their lookback min/max
        df = df.with_columns(
            [
                (pl.col("close") - pl.col("_price_min")).alias("_price_vs_min"),
                (pl.col("close") - pl.col("_price_max")).alias("_price_vs_max"),
                (pl.col(rsi_col) - pl.col("_rsi_min")).alias("_rsi_vs_min"),
                (pl.col(rsi_col) - pl.col("_rsi_max")).alias("_rsi_vs_max"),
            ]
        )

        # Bullish: price near recent low but RSI rising (not at its low)
        # Bearish: price near recent high but RSI falling (not at its high)
        df = df.with_columns(
            pl.when(
                (pl.col("_price_vs_min") < pl.col("_price_vs_max").abs() * 0.1)
                & (pl.col("_rsi_vs_min") > 5.0)
            )
            .then(1)
            .when(
                (pl.col("_price_vs_max").abs() < pl.col("_price_vs_min") * 0.1)
                & (pl.col("_rsi_vs_max").abs() > 5.0)
            )
            .then(-1)
            .otherwise(0)
            .alias("rsi_divergence")
        )

        temp_cols = [
            c for c in df.columns
            if c.startswith("_price_vs") or c.startswith("_rsi_v")
            or c in ("_price_min", "_price_max", "_rsi_min", "_rsi_max")
        ]
        df = df.drop(temp_cols)

        return df

    @staticmethod
    def add_vwap(df: pl.DataFrame) -> pl.DataFrame:
        """
        Add VWAP (Volume Weighted Average Price).

        Adds columns: vwap, vwap_distance (% distance from close to VWAP)
        """
        if "volume" not in df.columns:
            return df

        has_volume = df["volume"].null_count() < len(df) and df["volume"].sum() > 0
        if not has_volume:
            return df

        # Typical price
        df = df.with_columns(
            ((pl.col("high") + pl.col("low") + pl.col("close")) / 3.0).alias("_tp")
        )

        # Cumulative VWAP
        df = df.with_columns(
            [
                (pl.col("_tp") * pl.col("volume")).cum_sum().alias("_tp_vol_sum"),
                pl.col("volume").cum_sum().alias("_vol_sum"),
            ]
        )

        df = df.with_columns(
            (pl.col("_tp_vol_sum") / pl.col("_vol_sum"))
            .fill_nan(pl.col("close"))
            .alias("vwap")
        )

        # Distance from VWAP (normalized)
        df = df.with_columns(
            ((pl.col("close") - pl.col("vwap")) / pl.col("vwap"))
            .fill_nan(0.0)
            .alias("vwap_distance")
        )

        df = df.drop(["_tp", "_tp_vol_sum", "_vol_sum"])

        return df

    @staticmethod
    def add_session_features(df: pl.DataFrame) -> pl.DataFrame:
        """
        Add time-based session features using cyclical encoding.

        Uses sin/cos encoding for hour and day-of-week to capture
        cyclical patterns (23:00 is close to 00:00).

        Adds columns: hour_sin, hour_cos, dow_sin, dow_cos
        """
        if "timestamp" not in df.columns:
            return df

        df = df.with_columns(
            [
                pl.col("timestamp").dt.hour().alias("_hour"),
                pl.col("timestamp").dt.weekday().alias("_dow"),
            ]
        )

        # Cyclical encoding: sin/cos transform
        df = df.with_columns(
            [
                (2 * np.pi * pl.col("_hour") / 24.0).sin().alias("hour_sin"),
                (2 * np.pi * pl.col("_hour") / 24.0).cos().alias("hour_cos"),
                (2 * np.pi * pl.col("_dow") / 7.0).sin().alias("dow_sin"),
                (2 * np.pi * pl.col("_dow") / 7.0).cos().alias("dow_cos"),
            ]
        )

        df = df.drop(["_hour", "_dow"])

        return df

    # ===== Candlestick Patterns =====

    @staticmethod
    def add_candlestick_patterns(df: pl.DataFrame) -> pl.DataFrame:
        """
        Add 8 candlestick pattern features as binary columns.

        Adds columns: candle_hammer, candle_inv_hammer, candle_engulf_bull,
        candle_engulf_bear, candle_doji, candle_morning_star, candle_evening_star,
        candle_pin_bar
        """
        o = pl.col("open")
        h = pl.col("high")
        l = pl.col("low")
        c = pl.col("close")

        body = (c - o).abs()
        candle_range = h - l
        upper_wick = h - pl.max_horizontal(o, c)
        lower_wick = pl.min_horizontal(o, c) - l

        # Guard against zero range
        safe_range = pl.when(candle_range > 0).then(candle_range).otherwise(1.0)
        body_pct = body / safe_range

        # 1. Hammer: small body at top, long lower wick
        df = df.with_columns(
            pl.when(
                (body_pct < 0.3) & (lower_wick > body * 2) & (upper_wick < body)
            ).then(1).otherwise(0).alias("candle_hammer")
        )

        # 2. Inverted hammer: small body at bottom, long upper wick
        df = df.with_columns(
            pl.when(
                (body_pct < 0.3) & (upper_wick > body * 2) & (lower_wick < body)
            ).then(1).otherwise(0).alias("candle_inv_hammer")
        )

        # 3. Bullish engulfing: current bullish body engulfs previous bearish body
        prev_o = o.shift(1)
        prev_c = c.shift(1)
        df = df.with_columns(
            pl.when(
                (c > o)  # Current is bullish
                & (prev_c < prev_o)  # Previous is bearish
                & (o <= prev_c)  # Current open <= prev close
                & (c >= prev_o)  # Current close >= prev open
            ).then(1).otherwise(0).alias("candle_engulf_bull")
        )

        # 4. Bearish engulfing: current bearish body engulfs previous bullish body
        df = df.with_columns(
            pl.when(
                (c < o)  # Current is bearish
                & (prev_c > prev_o)  # Previous is bullish
                & (o >= prev_c)  # Current open >= prev close
                & (c <= prev_o)  # Current close <= prev open
            ).then(1).otherwise(0).alias("candle_engulf_bear")
        )

        # 5. Doji: very small body relative to range
        df = df.with_columns(
            pl.when(body_pct < 0.1).then(1).otherwise(0).alias("candle_doji")
        )

        # 6. Morning star: bearish + small body + bullish (3-bar pattern)
        prev2_o = o.shift(2)
        prev2_c = c.shift(2)
        prev_body_pct = (prev_c - prev_o).abs() / pl.when(
            (h.shift(1) - l.shift(1)) > 0
        ).then(h.shift(1) - l.shift(1)).otherwise(1.0)
        df = df.with_columns(
            pl.when(
                (prev2_c < prev2_o)  # Bar -2 is bearish
                & (prev_body_pct < 0.3)  # Bar -1 is small body
                & (c > o)  # Current is bullish
                & (c > (prev2_o + prev2_c) / 2)  # Close above midpoint of bar -2
            ).then(1).otherwise(0).alias("candle_morning_star")
        )

        # 7. Evening star: bullish + small body + bearish (3-bar pattern)
        df = df.with_columns(
            pl.when(
                (prev2_c > prev2_o)  # Bar -2 is bullish
                & (prev_body_pct < 0.3)  # Bar -1 is small body
                & (c < o)  # Current is bearish
                & (c < (prev2_o + prev2_c) / 2)  # Close below midpoint of bar -2
            ).then(1).otherwise(0).alias("candle_evening_star")
        )

        # 8. Pin bar: longest wick > 3x body
        max_wick = pl.max_horizontal(upper_wick, lower_wick)
        df = df.with_columns(
            pl.when(
                (max_wick > body * 3) & (body > 0)
            ).then(1).otherwise(0).alias("candle_pin_bar")
        )

        return df

    # ===== Fibonacci Levels =====

    @staticmethod
    def add_fibonacci_levels(
        df: pl.DataFrame,
        swing_lookback: int = 20,
        atr_period: int = 14,
    ) -> pl.DataFrame:
        """
        Add Fibonacci retracement level features.

        Uses rolling swing high/low to compute Fib levels,
        then measures distance from close to each level (normalized by ATR).

        Adds columns: fib_dist_236, fib_dist_382, fib_dist_500, fib_dist_618,
        fib_dist_786, fib_nearest_level, fib_cluster_strength
        """
        # Swing high/low detection via rolling window
        df = df.with_columns([
            pl.col("high").rolling_max(window_size=swing_lookback).alias("_swing_high"),
            pl.col("low").rolling_min(window_size=swing_lookback).alias("_swing_low"),
        ])

        # Ensure ATR exists
        atr_col = f"atr_{atr_period}"
        if atr_col not in df.columns:
            df = TechnicalIndicators.add_atr(df, period=atr_period)

        swing_range = pl.col("_swing_high") - pl.col("_swing_low")
        safe_atr = pl.when(pl.col(atr_col) > 0).then(pl.col(atr_col)).otherwise(1.0)

        # Fibonacci levels
        fib_levels = [0.236, 0.382, 0.500, 0.618, 0.786]
        fib_exprs = []
        fib_dist_cols = []

        for level in fib_levels:
            fib_price = pl.col("_swing_high") - swing_range * level
            col_name = f"fib_dist_{str(level).replace('.', '')}"
            fib_dist_cols.append(col_name)
            fib_exprs.append(
                ((pl.col("close") - fib_price) / safe_atr)
                .fill_nan(0.0)
                .alias(col_name)
            )

        df = df.with_columns(fib_exprs)

        # Nearest Fibonacci level (min absolute distance)
        abs_dists = [pl.col(c).abs() for c in fib_dist_cols]
        df = df.with_columns(
            pl.min_horizontal(*abs_dists).alias("fib_nearest_level")
        )

        # Cluster strength: how many Fib levels are within 0.5 ATR of close
        cluster_exprs = [
            pl.when(pl.col(c).abs() < 0.5).then(1).otherwise(0)
            for c in fib_dist_cols
        ]
        df = df.with_columns(
            pl.sum_horizontal(*cluster_exprs).alias("fib_cluster_strength")
        )

        # Cleanup
        df = df.drop(["_swing_high", "_swing_low"])

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

        # Advanced mean reversion
        df = ti.add_stochastic_rsi(df, rsi_period=rsi_period)
        df = ti.add_bollinger_squeeze(df, bb_period=bb_period)
        df = ti.add_rsi_divergence(df, rsi_period=rsi_period)

        # Volatility
        df = ti.add_atr(df, period=atr_period)
        df = ti.add_historical_volatility(df, period=hvol_period)

        # Volume (only if column exists and has non-null values)
        if include_volume and "volume" in df.columns:
            has_volume = df["volume"].null_count() < len(df) and df["volume"].sum() > 0
            if has_volume:
                df = ti.add_obv(df)
                df = ti.add_volume_sma_ratio(df)
                df = ti.add_vwap(df)

        # Price action
        df = ti.add_returns(df, periods=return_periods)
        df = ti.add_price_action(df)

        # Session features
        df = ti.add_session_features(df)

        # Candlestick patterns
        df = ti.add_candlestick_patterns(df)

        # Fibonacci levels
        df = ti.add_fibonacci_levels(df, atr_period=atr_period)

        return df
