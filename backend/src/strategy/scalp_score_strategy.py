"""
ScalpScoreStrategy — Multi-indicator scoring for 15-min scalping.

Computes a composite score (0-100) from 6 technical indicators:
  EMA Trend (20), RSI (18), MACD (18), Volume (12), ADX (18), BB Squeeze (14)

Score >= 60 -> entry signal (BUY or SELL depending on indicator alignment).
ML model acts as a boost layer externally (not inside this strategy).
"""

import polars as pl
from loguru import logger

from src.models.schemas import SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal

# Indicator weights (must sum to 100)
W_EMA = 20
W_RSI = 18
W_MACD = 18
W_VOLUME = 12
W_ADX = 18
W_BB = 14

# Score thresholds
DEFAULT_ENTRY_THRESHOLD = 60
DEFAULT_FULL_SIZE_THRESHOLD = 75


class ScalpScoreStrategy(BaseStrategy):
    """Multi-indicator scoring strategy for scalp/intraday trading."""

    def __init__(
        self,
        entry_threshold: int = DEFAULT_ENTRY_THRESHOLD,
        full_size_threshold: int = DEFAULT_FULL_SIZE_THRESHOLD,
    ):
        self.entry_threshold = entry_threshold
        self.full_size_threshold = full_size_threshold

    @property
    def name(self) -> str:
        return "scalp_score"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_up", "trending_down", "ranging"]

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _score_ema(ema_9: float, ema_21: float, price: float) -> tuple[float, float]:
        """
        EMA cross + slope scoring.
        Returns (buy_score, sell_score) each in [0, W_EMA].
        """
        if ema_9 <= 0 or ema_21 <= 0:
            return 0.0, 0.0

        spread = (ema_9 - ema_21) / ema_21  # positive = bullish
        # Slope: how far price is from EMA9
        slope = (price - ema_9) / ema_9 if ema_9 > 0 else 0

        buy_score = 0.0
        sell_score = 0.0

        if spread > 0:
            # Bullish: EMA9 above EMA21
            buy_score = min(W_EMA, W_EMA * min(spread * 200, 1.0))  # 0.5% spread = full points
            if slope > 0:
                buy_score = min(W_EMA, buy_score * 1.2)  # Bonus for price above EMA9
        elif spread < 0:
            # Bearish: EMA9 below EMA21
            sell_score = min(W_EMA, W_EMA * min(abs(spread) * 200, 1.0))
            if slope < 0:
                sell_score = min(W_EMA, sell_score * 1.2)

        return buy_score, sell_score

    @staticmethod
    def _score_rsi(rsi: float) -> tuple[float, float]:
        """
        RSI scoring for buy/sell.
        BUY zone: RSI 25-45 (oversold bounce).
        SELL zone: RSI 55-75 (overbought rejection).
        """
        buy_score = 0.0
        sell_score = 0.0

        if 25 <= rsi <= 45:
            # Peak score at RSI ~35
            buy_score = W_RSI * max(0, 1.0 - abs(rsi - 35) / 15)
        elif 55 <= rsi <= 75:
            # Peak score at RSI ~65
            sell_score = W_RSI * max(0, 1.0 - abs(rsi - 65) / 15)

        return buy_score, sell_score

    @staticmethod
    def _score_macd(histogram: float, macd: float, signal: float) -> tuple[float, float]:
        """MACD histogram + crossover scoring."""
        buy_score = 0.0
        sell_score = 0.0

        if histogram > 0:
            buy_score += W_MACD * 0.6  # Histogram positive
            if macd > signal:
                buy_score += W_MACD * 0.4  # Crossover confirmed
        elif histogram < 0:
            sell_score += W_MACD * 0.6
            if macd < signal:
                sell_score += W_MACD * 0.4

        return min(W_MACD, buy_score), min(W_MACD, sell_score)

    @staticmethod
    def _score_volume(volume: float, volume_sma: float) -> float:
        """
        Volume confirmation (direction-agnostic).
        Returns score in [0, W_VOLUME].
        """
        if volume_sma <= 0:
            return 0.0
        ratio = volume / volume_sma
        if ratio >= 1.2:
            return min(W_VOLUME, W_VOLUME * min((ratio - 1.0) / 0.5, 1.0))
        return 0.0

    @staticmethod
    def _score_adx(adx: float) -> float:
        """
        ADX trend strength (direction-agnostic).
        Returns score in [0, W_ADX].
        """
        if adx >= 30:
            return W_ADX  # Strong trend
        elif adx >= 20:
            return W_ADX * (adx - 15) / 15  # Linear ramp from 15 to 30
        return 0.0

    @staticmethod
    def _score_bb_squeeze(
        bb_upper: float, bb_lower: float,
        keltner_upper: float, keltner_lower: float,
        price: float, bb_middle: float,
    ) -> tuple[float, float]:
        """
        Bollinger Band squeeze + breakout direction.
        Squeeze: BB inside Keltner (compression).
        Breakout up -> buy points; breakout down -> sell points.
        """
        buy_score = 0.0
        sell_score = 0.0

        if bb_upper <= 0 or keltner_upper <= 0:
            return 0.0, 0.0

        bb_width = bb_upper - bb_lower
        kc_width = keltner_upper - keltner_lower

        if kc_width <= 0:
            return 0.0, 0.0

        # Squeeze detection: BB narrower than Keltner
        is_squeeze = bb_width < kc_width
        squeeze_ratio = 1.0 - (bb_width / kc_width) if is_squeeze else 0.0

        if squeeze_ratio > 0:
            # Breakout direction from squeeze
            if price > bb_middle:
                buy_score = W_BB * min(squeeze_ratio * 2, 1.0)
            elif price < bb_middle:
                sell_score = W_BB * min(squeeze_ratio * 2, 1.0)
        elif price > bb_upper:
            # Breaking above upper BB (strong momentum)
            buy_score = W_BB * 0.5
        elif price < bb_lower:
            # Breaking below lower BB
            sell_score = W_BB * 0.5

        return buy_score, sell_score

    # ------------------------------------------------------------------
    # Main signal generation
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
        config: StrategyConfig,
    ) -> TradingSignal:
        price = float(current_bar.get("close", 0))
        atr = float(current_bar.get("atr_14", 0))

        if price <= 0 or atr <= 0:
            return self._hold(epic, price)

        # Extract indicators
        ema_9 = float(current_bar.get("ema_9", 0))
        ema_21 = float(current_bar.get("ema_21", 0))
        rsi = float(current_bar.get("rsi_14", 50))
        macd_hist = float(current_bar.get("macd_histogram", 0))
        macd_val = float(current_bar.get("macd", 0))
        macd_sig = float(current_bar.get("macd_signal", 0))
        adx = float(current_bar.get("adx_14", 0))
        volume = float(current_bar.get("volume", 0))
        volume_sma = float(current_bar.get("volume_sma_20", 0))
        bb_upper = float(current_bar.get("bb_upper", 0))
        bb_lower = float(current_bar.get("bb_lower", 0))
        bb_middle = float(current_bar.get("bb_middle", 0))
        kc_upper = float(current_bar.get("keltner_upper", 0))
        kc_lower = float(current_bar.get("keltner_lower", 0))

        # Compute component scores
        ema_buy, ema_sell = self._score_ema(ema_9, ema_21, price)
        rsi_buy, rsi_sell = self._score_rsi(rsi)
        macd_buy, macd_sell = self._score_macd(macd_hist, macd_val, macd_sig)
        vol_score = self._score_volume(volume, volume_sma)
        adx_score = self._score_adx(adx)
        bb_buy, bb_sell = self._score_bb_squeeze(
            bb_upper, bb_lower, kc_upper, kc_lower, price, bb_middle
        )

        buy_total = ema_buy + rsi_buy + macd_buy + vol_score + adx_score + bb_buy
        sell_total = ema_sell + rsi_sell + macd_sell + vol_score + adx_score + bb_sell

        # Determine direction: highest score wins
        if buy_total >= sell_total and buy_total >= self.entry_threshold:
            direction = SignalDirection.BUY
            score = buy_total
            signal_class = SignalClass.BUY
        elif sell_total > buy_total and sell_total >= self.entry_threshold:
            direction = SignalDirection.SELL
            score = sell_total
            signal_class = SignalClass.SELL
        else:
            return self._hold(epic, price)

        # Confidence: map score to [0.0, 1.0]
        confidence = min(1.0, score / 100.0)

        # SL / TP from config
        sl_mult = config.stop_multiplier  # 1.0 ATR for scalp
        rr = config.risk_reward_ratio     # 2.0 for scalp

        if direction == SignalDirection.BUY:
            stop = price - atr * sl_mult
            tp = price + atr * sl_mult * rr
        else:
            stop = price + atr * sl_mult
            tp = price - atr * sl_mult * rr

        logger.debug(
            f"[{epic}] ScalpScore: BUY={buy_total:.0f} SELL={sell_total:.0f} "
            f"-> {direction.value} (score={score:.0f}, conf={confidence:.2f})"
        )

        return TradingSignal(
            epic=epic,
            direction=direction,
            confidence=confidence,
            signal_class=signal_class,
            entry_price=price,
            suggested_stop=stop,
            suggested_tp=tp,
            technical_confirmation=True,
            strategy_name=self.name,
        )

    def generate_backtest_signals(
        self,
        ohlc_df: pl.DataFrame,
        epic: str,
        timeframe: str,
    ) -> pl.DataFrame:
        """Vectorized backtest signal generation."""
        directions = []
        confidences = []

        rows = ohlc_df.to_dicts()
        config = StrategyConfig(
            epic=epic,
            timeframe=timeframe,
            stop_multiplier=1.0,
            risk_reward_ratio=2.0,
        )
        dummy_recent = pl.DataFrame({"close": [0.0]})

        for row in rows:
            sig = self.generate_signal(epic, row, dummy_recent, config)
            dir_val = {"BUY": 1, "SELL": -1, "HOLD": 0}[sig.direction.value]
            directions.append(dir_val)
            confidences.append(sig.confidence)

        return ohlc_df.with_columns([
            pl.Series("signal_direction", directions),
            pl.Series("signal_confidence", confidences),
            pl.lit(None).alias("signal_stop"),
            pl.lit(None).alias("signal_tp"),
        ])

    @staticmethod
    def _hold(epic: str, price: float) -> TradingSignal:
        return TradingSignal(
            epic=epic,
            direction=SignalDirection.HOLD,
            confidence=0.0,
            signal_class=SignalClass.HOLD,
            entry_price=price,
            technical_confirmation=False,
        )
