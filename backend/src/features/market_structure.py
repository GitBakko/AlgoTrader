"""
Market structure detection: Break of Structure (BOS) and Change of Character (CHoCH).
Detects swing pivots, classifies them (HH/HL/LH/LL), and identifies
structural breaks for trend analysis.
"""

import numpy as np
import polars as pl


class MarketStructureDetector:
    """
    Detects market structure via swing pivots and structural breaks.

    Swing pivots: local high/low over lookback window.
    Classification: HH (higher high), HL (higher low), LH (lower high), LL (lower low).
    BOS: price breaks last pivot IN the direction of current trend.
    CHoCH: price breaks last pivot AGAINST the direction of current trend.

    Output features:
        - bos_signal: +1 (bullish BOS), -1 (bearish BOS), 0 (none)
        - choch_signal: +1 (bullish CHoCH), -1 (bearish CHoCH), 0 (none)
        - structure_trend: +1 (bullish), -1 (bearish), 0 (undefined)
    """

    def __init__(self, pivot_lookback: int = 5, min_swing_pct: float = 0.001):
        """
        Args:
            pivot_lookback: Bars to look on each side for pivot detection
            min_swing_pct: Minimum swing size as fraction of price (filters noise)
        """
        self.pivot_lookback = pivot_lookback
        self.min_swing_pct = min_swing_pct

    def add_all(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Add all market structure features to the DataFrame.

        Args:
            df: DataFrame with 'high', 'low', 'close' columns.

        Returns:
            DataFrame with bos_signal, choch_signal, structure_trend columns.
        """
        if len(df) < self.pivot_lookback * 3:
            # Not enough data for meaningful structure detection
            len(df)
            df = df.with_columns(
                [
                    pl.lit(0).alias("bos_signal"),
                    pl.lit(0).alias("choch_signal"),
                    pl.lit(0).alias("structure_trend"),
                ]
            )
            return df

        high = df["high"].to_numpy().astype(np.float64)
        low = df["low"].to_numpy().astype(np.float64)
        close = df["close"].to_numpy().astype(np.float64)

        bos, choch, trend = self._detect_structure(high, low, close)

        df = df.with_columns(
            [
                pl.Series("bos_signal", bos),
                pl.Series("choch_signal", choch),
                pl.Series("structure_trend", trend),
            ]
        )

        return df

    def _detect_structure(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Core structure detection algorithm in numpy.

        Returns:
            Tuple of (bos_signal, choch_signal, structure_trend) arrays.
        """
        n = len(high)
        lb = self.pivot_lookback

        # Output arrays
        bos = np.zeros(n, dtype=np.int32)
        choch = np.zeros(n, dtype=np.int32)
        trend = np.zeros(n, dtype=np.int32)

        # Find swing highs and lows
        swing_highs = self._find_swing_highs(high, lb)
        swing_lows = self._find_swing_lows(low, lb)

        # Track the last two swing highs and lows
        last_sh: float | None = None
        prev_sh: float | None = None
        last_sl: float | None = None
        prev_sl: float | None = None

        # Current structure trend: +1 bullish, -1 bearish, 0 undefined
        current_trend = 0

        for i in range(n):
            # Update swing pivots
            if swing_highs[i]:
                prev_sh = last_sh
                last_sh = high[i]

            if swing_lows[i]:
                prev_sl = last_sl
                last_sl = low[i]

            # Need at least two of each to classify
            if last_sh is None or last_sl is None:
                trend[i] = current_trend
                continue

            # Determine structure trend from pivot classification
            # Bullish: HH + HL pattern
            # Bearish: LH + LL pattern
            if prev_sh is not None and prev_sl is not None:
                is_hh = last_sh > prev_sh
                is_hl = last_sl > prev_sl
                is_lh = last_sh < prev_sh
                is_ll = last_sl < prev_sl

                if is_hh and is_hl:
                    new_trend = 1  # Bullish
                elif is_lh and is_ll:
                    new_trend = -1  # Bearish
                else:
                    new_trend = current_trend  # Mixed, keep previous

                # BOS: structure continues (price breaks in trend direction)
                if current_trend == 1 and last_sh is not None:
                    if close[i] > last_sh and is_hh:
                        bos[i] = 1

                if current_trend == -1 and last_sl is not None:
                    if close[i] < last_sl and is_ll:
                        bos[i] = -1

                # CHoCH: structure reverses
                if current_trend == 1 and last_sl is not None:
                    if close[i] < last_sl and is_ll:
                        choch[i] = -1  # Bearish CHoCH

                if current_trend == -1 and last_sh is not None:
                    if close[i] > last_sh and is_hh:
                        choch[i] = 1  # Bullish CHoCH

                # Update trend if CHoCH detected
                if choch[i] != 0:
                    current_trend = choch[i]
                elif new_trend != 0 and new_trend != current_trend:
                    current_trend = new_trend

            trend[i] = current_trend

        return bos, choch, trend

    def _find_swing_highs(self, high: np.ndarray, lookback: int) -> np.ndarray:
        """
        Find swing high points.
        A swing high at index i means high[i] is the max of
        high[i-lookback : i+lookback+1].
        """
        n = len(high)
        result = np.zeros(n, dtype=bool)
        min_size = high.mean() * self.min_swing_pct if high.mean() > 0 else 0
        lb2 = lookback * 2

        for i in range(lookback, n - lookback):
            window = high[i - lookback : i + lookback + 1]
            if high[i] == window.max():
                # Min of surrounding region (avoid np.concatenate per iteration)
                left = high[max(0, i - lb2) : i]
                right = high[i + 1 : min(n, i + lb2 + 1)]
                local_low = (
                    min(left.min(), right.min())
                    if len(left) > 0 and len(right) > 0
                    else (
                        left.min()
                        if len(left) > 0
                        else (right.min() if len(right) > 0 else high[i])
                    )
                )
                if high[i] - local_low >= min_size:
                    result[i] = True

        return result

    def _find_swing_lows(self, low: np.ndarray, lookback: int) -> np.ndarray:
        """
        Find swing low points.
        A swing low at index i means low[i] is the min of
        low[i-lookback : i+lookback+1].
        """
        n = len(low)
        result = np.zeros(n, dtype=bool)
        min_size = low.mean() * self.min_swing_pct if low.mean() > 0 else 0
        lb2 = lookback * 2

        for i in range(lookback, n - lookback):
            window = low[i - lookback : i + lookback + 1]
            if low[i] == window.min():
                # Max of surrounding region (avoid np.concatenate per iteration)
                left = low[max(0, i - lb2) : i]
                right = low[i + 1 : min(n, i + lb2 + 1)]
                local_high = (
                    max(left.max(), right.max())
                    if len(left) > 0 and len(right) > 0
                    else (
                        left.max() if len(left) > 0 else (right.max() if len(right) > 0 else low[i])
                    )
                )
                if local_high - low[i] >= min_size:
                    result[i] = True

        return result
