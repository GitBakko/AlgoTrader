"""
Volatility Squeeze Breakout Strategy.

Detects Bollinger Band inside Keltner Channel (true squeeze) and generates
signals when the squeeze releases with momentum confirmation.

Entry: squeeze_on → squeeze_off + MACD histogram direction + volume spike
SL: below/above the squeeze range | TP: 2x risk-reward
Applicable regimes: ranging (captures range→trend transition)
"""

import polars as pl
from loguru import logger

from src.features.keltner import KeltnerChannel
from src.features.technical import TechnicalIndicators
from src.models.schemas import SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal


class SqueezeBreakoutStrategy(BaseStrategy):
    """
    Volatility Squeeze Breakout Strategy.

    Squeeze = BB inside KC. Release = BB exits KC with momentum.
    Designed for ranging markets to capture breakout transitions.
    """

    def __init__(
        self,
        min_squeeze_bars: int = 6,
        volume_confirm: float = 1.3,
        momentum_lookback: int = 3,
    ):
        """
        Args:
            min_squeeze_bars: Minimum consecutive bars in squeeze to be valid
            volume_confirm: Volume must be >= this multiple of SMA to confirm
            momentum_lookback: Bars to check MACD momentum direction
        """
        self.min_squeeze_bars = min_squeeze_bars
        self.volume_confirm = volume_confirm
        self.momentum_lookback = momentum_lookback

    @property
    def name(self) -> str:
        return "squeeze_breakout"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["ranging"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        """
        Generate signal from current bar data.

        Requires columns: squeeze_off, squeeze_on, macd_histogram,
        volume_sma_ratio, atr_14, close, high, low.
        """
        price = float(current_bar.get("close", 0))
        atr = float(current_bar.get("atr_14", 0))

        hold = TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=SignalClass.HOLD,
            entry_price=price,
            technical_confirmation=False,
        )

        if price <= 0 or atr <= 0:
            return hold

        squeeze_off = current_bar.get("squeeze_off", 0)
        if squeeze_off != 1:
            return hold

        # Check squeeze duration from recent_bars
        if not self._check_squeeze_duration(recent_bars):
            logger.debug(f"{epic}: Squeeze release but duration < {self.min_squeeze_bars}")
            return hold

        # MACD momentum direction at release
        macd_hist = float(current_bar.get("macd_histogram", 0))
        if macd_hist == 0:
            return hold

        # Volume confirmation
        vol_ratio = float(current_bar.get("volume_sma_ratio", 0))
        has_volume = vol_ratio >= self.volume_confirm if vol_ratio > 0 else True

        if not has_volume:
            logger.debug(f"{epic}: Squeeze release but volume ratio {vol_ratio:.2f} < {self.volume_confirm}")
            return hold

        # MACD momentum trend (check last N bars trending same direction)
        momentum_confirmed = self._check_momentum_trend(recent_bars, macd_hist > 0)

        if not momentum_confirmed:
            logger.debug(f"{epic}: Squeeze release but momentum not confirmed")
            return hold

        # Determine direction from MACD momentum
        if macd_hist > 0:
            direction = SignalDirection.BUY
            signal_class = SignalClass.BUY
            # SL below squeeze low
            squeeze_low = self._get_squeeze_low(recent_bars)
            suggested_stop = squeeze_low - 0.5 * atr if squeeze_low else price - 2.0 * atr
            risk = price - suggested_stop
            suggested_tp = price + risk * config.risk_reward_ratio
        else:
            direction = SignalDirection.SELL
            signal_class = SignalClass.SELL
            # SL above squeeze high
            squeeze_high = self._get_squeeze_high(recent_bars)
            suggested_stop = squeeze_high + 0.5 * atr if squeeze_high else price + 2.0 * atr
            risk = suggested_stop - price
            suggested_tp = price - risk * config.risk_reward_ratio

        # Confidence based on squeeze duration and volume
        confidence = min(0.75, 0.55 + (vol_ratio - 1.0) * 0.1) if vol_ratio > 0 else 0.55

        logger.info(
            f"{epic}: Squeeze breakout {direction.value} "
            f"confidence={confidence:.2f} vol_ratio={vol_ratio:.2f}"
        )

        return TradingSignal(
            epic=epic,
            direction=direction,
            confidence=confidence,
            signal_class=signal_class,
            entry_price=price,
            suggested_stop=suggested_stop,
            suggested_tp=suggested_tp,
            technical_confirmation=True,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """
        Generate squeeze breakout signals for backtesting.

        Adds columns: signal_direction (1=BUY, -1=SELL, 0=HOLD),
        signal_confidence, signal_stop, signal_tp
        """
        ti = TechnicalIndicators
        df = ohlc_df.clone()

        # Ensure required indicators exist
        if "macd_histogram" not in df.columns:
            df = ti.add_macd(df)
        if "bb_upper" not in df.columns:
            df = ti.add_bollinger_bands(df)
        if "atr_14" not in df.columns:
            df = ti.add_atr(df, period=14)
        if "volume_sma_ratio" not in df.columns and "volume" in df.columns:
            has_volume = df["volume"].null_count() < len(df) and df["volume"].sum() > 0
            if has_volume:
                df = ti.add_volume_sma_ratio(df)

        # Add Keltner + true squeeze
        if "squeeze_on" not in df.columns:
            df = KeltnerChannel.add_true_squeeze(df)

        # Compute squeeze duration
        squeeze_vals = df["squeeze_on"].to_numpy()
        import numpy as np
        duration = np.zeros(len(squeeze_vals), dtype=np.int32)
        count = 0
        for i in range(len(squeeze_vals)):
            if squeeze_vals[i] == 1:
                count += 1
            else:
                count = 0
            duration[i] = count

        df = df.with_columns(pl.Series("_sq_duration", duration))

        # Previous squeeze duration at release point
        df = df.with_columns(
            pl.col("_sq_duration").shift(1).alias("_prev_sq_duration")
        )

        # Signal generation vectorized
        # Valid squeeze release: squeeze_off == 1 AND prev duration >= min_squeeze_bars
        valid_release = (
            (pl.col("squeeze_off") == 1)
            & (pl.col("_prev_sq_duration") >= self.min_squeeze_bars)
        )

        # Volume confirmation
        if "volume_sma_ratio" in df.columns:
            vol_ok = pl.col("volume_sma_ratio") >= self.volume_confirm
        else:
            vol_ok = pl.lit(True)

        # Direction from MACD histogram
        macd_positive = pl.col("macd_histogram") > 0
        macd_negative = pl.col("macd_histogram") < 0

        # Generate signals
        df = df.with_columns([
            pl.when(valid_release & vol_ok & macd_positive)
            .then(1)
            .when(valid_release & vol_ok & macd_negative)
            .then(-1)
            .otherwise(0)
            .alias("signal_direction"),

            pl.when(valid_release & vol_ok & (macd_positive | macd_negative))
            .then(0.60)
            .otherwise(0.0)
            .alias("signal_confidence"),
        ])

        # SL/TP calculations
        atr_col = "atr_14"
        df = df.with_columns([
            # BUY: stop = low of squeeze range - 0.5 ATR
            pl.when(pl.col("signal_direction") == 1)
            .then(
                pl.col("low").rolling_min(window_size=self.min_squeeze_bars)
                - 0.5 * pl.col(atr_col)
            )
            # SELL: stop = high of squeeze range + 0.5 ATR
            .when(pl.col("signal_direction") == -1)
            .then(
                pl.col("high").rolling_max(window_size=self.min_squeeze_bars)
                + 0.5 * pl.col(atr_col)
            )
            .otherwise(None)
            .alias("signal_stop"),

            # TP = 2x risk from stop
            pl.when(pl.col("signal_direction") == 1)
            .then(
                pl.col("close") + 2.0 * (
                    pl.col("close") - (
                        pl.col("low").rolling_min(window_size=self.min_squeeze_bars)
                        - 0.5 * pl.col(atr_col)
                    )
                )
            )
            .when(pl.col("signal_direction") == -1)
            .then(
                pl.col("close") - 2.0 * (
                    (
                        pl.col("high").rolling_max(window_size=self.min_squeeze_bars)
                        + 0.5 * pl.col(atr_col)
                    ) - pl.col("close")
                )
            )
            .otherwise(None)
            .alias("signal_tp"),
        ])

        # Cleanup temp columns
        df = df.drop(["_sq_duration", "_prev_sq_duration"])

        return df

    def _check_squeeze_duration(self, recent_bars: pl.DataFrame) -> bool:
        """Check if squeeze lasted at least min_squeeze_bars before release."""
        if "squeeze_on" not in recent_bars.columns:
            return False

        vals = recent_bars["squeeze_on"].to_list()
        if len(vals) < self.min_squeeze_bars + 1:
            return False

        # Count consecutive 1s before the last bar (which should be release)
        count = 0
        for v in reversed(vals[:-1]):
            if v == 1:
                count += 1
            else:
                break

        return count >= self.min_squeeze_bars

    def _check_momentum_trend(self, recent_bars: pl.DataFrame, is_bullish: bool) -> bool:
        """Check if MACD histogram has been trending in the right direction."""
        if "macd_histogram" not in recent_bars.columns:
            return True  # Skip check if no data

        vals = recent_bars["macd_histogram"].tail(self.momentum_lookback).to_list()
        if len(vals) < 2:
            return True

        # Check if last values are increasingly positive (bull) or negative (bear)
        if is_bullish:
            return vals[-1] > vals[-2] if len(vals) >= 2 else True
        else:
            return vals[-1] < vals[-2] if len(vals) >= 2 else True

    def _get_squeeze_low(self, recent_bars: pl.DataFrame) -> float | None:
        """Get the lowest low during the squeeze period."""
        if "squeeze_on" not in recent_bars.columns or "low" not in recent_bars.columns:
            return None

        squeeze_mask = recent_bars["squeeze_on"] == 1
        squeeze_bars = recent_bars.filter(squeeze_mask)
        if squeeze_bars.is_empty():
            return None

        return float(squeeze_bars["low"].min())

    def _get_squeeze_high(self, recent_bars: pl.DataFrame) -> float | None:
        """Get the highest high during the squeeze period."""
        if "squeeze_on" not in recent_bars.columns or "high" not in recent_bars.columns:
            return None

        squeeze_mask = recent_bars["squeeze_on"] == 1
        squeeze_bars = recent_bars.filter(squeeze_mask)
        if squeeze_bars.is_empty():
            return None

        return float(squeeze_bars["high"].max())
