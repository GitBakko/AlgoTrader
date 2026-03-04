"""
ScalpScoreStrategy — Multi-indicator scoring for 15-min scalping.

SCALPING-GURU architecture: raw score + binary gate filters.

Computes a composite score (0-100) from 6 technical indicators:
  EMA Trend (20), RSI (18), MACD (18), Volume (12), ADX (18), BB Squeeze (14)

Score >= threshold AND gate_filters_pass -> entry signal.

Gate filters (binary pass/fail, NOT multiplicative):
  - Session: kill zone or active session (off-session = hard block)
  - VWAP: directional gate (buy only above VWAP, sell only below)
  - HTF: additive bonus/malus (+5 aligned, -10 opposing)

ML model acts as a boost layer externally (not inside this strategy).
"""

import polars as pl
from loguru import logger

from src.models.schemas import SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal
from src.strategy.session_filter import SessionFilter

# Indicator weights (must sum to 100)
W_EMA = 20
W_RSI = 18
W_MACD = 18
W_VOLUME = 12
W_ADX = 18
W_BB = 14

# Score thresholds
DEFAULT_ENTRY_THRESHOLD = 55
DEFAULT_FULL_SIZE_THRESHOLD = 70


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
    # Micro-regime detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_micro_regime(current_bar: dict, recent_bars: pl.DataFrame) -> str:
        """
        Detect micro-regime from current indicators.

        Returns:
            "SQUEEZE" — BB inside Keltner (breakout building)
            "HIGH_VOL" — ATR > 2x rolling mean (volatile)
            "NORMAL" — default
        """
        bb_upper = float(current_bar.get("bb_upper", 0))
        bb_lower = float(current_bar.get("bb_lower", 0))
        kc_upper = float(current_bar.get("keltner_upper", 0))
        kc_lower = float(current_bar.get("keltner_lower", 0))

        # Squeeze: BB bands inside Keltner channels
        if bb_upper > 0 and kc_upper > 0:
            bb_width = bb_upper - bb_lower
            kc_width = kc_upper - kc_lower
            if kc_width > 0 and bb_width < kc_width:
                return "SQUEEZE"

        # High volatility: ATR spike above 2x rolling mean
        atr = float(current_bar.get("atr_14", 0))
        if atr > 0 and "atr_14" in recent_bars.columns and len(recent_bars) > 10:
            atr_mean = recent_bars.get_column("atr_14").mean()
            if atr_mean is not None and atr_mean > 0 and atr > 2.0 * atr_mean:
                return "HIGH_VOL"

        return "NORMAL"

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

        # Session awareness: block or penalise off-session trades
        utc_hour = int(current_bar.get("utc_hour", -1))
        session_mult = 1.0
        if utc_hour >= 0:
            session_mult = SessionFilter.get_session_multiplier(epic, utc_hour)
            if session_mult == 0.0:
                logger.debug(f"[{epic}] Session blocked (UTC hour={utc_hour})")
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

        # --- GURU GATE FILTERS (binary, not multiplicative) ---

        # VWAP directional gate: zero the opposing direction
        vwap = float(current_bar.get("vwap", 0))
        if vwap > 0:
            if price < vwap:
                buy_total = 0  # Cannot buy below VWAP
            elif price > vwap:
                sell_total = 0  # Cannot sell above VWAP

        # Session: no score penalty — only threshold adjustment
        # (off-session hard block already handled above)
        effective_threshold = self.entry_threshold
        if session_mult < 1.0:
            effective_threshold += 5  # Slightly higher bar outside kill zones

        # Micro-regime: additive adjustments
        micro_regime = self._detect_micro_regime(current_bar, recent_bars)
        if micro_regime == "SQUEEZE":
            buy_total += 5   # Breakout energy building
            sell_total += 5
        elif micro_regime == "HIGH_VOL":
            effective_threshold = max(effective_threshold, 65)

        # HTF confluence: additive bonus/malus (not multiplicative)
        htf_bias = current_bar.get("htf_bias")
        if htf_bias == "bearish":
            buy_total -= 10  # Fighting the trend
            sell_total += 5  # Aligned with trend
        elif htf_bias == "bullish":
            sell_total -= 10  # Fighting the trend
            buy_total += 5   # Aligned with trend

        # Determine direction: highest score wins
        if buy_total >= sell_total and buy_total >= effective_threshold:
            direction = SignalDirection.BUY
            score = buy_total
            signal_class = SignalClass.BUY
        elif sell_total > buy_total and sell_total >= effective_threshold:
            direction = SignalDirection.SELL
            score = sell_total
            signal_class = SignalClass.SELL
        else:
            # Show feature details for HOLD signals during testing
            vwap_tag = f" VWAP={vwap:.2f}" if vwap > 0 else ""
            regime_tag = f" regime={micro_regime}" if micro_regime != "NORMAL" else ""
            htf_tag = f" HTF={htf_bias}" if htf_bias else ""
            sess_tag = f" sess={session_mult:.1f}" if session_mult < 1.0 else ""
            logger.info(
                f"[{epic}] ScalpScore: BUY={buy_total:.0f} SELL={sell_total:.0f} "
                f"< thr={effective_threshold}{vwap_tag}{regime_tag}{htf_tag}{sess_tag}"
            )
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

        vwap_info = f" VWAP={vwap:.2f}" if vwap > 0 else ""
        regime_info = f" regime={micro_regime}" if micro_regime != "NORMAL" else ""
        htf_info = f" HTF={htf_bias}" if htf_bias else ""
        logger.info(
            f"[{epic}] ScalpScore: BUY={buy_total:.0f} SELL={sell_total:.0f} "
            f"-> {direction.value} (score={score:.0f}, conf={confidence:.2f})"
            f"{vwap_info}{regime_info}{htf_info}"
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
