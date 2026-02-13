"""
VWAP Standard Deviation Reversion Strategy.

Mean reversion on VWAP SD bands in ranging markets.
Entry: close outside 2*SD bands. TP: VWAP center. SL: beyond 3*SD.
Filters: ADX < 25, RSI confirmation, volume < 2x average.
"""

import polars as pl
from loguru import logger

from src.features.technical import TechnicalIndicators
from src.features.vwap_bands import VWAPBands
from src.models.schemas import SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal


class VWAPReversionStrategy(BaseStrategy):
    """
    VWAP SD reversion strategy for ranging markets.

    Entry: close < VWAP - 2*SD (LONG) or close > VWAP + 2*SD (SHORT)
    TP: VWAP center (mean reversion target)
    SL: beyond 3*SD band
    Filters: ADX < 25, RSI < 30 (long) / > 70 (short), volume < 2x average
    """

    def __init__(
        self,
        entry_sd: float = 2.0,
        stop_sd: float = 3.0,
        max_adx: float = 25.0,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        max_volume_ratio: float = 2.0,
    ):
        self.entry_sd = entry_sd
        self.stop_sd = stop_sd
        self.max_adx = max_adx
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.max_volume_ratio = max_volume_ratio

    @property
    def name(self) -> str:
        return "vwap_reversion"

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
        """Generate mean-reversion signal from VWAP SD bands."""
        price = float(current_bar.get("close", 0))
        hold = TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=SignalClass.HOLD,
            entry_price=price,
            technical_confirmation=False,
        )

        if price <= 0:
            return hold

        vwap = current_bar.get("vwap_rolling")
        vwap_sd = current_bar.get("vwap_sd")
        z_score = current_bar.get("vwap_z_score")

        if vwap is None or vwap_sd is None or z_score is None:
            return hold

        vwap = float(vwap)
        vwap_sd = float(vwap_sd)
        z_score = float(z_score)

        if vwap_sd <= 0:
            return hold

        # ADX filter: only trade in non-trending conditions
        adx = current_bar.get("adx")
        if adx is not None and float(adx) > self.max_adx:
            return hold

        # Volume filter: avoid high-volume breakouts
        vol_ratio = current_bar.get("volume_sma_ratio")
        if vol_ratio is not None and float(vol_ratio) > self.max_volume_ratio:
            return hold

        # RSI confirmation
        rsi = current_bar.get("rsi_14")

        # Check entry conditions
        if z_score <= -self.entry_sd:
            # Below lower band: BUY (mean reversion up)
            if rsi is not None and float(rsi) > self.rsi_oversold:
                return hold  # RSI not oversold enough

            direction = SignalDirection.BUY
            signal_class = SignalClass.BUY
            suggested_stop = vwap - self.stop_sd * vwap_sd
            suggested_tp = vwap  # Target: VWAP center
            confidence = min(0.70, 0.50 + abs(z_score - self.entry_sd) * 0.05)

        elif z_score >= self.entry_sd:
            # Above upper band: SELL (mean reversion down)
            if rsi is not None and float(rsi) < self.rsi_overbought:
                return hold  # RSI not overbought enough

            direction = SignalDirection.SELL
            signal_class = SignalClass.SELL
            suggested_stop = vwap + self.stop_sd * vwap_sd
            suggested_tp = vwap
            confidence = min(0.70, 0.50 + abs(z_score - self.entry_sd) * 0.05)

        else:
            return hold

        logger.info(
            f"{epic}: VWAP reversion {direction.value} "
            f"z={z_score:.2f} confidence={confidence:.2f}"
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
            strategy_name=self.name,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """Generate VWAP reversion signals for backtesting."""
        df = ohlc_df.clone()

        # Ensure indicators
        if "vwap_z_score" not in df.columns:
            df = VWAPBands.add_vwap_bands(df)
        if "rsi_14" not in df.columns:
            df = TechnicalIndicators.add_rsi(df)
        if "adx" not in df.columns:
            df = TechnicalIndicators.add_adx(df)
        if "volume_sma_ratio" not in df.columns and "volume" in df.columns:
            has_volume = df["volume"].null_count() < len(df) and df["volume"].sum() > 0
            if has_volume:
                df = TechnicalIndicators.add_volume_sma_ratio(df)

        z = pl.col("vwap_z_score")

        # ADX filter
        adx_ok = pl.lit(True)
        if "adx" in df.columns:
            adx_ok = pl.col("adx") <= self.max_adx

        # Volume filter
        vol_ok = pl.lit(True)
        if "volume_sma_ratio" in df.columns:
            vol_ok = pl.col("volume_sma_ratio") <= self.max_volume_ratio

        # RSI confirmation
        rsi_buy_ok = pl.lit(True)
        rsi_sell_ok = pl.lit(True)
        if "rsi_14" in df.columns:
            rsi_buy_ok = pl.col("rsi_14") <= self.rsi_oversold
            rsi_sell_ok = pl.col("rsi_14") >= self.rsi_overbought

        # Signals
        df = df.with_columns([
            pl.when((z <= -self.entry_sd) & adx_ok & vol_ok & rsi_buy_ok)
            .then(1)
            .when((z >= self.entry_sd) & adx_ok & vol_ok & rsi_sell_ok)
            .then(-1)
            .otherwise(0)
            .alias("signal_direction"),

            pl.when(
                ((z <= -self.entry_sd) & adx_ok & vol_ok & rsi_buy_ok)
                | ((z >= self.entry_sd) & adx_ok & vol_ok & rsi_sell_ok)
            )
            .then(0.55)
            .otherwise(0.0)
            .alias("signal_confidence"),
        ])

        # SL/TP
        if "vwap_sd" in df.columns and "vwap_rolling" in df.columns:
            df = df.with_columns([
                pl.when(pl.col("signal_direction") == 1)
                .then(pl.col("vwap_rolling") - self.stop_sd * pl.col("vwap_sd"))
                .when(pl.col("signal_direction") == -1)
                .then(pl.col("vwap_rolling") + self.stop_sd * pl.col("vwap_sd"))
                .otherwise(None)
                .alias("signal_stop"),

                pl.when(pl.col("signal_direction").abs() == 1)
                .then(pl.col("vwap_rolling"))
                .otherwise(None)
                .alias("signal_tp"),
            ])

        return df
