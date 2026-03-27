"""
Target builder for ML models.
Generates ATR-relative classification labels from OHLC data.
"""

import polars as pl

from src.models.schemas import SignalClass


class TargetBuilder:
    """
    Builds classification targets based on ATR-relative future returns.

    3-class system (simplified from 5 to concentrate probability mass):
    - BUY (2):   future return > threshold * ATR
    - HOLD (1):  |future return| <= threshold * ATR
    - SELL (0):  future return < -threshold * ATR
    """

    def __init__(
        self,
        horizon_bars: int = 12,
        atr_column: str = "atr_14",
        threshold: float = 0.75,
    ):
        """
        Args:
            horizon_bars: Number of bars ahead for return calculation
            atr_column: Name of the ATR column in the DataFrame
            threshold: ATR multiplier for BUY/SELL threshold
        """
        self.horizon_bars = horizon_bars
        self.atr_column = atr_column
        self.threshold = threshold

    def build_targets(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Add target column to DataFrame based on future returns vs ATR.

        Args:
            df: DataFrame with 'close' and ATR column

        Returns:
            DataFrame with 'target' column added.
            Last `horizon_bars` rows will have null target.
        """
        if self.atr_column not in df.columns:
            raise ValueError(
                f"ATR column '{self.atr_column}' not found. "
                "Run TechnicalIndicators.add_atr() first."
            )

        # Future return: close[t+horizon] - close[t]
        df = df.with_columns(
            ((pl.col("close").shift(-self.horizon_bars) - pl.col("close"))).alias("_future_change")
        )

        # ATR-relative return
        df = df.with_columns(
            (pl.col("_future_change") / pl.col(self.atr_column)).alias("_atr_relative_return")
        )

        # Classify into 3 classes
        df = df.with_columns(
            pl.when(pl.col("_atr_relative_return").is_null())
            .then(None)
            .when(pl.col("_atr_relative_return") > self.threshold)
            .then(SignalClass.BUY)
            .when(pl.col("_atr_relative_return") < -self.threshold)
            .then(SignalClass.SELL)
            .otherwise(SignalClass.HOLD)
            .cast(pl.Int32)
            .alias("target")
        )

        df = df.drop(["_future_change", "_atr_relative_return"])

        return df

    def get_class_distribution(self, df: pl.DataFrame) -> dict[str, int]:
        """
        Get distribution of target classes.

        Args:
            df: DataFrame with 'target' column

        Returns:
            Dict mapping class name to count
        """
        if "target" not in df.columns:
            raise ValueError("No 'target' column. Run build_targets() first.")

        counts = (
            df.filter(pl.col("target").is_not_null())
            .group_by("target")
            .agg(pl.len().alias("count"))
            .sort("target")
        )

        result = {}
        for row in counts.iter_rows(named=True):
            class_val = row["target"]
            try:
                name = SignalClass(class_val).name
            except ValueError:
                name = f"UNKNOWN_{class_val}"
            result[name] = row["count"]

        return result
