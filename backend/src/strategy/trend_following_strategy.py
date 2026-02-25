"""
Trend-following strategy.
Entry on EMA crossover in direction of macro trend (SMA50).
ML model acts as confirmation filter (must agree with direction).
"""

import polars as pl
from loguru import logger

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend-following with ML confirmation.

    Entry rules:
    1. Macro trend: Price above SMA(50) = bullish, below = bearish
    2. EMA crossover: EMA(8) crosses EMA(21) in trend direction
    3. ADX confirmation: ADX > 20 (trend has strength)
    4. ML confirmation: Model predicts same direction (BUY or SELL, not HOLD)

    All 4 must agree for a signal.
    """

    @property
    def name(self) -> str:
        return "trend_following"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_up", "trending_down"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        """
        Generate trend-following signal from current bar data.

        Required current_bar keys:
        - close: current price
        - sma_50: 50-period SMA
        - ema_8, ema_21: fast/slow EMAs
        - ema_8_prev, ema_21_prev: previous bar EMAs (for crossover)
        - adx: ADX value
        - atr_14: ATR value
        - prediction: PredictionResult (from ML model)
        """
        price = current_bar.get("close", 0.0)

        sma_50 = current_bar.get("sma_50")
        ema_8 = current_bar.get("ema_8")
        ema_21 = current_bar.get("ema_21")
        ema_8_prev = current_bar.get("ema_8_prev")
        ema_21_prev = current_bar.get("ema_21_prev")
        adx = current_bar.get("adx")
        atr = current_bar.get("atr_14", 0.0)

        prediction: PredictionResult | None = current_bar.get("prediction")

        # Default HOLD
        hold = TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=SignalClass.HOLD,
            entry_price=price,
            strategy_name="trend_following",
        )

        # Need all data
        if any(v is None for v in [sma_50, ema_8, ema_21, ema_8_prev, ema_21_prev, adx]):
            return hold

        if atr <= 0:
            return hold

        # 1. Macro trend direction
        if price > sma_50:
            macro_direction = SignalDirection.BUY
        elif price < sma_50:
            macro_direction = SignalDirection.SELL
        else:
            return hold

        # 2. EMA crossover in trend direction
        ema_cross_up = ema_8_prev <= ema_21_prev and ema_8 > ema_21
        ema_cross_down = ema_8_prev >= ema_21_prev and ema_8 < ema_21

        if macro_direction == SignalDirection.BUY and not ema_cross_up:
            # Also accept already-crossed (ema_8 > ema_21) for continuation
            if ema_8 <= ema_21:
                return hold
        elif macro_direction == SignalDirection.SELL and not ema_cross_down:
            if ema_8 >= ema_21:
                return hold

        # 3. ADX confirmation (trend has strength)
        if adx < 20.0:
            return hold

        # 4. ML confirmation (must agree with direction)
        ml_confidence = 0.0
        if prediction is not None:
            ml_class = prediction.signal_class
            ml_confidence = prediction.confidence

            if macro_direction == SignalDirection.BUY and ml_class != SignalClass.BUY:
                return hold  # ML disagrees
            elif macro_direction == SignalDirection.SELL and ml_class != SignalClass.SELL:
                return hold  # ML disagrees
        else:
            return hold  # No ML prediction = no trade

        # All 4 agree — generate signal
        # Confidence = blend of ADX strength + ML confidence
        adx_factor = min(adx / 50.0, 1.0)  # 0-1 scale
        blended_confidence = 0.4 * adx_factor + 0.6 * ml_confidence

        logger.info(
            f"[{epic}] TREND signal: {macro_direction.value} "
            f"(ADX={adx:.1f}, ML_conf={ml_confidence:.2f}, "
            f"blended={blended_confidence:.2f})"
        )

        return TradingSignal(
            epic=epic,
            direction=macro_direction,
            confidence=blended_confidence,
            signal_class=(
                SignalClass.BUY
                if macro_direction == SignalDirection.BUY
                else SignalClass.SELL
            ),
            entry_price=price,
            strategy_name="trend_following",
            technical_confirmation=True,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """
        Generate trend-following signals for backtesting.

        Adds columns: signal_direction (1=BUY, -1=SELL, 0=HOLD),
        signal_confidence.

        Note: ML confirmation is not available in batch backtest mode,
        so this uses only technical conditions (SMA50 + EMA crossover + ADX).
        """
        df = ohlc_df.clone()

        # Ensure required columns exist
        required = ["close", "sma_50", "ema_8", "ema_21", "adx"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            logger.warning(
                f"{epic}: Trend backtest missing columns: {missing}"
            )
            return df.with_columns([
                pl.lit(0).alias("signal_direction"),
                pl.lit(0.0).alias("signal_confidence"),
            ])

        # Previous EMA values for crossover detection
        df = df.with_columns([
            pl.col("ema_8").shift(1).alias("_ema_8_prev"),
            pl.col("ema_21").shift(1).alias("_ema_21_prev"),
        ])

        # Macro trend
        bullish_trend = pl.col("close") > pl.col("sma_50")
        bearish_trend = pl.col("close") < pl.col("sma_50")

        # EMA crossover or continuation
        ema_bullish = pl.col("ema_8") > pl.col("ema_21")
        ema_bearish = pl.col("ema_8") < pl.col("ema_21")

        # ADX filter
        adx_ok = pl.col("adx") >= 20.0

        # ADX-based confidence
        adx_factor = (pl.col("adx") / 50.0).clip(0.0, 1.0)
        base_confidence = 0.4 * adx_factor + 0.6 * 0.60  # Use 0.60 as default ML proxy

        df = df.with_columns([
            pl.when(bullish_trend & ema_bullish & adx_ok)
            .then(1)
            .when(bearish_trend & ema_bearish & adx_ok)
            .then(-1)
            .otherwise(0)
            .alias("signal_direction"),

            pl.when((bullish_trend & ema_bullish & adx_ok) | (bearish_trend & ema_bearish & adx_ok))
            .then(base_confidence)
            .otherwise(0.0)
            .alias("signal_confidence"),
        ])

        # Cleanup temp columns
        df = df.drop(["_ema_8_prev", "_ema_21_prev"])

        return df
