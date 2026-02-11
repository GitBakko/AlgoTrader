"""
Multi-timeframe feature alignment module.
Aligns features from different timeframes onto a single base timeframe.
"""

import polars as pl


class TimeframeAligner:
    """
    Aligns features from multiple timeframes onto a base timeframe.

    Strategy: higher-timeframe features are forward-filled to the base timeframe,
    meaning a 4h value remains valid until the next 4h bar completes.
    This prevents look-ahead bias.
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
                timestamp_col, "open", "high", "low", "close", "volume",
                "epic", "timeframe", "source",
            }
            feature_cols = [c for c in tf_df.columns if c not in exclude_cols]

            if not feature_cols:
                continue

            # Select only timestamp + feature columns from higher TF
            tf_features = tf_df.select([timestamp_col] + feature_cols)

            # Rename feature columns with timeframe prefix
            rename_map = {col: f"{tf_name}_{col}" for col in feature_cols}
            tf_features = tf_features.rename(rename_map)

            # Join using asof join (forward-fill: use latest available higher-TF value)
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
