"""
ML Ensemble Strategy — wraps existing PredictionService + SignalGenerator
as a BaseStrategy for use in the StrategyRouter.
"""

import polars as pl
from loguru import logger

from src.models.schemas import PredictionResult, SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal
from src.strategy.signal_generator import SignalGenerator


class MLStrategy(BaseStrategy):
    """
    Wraps the existing ML prediction + signal generation pipeline
    as a BaseStrategy implementation.

    In real-time mode, expects a PredictionResult in current_bar["prediction"].
    In backtest mode, generates signals from pre-computed prediction columns.
    """

    @property
    def name(self) -> str:
        return "ml_ensemble"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_up", "trending_down", "ranging"]

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        """
        Generate signal using ML prediction from current_bar.

        Expected current_bar keys:
        - prediction: PredictionResult (from PredictionService)
        - close: current price
        - atr_14: current ATR
        - rsi_14: current RSI (optional)
        - adx: current ADX (optional)
        - regime: current regime (optional)
        """
        prediction = current_bar.get("prediction")
        price = float(current_bar.get("close", 0))

        if prediction is None or price <= 0:
            return TradingSignal(
                epic=epic,
                direction=SignalDirection.HOLD,
                confidence=0.0,
                signal_class=SignalClass.HOLD,
                entry_price=price,
                technical_confirmation=False,
                strategy_name=self.name,
            )

        atr = float(current_bar.get("atr_14", price * 0.01))
        rsi = current_bar.get("rsi_14")
        adx = current_bar.get("adx")
        regime = current_bar.get("regime")

        if rsi is not None:
            rsi = float(rsi)
        if adx is not None:
            adx = float(adx)

        signal = SignalGenerator.generate_signal(
            prediction=prediction,
            epic=epic,
            current_price=price,
            atr=atr,
            rsi=rsi,
            regime=regime,
            config=config,
            adx=adx,
        )

        # Tag with strategy name
        signal.strategy_name = self.name
        return signal

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """
        Generate ML-based signals for backtesting.

        Expects ohlc_df to already contain prediction columns
        (signal_class, confidence) from a pre-run ML inference pass.
        """
        df = ohlc_df.clone()

        if "signal_class" not in df.columns or "confidence" not in df.columns:
            logger.warning(
                f"{epic}: ML backtest requires pre-computed signal_class " "and confidence columns"
            )
            df = df.with_columns(
                [
                    pl.lit(0).alias("signal_direction"),
                    pl.lit(0.0).alias("signal_confidence"),
                ]
            )
            return df

        # Map signal_class to direction
        df = df.with_columns(
            [
                pl.when(pl.col("signal_class") == SignalClass.BUY)
                .then(1)
                .when(pl.col("signal_class") == SignalClass.SELL)
                .then(-1)
                .otherwise(0)
                .alias("signal_direction"),
                pl.col("confidence").alias("signal_confidence"),
            ]
        )

        return df
