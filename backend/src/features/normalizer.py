"""
Feature normalization module.
Rolling z-score, log transform, and outlier clipping.
All normalizations use only past data to prevent look-ahead bias.
"""

import polars as pl


class FeatureNormalizer:
    """
    Normalizes features using rolling statistics.
    All methods are stateless and prevent look-ahead bias by using
    only past data (rolling windows).
    """

    @staticmethod
    def rolling_zscore(
        df: pl.DataFrame,
        columns: list[str],
        window: int = 252,
        min_periods: int | None = None,
    ) -> pl.DataFrame:
        """
        Apply rolling z-score normalization.
        z = (x - rolling_mean) / rolling_std

        Args:
            df: Input DataFrame
            columns: Columns to normalize
            window: Rolling window size (default: 252 = ~1 year daily)
            min_periods: Minimum observations for calculation (default: window // 2)
        """
        if min_periods is None:
            min_periods = max(window // 2, 2)

        for col in columns:
            if col not in df.columns:
                continue

            norm_col = f"{col}_zscore"
            rolling_std = pl.col(col).rolling_std(window_size=window, min_periods=min_periods)
            # Replace zero std with NaN to avoid inf, then fill_nan handles both cases
            safe_std = pl.when(rolling_std.abs() < 1e-10).then(None).otherwise(rolling_std)
            df = df.with_columns(
                (
                    (pl.col(col) - pl.col(col).rolling_mean(window_size=window, min_periods=min_periods))
                    / safe_std
                )
                .fill_nan(0.0)
                .fill_null(0.0)
                .alias(norm_col)
            )

        return df

    @staticmethod
    def log_transform(
        df: pl.DataFrame,
        columns: list[str],
    ) -> pl.DataFrame:
        """
        Apply log1p transform for non-stationary features (volume, OBV, etc.).

        Args:
            df: Input DataFrame
            columns: Columns to transform
        """
        for col in columns:
            if col not in df.columns:
                continue

            log_col = f"{col}_log"
            df = df.with_columns(
                pl.col(col).abs().log1p().alias(log_col)
            )

        return df

    @staticmethod
    def clip_outliers(
        df: pl.DataFrame,
        columns: list[str],
        n_sigma: float = 5.0,
        window: int = 252,
    ) -> pl.DataFrame:
        """
        Clip outliers based on rolling z-score.
        Values beyond n_sigma standard deviations are clipped.

        Args:
            df: Input DataFrame
            columns: Columns to clip
            n_sigma: Clipping threshold in standard deviations
            window: Rolling window for mean/std calculation
        """
        for col in columns:
            if col not in df.columns:
                continue

            df = df.with_columns(
                [
                    pl.col(col).rolling_mean(window_size=window, min_periods=2).alias("_clip_mean"),
                    pl.col(col).rolling_std(window_size=window, min_periods=2).alias("_clip_std"),
                ]
            )

            df = df.with_columns(
                pl.col(col)
                .clip(
                    lower_bound=pl.col("_clip_mean") - n_sigma * pl.col("_clip_std"),
                    upper_bound=pl.col("_clip_mean") + n_sigma * pl.col("_clip_std"),
                )
                .alias(col)
            )

            df = df.drop(["_clip_mean", "_clip_std"])

        return df

    @staticmethod
    def clip_and_zscore(
        df: pl.DataFrame,
        columns: list[str],
        window: int = 252,
        min_periods: int | None = None,
        n_sigma: float = 5.0,
    ) -> pl.DataFrame:
        """
        Clip outliers and compute z-score in a single pass.
        Computes rolling mean/std once per column instead of twice.

        Args:
            df: Input DataFrame
            columns: Columns to process
            window: Rolling window size
            min_periods: Minimum observations (default: window // 2)
            n_sigma: Clipping threshold in standard deviations
        """
        if min_periods is None:
            min_periods = max(window // 2, 2)

        for col in columns:
            if col not in df.columns:
                continue

            # Compute rolling stats once
            rm = pl.col(col).rolling_mean(window_size=window, min_periods=min_periods)
            rs = pl.col(col).rolling_std(window_size=window, min_periods=min_periods)
            df = df.with_columns([rm.alias("_rm"), rs.alias("_rs")])

            # Clip outliers
            df = df.with_columns(
                pl.col(col)
                .clip(
                    lower_bound=pl.col("_rm") - n_sigma * pl.col("_rs"),
                    upper_bound=pl.col("_rm") + n_sigma * pl.col("_rs"),
                )
                .alias(col)
            )

            # Z-score using same rolling stats
            safe_std = pl.when(pl.col("_rs").abs() < 1e-10).then(None).otherwise(pl.col("_rs"))
            df = df.with_columns(
                ((pl.col(col) - pl.col("_rm")) / safe_std)
                .fill_nan(0.0)
                .fill_null(0.0)
                .alias(f"{col}_zscore")
            )

            df = df.drop(["_rm", "_rs"])

        return df

    @staticmethod
    def normalize_features(
        df: pl.DataFrame,
        feature_columns: list[str],
        window: int = 252,
        log_columns: list[str] | None = None,
        clip_sigma: float = 5.0,
    ) -> pl.DataFrame:
        """
        Apply full normalization pipeline to feature columns.

        Pipeline:
        1. Log transform for specified columns (volume-like features)
        2. Clip outliers + rolling z-score (fused single-pass)

        Args:
            df: Input DataFrame with features
            feature_columns: Columns to normalize
            window: Rolling window for normalization
            log_columns: Columns to log-transform first (e.g., volume, OBV)
            clip_sigma: Outlier clipping threshold

        Returns:
            DataFrame with normalized feature columns (suffixed with _zscore)
        """
        norm = FeatureNormalizer

        # Step 1: Log transform volume-like columns
        if log_columns:
            existing_log_cols = [c for c in log_columns if c in df.columns]
            if existing_log_cols:
                df = norm.log_transform(df, existing_log_cols)
                # Replace feature columns with log versions for normalization
                feature_columns = [
                    f"{c}_log" if c in existing_log_cols else c
                    for c in feature_columns
                ]

        # Step 2: Fused clip + z-score (single pass over rolling stats)
        process_cols = [c for c in feature_columns if c in df.columns]
        df = norm.clip_and_zscore(df, process_cols, window=window, n_sigma=clip_sigma)

        return df
