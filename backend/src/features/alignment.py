"""
Multi-timeframe feature alignment module.
Aligns features from different timeframes onto a single base timeframe.
"""

import polars as pl

# Bar duration in seconds, used to convert an OPEN-stamped HTF bar to its CLOSE
# time before the asof join (see align() look-ahead fix).
_TF_SECONDS = {
    "1min": 60,
    "5min": 300,
    "15min": 900,
    "30min": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


def _timeframe_seconds(tf: str) -> int:
    """Bar duration in seconds for a timeframe label, or 0 if unknown."""
    return _TF_SECONDS.get(tf.strip().lower(), 0)


class TimeframeAligner:
    """
    Aligns features from multiple timeframes onto a base timeframe.

    Strategy: higher-timeframe features are forward-filled to the base timeframe,
    meaning a 4h value remains valid until the next 4h bar completes.

    Look-ahead safety: OHLC ``timestamp`` is the bar's OPEN time, so a bar
    open-stamped at T only CLOSES at T + bar_duration and its close/indicator
    values encode prices up to bar_duration in the FUTURE relative to T. A naive
    asof-backward on the raw open-timestamp would therefore attach a still-forming
    HTF bar (with future-laden values) to base bars inside it — a look-ahead leak.
    align() converts HTF timestamps to CLOSE time before the asof join so each base
    bar only ever sees HTF bars that are fully closed at/<= the base bar.
    """

    @staticmethod
    def align(
        base_df: pl.DataFrame,
        higher_tf_dfs: dict[str, pl.DataFrame],
        base_timeframe: str,
        timestamp_col: str = "timestamp",
    ) -> pl.DataFrame:
        """
        Align higher-timeframe features onto the base timeframe.

        Args:
            base_df: DataFrame with base timeframe data (e.g., 1h bars)
            higher_tf_dfs: Dict mapping timeframe -> DataFrame with features
                          e.g., {"4h": df_4h, "1d": df_1d}
            base_timeframe: Name of the base timeframe (for column prefixing)
            timestamp_col: Name of the timestamp column

        Returns:
            Base DataFrame with additional columns from higher timeframes,
            prefixed with the timeframe name (e.g., "4h_ema_50").
        """
        result = base_df.clone()

        for tf_name, tf_df in higher_tf_dfs.items():
            if tf_df.is_empty():
                continue

            # Get feature columns (everything except OHLCV and metadata)
            exclude_cols = {
                timestamp_col,
                "open",
                "high",
                "low",
                "close",
                "volume",
                "epic",
                "timeframe",
                "source",
            }
            feature_cols = [c for c in tf_df.columns if c not in exclude_cols]

            if not feature_cols:
                continue

            # Select only timestamp + feature columns from higher TF
            tf_features = tf_df.select([timestamp_col] + feature_cols)

            # Rename feature columns with timeframe prefix
            rename_map = {col: f"{tf_name}_{col}" for col in feature_cols}
            tf_features = tf_features.rename(rename_map)

            # LOOK-AHEAD FIX: timestamps are bar OPEN times. A bar open-stamped at
            # T closes at T + dur and its values encode the future up to T+dur.
            # Shift HTF timestamps to CLOSE time so asof-backward attaches only HTF
            # bars fully closed at/<= the base bar (no future leak). Without this,
            # 4h_/1d_ features leaked ~4h/~1d of future into every base bar,
            # inflating training metrics and breaking the model live (train/serve
            # skew, since live has no future HTF data at decision time).
            dur_s = _timeframe_seconds(tf_name)
            if dur_s:
                tf_features = tf_features.with_columns(
                    (pl.col(timestamp_col) + pl.duration(seconds=dur_s)).alias(timestamp_col)
                )

            # Join using asof join (forward-fill: use latest CLOSED higher-TF bar)
            result = result.join_asof(
                tf_features.sort(timestamp_col),
                on=timestamp_col,
                strategy="backward",
            )

        return result

    @staticmethod
    def get_required_lookback(
        base_timeframe_minutes: int,
        higher_timeframe_minutes: int,
        indicator_lookback_bars: int,
    ) -> int:
        """
        Calculate how many base-timeframe bars we need to load to have
        enough data for higher-timeframe indicator calculation.

        Args:
            base_timeframe_minutes: Minutes per bar of base timeframe
            higher_timeframe_minutes: Minutes per bar of higher timeframe
            indicator_lookback_bars: How many bars the indicator needs

        Returns:
            Number of base-timeframe bars needed
        """
        ratio = higher_timeframe_minutes / base_timeframe_minutes
        return int(indicator_lookback_bars * ratio) + 1
