"""
ScalpScoreStrategy — Confluence voting model for 15-min scalping.

SCALPING-GURU architecture (Section 3.1):
  "Confluence Check (minimo N segnali concordanti)"

Instead of additive scoring with a threshold, each indicator group
votes BUY/SELL/NEUTRAL independently. A trade fires when enough
indicator groups agree on the same direction.

7 indicator groups (each votes independently):
  1. EMA Trend  — EMA(9) vs EMA(21) cross direction
  2. RSI        — Oversold (<45) = BUY, Overbought (>55) = SELL
  3. MACD       — Histogram + crossover direction
  4. Volume     — Confirmation boost (volume > 1.2x SMA)
  5. ADX        — Trend strength confirmation (ADX > 20)
  6. BB/Keltner — Squeeze breakout direction
  7. Sentiment  — SIL composite score (Fear&Greed, FRED, Alpha Vantage, COT, Social)

Gate filters (binary pass/fail):
  - Session: kill zone or active session (off-session = hard block)
  - VWAP: directional gate (buy only above VWAP, sell only below)
  - HTF: adds/removes 1 vote for alignment/opposition

Entry rule: confluence_count >= MIN_CONFLUENCE (default 3/7)
"""

import polars as pl
from loguru import logger

from src.models.schemas import SignalClass
from src.strategy.base_strategy import BaseStrategy
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal
from src.strategy.session_filter import SessionFilter
from src.utils.config import get_settings

# Minimum concordant indicator votes to trigger a signal
DEFAULT_MIN_CONFLUENCE = 3
# During kill zones (high-probability windows), lower the bar
KILLZONE_MIN_CONFLUENCE = 3
# Outside kill zones, require stronger agreement
OFF_KILLZONE_MIN_CONFLUENCE = 4


class ScalpScoreStrategy(BaseStrategy):
    """Confluence voting strategy for scalp/intraday trading."""

    def __init__(
        self,
        min_confluence: int = DEFAULT_MIN_CONFLUENCE,
    ):
        self.min_confluence = min_confluence

    @property
    def name(self) -> str:
        return "scalp_score"

    @property
    def applicable_regimes(self) -> list[str]:
        return ["trending_up", "trending_down", "ranging"]

    # ------------------------------------------------------------------
    # Indicator vote functions — each returns +1 (BUY), -1 (SELL), 0
    # ------------------------------------------------------------------

    @staticmethod
    def _vote_ema(ema_9: float, ema_21: float) -> tuple[int, dict]:
        """EMA cross: bullish cross = BUY, bearish cross = SELL."""
        details = {"ema_9": ema_9, "ema_21": ema_21}
        if ema_9 <= 0 or ema_21 <= 0:
            return 0, details
        spread = (ema_9 - ema_21) / ema_21
        if spread > 0.001:   # >0.1% spread = bullish
            return 1, details
        elif spread < -0.001:
            return -1, details
        return 0, details

    @staticmethod
    def _vote_rsi(rsi: float) -> tuple[int, dict]:
        """RSI: oversold zone = BUY potential, overbought = SELL."""
        details = {"rsi_14": rsi}
        if rsi < 45:
            return 1, details
        elif rsi > 55:
            return -1, details
        return 0, details

    @staticmethod
    def _vote_macd(histogram: float, macd: float, signal: float) -> tuple[int, dict]:
        """MACD: histogram direction + crossover."""
        details = {"histogram": histogram, "macd": macd, "signal": signal}
        if histogram > 0 and macd > signal:
            return 1, details
        elif histogram < 0 and macd < signal:
            return -1, details
        # Histogram positive but no cross (or vice versa) = neutral
        if histogram > 0:
            return 1, details
        elif histogram < 0:
            return -1, details
        return 0, details

    @staticmethod
    def _vote_volume(volume: float, volume_sma: float) -> tuple[int, dict]:
        """Volume confirmation: strong volume = confirms current move."""
        details = {"volume": volume, "volume_sma_20": volume_sma}
        if volume_sma <= 0:
            return 0, details
        if volume / volume_sma >= 1.2:
            return 1, details
        return 0, details

    @staticmethod
    def _vote_adx(adx: float) -> tuple[int, dict]:
        """ADX trend strength: >20 = trend exists, confirming vote."""
        details = {"adx_14": adx}
        if adx >= 20:
            return 1, details
        return 0, details

    @staticmethod
    def _vote_bb_squeeze(
        bb_upper: float, bb_lower: float,
        keltner_upper: float, keltner_lower: float,
        price: float, bb_middle: float,
    ) -> tuple[int, dict]:
        """BB squeeze: breakout direction from compression."""
        details = {
            "bb_upper": bb_upper, "bb_lower": bb_lower,
            "kc_upper": keltner_upper, "kc_lower": keltner_lower,
            "price": price, "bb_mid": bb_middle,
        }
        if bb_upper <= 0 or keltner_upper <= 0:
            return 0, details

        bb_width = bb_upper - bb_lower
        kc_width = keltner_upper - keltner_lower
        if kc_width <= 0:
            return 0, details

        # Squeeze: BB inside Keltner
        if bb_width < kc_width:
            if price > bb_middle:
                return 1, details
            elif price < bb_middle:
                return -1, details
        # Not in squeeze: check band touches
        elif price > bb_upper:
            return 1, details
        elif price < bb_lower:
            return -1, details

        return 0, details

    @staticmethod
    def _vote_sentiment(
        composite_score: float,
        bullish_threshold: float = 0.6,
        bearish_threshold: float = 0.35,
    ) -> tuple[int, dict]:
        """Sentiment vote based on SIL composite score.

        Thresholds:
        - composite > 0.6 → BULLISH (+1)
        - composite < 0.35 → BEARISH (-1)
        - otherwise → NEUTRAL (0)
        - composite == 0.0 → NEUTRAL (no SIL data, don't influence)
        """
        details = {"composite": composite_score}
        if composite_score <= 0.0:
            return 0, details
        if composite_score > bullish_threshold:
            return 1, details
        elif composite_score < bearish_threshold:
            return -1, details
        return 0, details

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

        # Session awareness: block off-session trades
        utc_hour = int(current_bar.get("utc_hour", -1))
        session_mult = 1.0
        if utc_hour >= 0:
            session_mult = SessionFilter.get_session_multiplier(epic, utc_hour)
            if session_mult == 0.0:
                logger.debug(f"[{epic}] Session blocked (UTC hour={utc_hour})")
                return self._hold(epic, price)

        # Dead market gate: skip when BOTH ADX low AND BB width compressed
        _dm_settings = get_settings()
        adx_val = float(current_bar.get("adx_14", 0))
        bb_upper = float(current_bar.get("bb_upper", 0))
        bb_lower = float(current_bar.get("bb_lower", 0))
        bb_mid = float(current_bar.get("bb_middle", 0))
        if (adx_val > 0 and bb_mid > 0
                and adx_val < _dm_settings.scalp_dead_market_adx):
            # Compute BB width percentile from recent_bars
            bb_width_now = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0
            bb_pctile = 50.0  # default: assume mid-range
            if ("bb_upper" in recent_bars.columns
                    and "bb_lower" in recent_bars.columns
                    and "bb_middle" in recent_bars.columns
                    and len(recent_bars) > 10):
                widths = (
                    (recent_bars["bb_upper"] - recent_bars["bb_lower"])
                    / recent_bars["bb_middle"]
                ).drop_nulls().to_list()
                if widths:
                    count_below = sum(1 for w in widths if w <= bb_width_now)
                    bb_pctile = count_below / len(widths) * 100
            if bb_pctile < _dm_settings.scalp_dead_market_bb_pctile:
                logger.debug(
                    f"[{epic}] Dead market gate: ADX={adx_val:.1f} "
                    f"BB_pctile={bb_pctile:.0f}%"
                )
                return self._hold(epic, price)

        # --- Collect votes from each indicator group ---
        ema_vote, ema_details = self._vote_ema(
            float(current_bar.get("ema_9", 0)),
            float(current_bar.get("ema_21", 0)),
        )
        rsi_vote, rsi_details = self._vote_rsi(float(current_bar.get("rsi_14", 50)))
        macd_vote, macd_details = self._vote_macd(
            float(current_bar.get("macd_histogram", 0)),
            float(current_bar.get("macd", 0)),
            float(current_bar.get("macd_signal", 0)),
        )

        volume = float(current_bar.get("volume", 0))
        volume_sma = float(current_bar.get("volume_sma_20", 0))
        vol_vote, vol_details = self._vote_volume(volume, volume_sma)

        adx_vote, adx_details = self._vote_adx(float(current_bar.get("adx_14", 0)))

        bb_vote, bb_details = self._vote_bb_squeeze(
            float(current_bar.get("bb_upper", 0)),
            float(current_bar.get("bb_lower", 0)),
            float(current_bar.get("keltner_upper", 0)),
            float(current_bar.get("keltner_lower", 0)),
            price,
            float(current_bar.get("bb_middle", 0)),
        )

        # 7th vote: Sentiment (SIL composite score)
        sil_composite = float(current_bar.get("sil_composite_score", 0.0))
        sentiment_vote, sentiment_details = self._vote_sentiment(sil_composite)

        # Build votes data for audit trail
        votes_data = {
            "ema": {"value": ema_vote, **ema_details},
            "rsi": {"value": rsi_vote, **rsi_details},
            "macd": {"value": macd_vote, **macd_details},
            "volume": {"value": vol_vote, **vol_details},
            "adx": {"value": adx_vote, **adx_details},
            "bb_keltner": {"value": bb_vote, **bb_details},
            "sentiment": {"value": sentiment_vote, **sentiment_details},
        }

        # Volume and ADX are direction-agnostic confirmations.
        # They amplify the majority direction.
        directional_votes = [ema_vote, rsi_vote, macd_vote, bb_vote, sentiment_vote]
        buy_dir = sum(1 for v in directional_votes if v > 0)
        sell_dir = sum(1 for v in directional_votes if v < 0)

        # Determine majority direction.
        # FIX: Require minimum 3 directional votes before adding confirmations.
        # This prevents VOL+ADX from inflating weak 2/5 signals into tradeable ones.
        MIN_DIRECTIONAL_FOR_CONFIRMATION = 3

        if buy_dir > sell_dir:
            majority = 1  # BUY majority
            buy_count = buy_dir
            sell_count = sell_dir
            # Confirmation votes only add if directional consensus is strong enough
            if buy_dir >= MIN_DIRECTIONAL_FOR_CONFIRMATION:
                if vol_vote > 0:
                    buy_count += 1
                if adx_vote > 0:
                    buy_count += 1
        elif sell_dir > buy_dir:
            majority = -1  # SELL majority
            buy_count = buy_dir
            sell_count = sell_dir
            if sell_dir >= MIN_DIRECTIONAL_FOR_CONFIRMATION:
                if vol_vote > 0:
                    sell_count += 1
                if adx_vote > 0:
                    sell_count += 1
        else:
            # Tied or all neutral — no trade
            majority = 0
            buy_count = buy_dir
            sell_count = sell_dir

        # --- GURU GATE FILTERS ---

        # VWAP directional gate
        vwap = float(current_bar.get("vwap", 0))
        if vwap > 0:
            if price < vwap:
                buy_count = 0   # Cannot buy below VWAP
            elif price > vwap:
                sell_count = 0  # Cannot sell above VWAP

        # HTF confluence: adds/removes 1 vote
        htf_bias = current_bar.get("htf_bias")
        if htf_bias == "bullish":
            buy_count += 1
            sell_count = max(0, sell_count - 1)
        elif htf_bias == "bearish":
            sell_count += 1
            buy_count = max(0, buy_count - 1)

        # Effective confluence requirement (3-tier: kill zone / chop zone / default)
        _strat_settings = get_settings()
        if session_mult >= 1.0:
            # Inside kill zone — lowest bar
            effective_min = KILLZONE_MIN_CONFLUENCE
        elif (_strat_settings.scalp_chop_zone_start
              <= utc_hour < _strat_settings.scalp_chop_zone_end):
            # Chop zone (e.g. 16-20 UTC) — highest bar
            effective_min = _strat_settings.scalp_chop_zone_min_confluence
        else:
            # Outside kill zone — moderate bar
            effective_min = OFF_KILLZONE_MIN_CONFLUENCE

        # Vote summary for logging
        votes_str = (
            f"EMA={ema_vote:+d} RSI={rsi_vote:+d} MACD={macd_vote:+d} "
            f"BB={bb_vote:+d} VOL={vol_vote:+d} ADX={adx_vote:+d} "
            f"SENT={sentiment_vote:+d}"
        )

        # Determine signal
        if buy_count >= effective_min and buy_count > sell_count:
            direction = SignalDirection.BUY
            confluence = buy_count
            signal_class = SignalClass.BUY
        elif sell_count >= effective_min and sell_count > buy_count:
            direction = SignalDirection.SELL
            confluence = sell_count
            signal_class = SignalClass.SELL
        else:
            vwap_tag = f" VWAP={vwap:.2f}" if vwap > 0 else ""
            htf_tag = f" HTF={htf_bias}" if htf_bias else ""
            sess_tag = f" kz" if session_mult >= 1.0 else f" s={session_mult:.1f}"
            logger.info(
                f"[{epic}] Confluence: BUY={buy_count} SELL={sell_count} "
                f"< min={effective_min} [{votes_str}]{vwap_tag}{htf_tag}{sess_tag}"
            )
            return self._hold(epic, price)

        # HTF gate: block counter-trend entries entirely
        if _strat_settings.scalp_htf_gate_enabled and htf_bias is not None:
            if direction == SignalDirection.BUY and htf_bias == "bearish":
                logger.info(
                    f"[{epic}] HTF gate: BUY blocked by bearish 1H trend "
                    f"(confluence={confluence}/7)"
                )
                return self._hold(epic, price)
            if direction == SignalDirection.SELL and htf_bias == "bullish":
                logger.info(
                    f"[{epic}] HTF gate: SELL blocked by bullish 1H trend "
                    f"(confluence={confluence}/7)"
                )
                return self._hold(epic, price)

        # Confidence: map confluence count to [0.3, 1.0]
        # 3/7 = 0.43, 4/7 = 0.57, 5/7 = 0.71, 6/7 = 0.86, 7/7 = 1.0
        confidence = min(1.0, confluence / 7.0)

        # SL / TP from config
        sl_mult = config.stop_multiplier
        rr = config.risk_reward_ratio

        if direction == SignalDirection.BUY:
            stop = price - atr * sl_mult
            tp = price + atr * sl_mult * rr
        else:
            stop = price + atr * sl_mult
            tp = price - atr * sl_mult * rr

        vwap_info = f" VWAP={vwap:.2f}" if vwap > 0 else ""
        htf_info = f" HTF={htf_bias}" if htf_bias else ""
        logger.info(
            f"[{epic}] Confluence: {direction.value} "
            f"({confluence}/7) [{votes_str}]{vwap_info}{htf_info}"
        )

        # Assemble audit metadata
        zone = "kill_zone" if session_mult >= 1.0 else "off_killzone"
        if (_strat_settings.scalp_chop_zone_start
                <= utc_hour < _strat_settings.scalp_chop_zone_end):
            zone = "chop_zone"
        audit_metadata = {
            "votes": votes_data,
            "gates": {
                "session": {
                    "passed": True,
                    "session_mult": session_mult,
                    "utc_hour": utc_hour,
                    "zone": zone,
                },
                "dead_market": {"passed": True, "adx": adx_val},
                "vwap": {
                    "passed": True,
                    "price": price,
                    "vwap": vwap,
                    "bias": "above" if price > vwap else "below",
                },
                "htf": {
                    "passed": True,
                    "htf_bias": htf_bias,
                },
                "confluence": {
                    "passed": True,
                    "buy_count": buy_count,
                    "sell_count": sell_count,
                    "effective_min": effective_min,
                    "direction": direction.value,
                },
            },
            "market_snapshot": {
                "price": price,
                "atr": round(atr, 5),
                "rsi": round(float(current_bar.get("rsi_14", 0)), 1),
                "adx": round(adx_val, 1),
                "vwap": round(vwap, 4) if vwap else 0,
                "htf_bias": htf_bias or "neutral",
                "volume": float(current_bar.get("volume", 0)),
                "bb_width": round(bb_upper - bb_lower, 4),
            },
        }

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
            metadata=audit_metadata,
        )

    def evaluate_technical_quality(
        self,
        ml_direction: SignalDirection,
        epic: str,
        current_bar: dict,
        recent_bars: pl.DataFrame,
    ) -> dict:
        """Evaluate technical quality for a given ML direction.

        Used by ML-Primary mode: ML decides direction, this method reports
        how well the technicals support that direction (without applying
        gates or thresholds).

        Returns dict with vote breakdown, quality score, and gate alignment.
        """
        price = float(current_bar.get("close", 0))
        utc_hour = int(current_bar.get("utc_hour", 12))

        # Session check (hard block)
        session_mult = SessionFilter.get_session_multiplier(epic, utc_hour)
        if session_mult == 0.0:
            return {
                "agreeing_votes": 0, "opposing_votes": 0, "neutral_votes": 7,
                "quality_score": 0.0,
                "vwap_aligned": False, "htf_aligned": None,
                "session_blocked": True, "dead_market_blocked": False,
                "votes_detail": {}, "session_mult": 0.0,
            }

        # Dead market check
        _dm_settings = get_settings()
        adx_val = float(current_bar.get("adx_14", 0))
        bb_upper = float(current_bar.get("bb_upper", 0))
        bb_lower = float(current_bar.get("bb_lower", 0))
        bb_mid = float(current_bar.get("bb_middle", 0))
        dead_market = False
        if (adx_val > 0 and bb_mid > 0
                and adx_val < _dm_settings.scalp_dead_market_adx):
            bb_width_now = (bb_upper - bb_lower) / bb_mid if bb_mid > 0 else 0
            bb_pctile = 50.0
            if ("bb_upper" in recent_bars.columns
                    and "bb_lower" in recent_bars.columns
                    and "bb_middle" in recent_bars.columns
                    and len(recent_bars) > 10):
                widths = (
                    (recent_bars["bb_upper"] - recent_bars["bb_lower"])
                    / recent_bars["bb_middle"]
                ).drop_nulls().to_list()
                if widths:
                    count_below = sum(1 for w in widths if w <= bb_width_now)
                    bb_pctile = count_below / len(widths) * 100
            if bb_pctile < _dm_settings.scalp_dead_market_bb_pctile:
                dead_market = True

        if dead_market:
            return {
                "agreeing_votes": 0, "opposing_votes": 0, "neutral_votes": 7,
                "quality_score": 0.0,
                "vwap_aligned": False, "htf_aligned": None,
                "session_blocked": False, "dead_market_blocked": True,
                "votes_detail": {}, "session_mult": session_mult,
            }

        # Collect all 7 votes (same as generate_signal)
        ema_vote, _ = self._vote_ema(
            float(current_bar.get("ema_9", 0)),
            float(current_bar.get("ema_21", 0)),
        )
        rsi_vote, _ = self._vote_rsi(float(current_bar.get("rsi_14", 50)))
        macd_vote, _ = self._vote_macd(
            float(current_bar.get("macd_histogram", 0)),
            float(current_bar.get("macd", 0)),
            float(current_bar.get("macd_signal", 0)),
        )
        vol_vote, _ = self._vote_volume(
            float(current_bar.get("volume", 0)),
            float(current_bar.get("volume_sma_20", 0)),
        )
        adx_vote, _ = self._vote_adx(float(current_bar.get("adx_14", 0)))
        bb_vote, _ = self._vote_bb_squeeze(
            bb_upper, bb_lower,
            float(current_bar.get("keltner_upper", 0)),
            float(current_bar.get("keltner_lower", 0)),
            price,
            bb_mid,
        )
        sil_composite = float(current_bar.get("sil_composite_score", 0.0))
        sentiment_vote, _ = self._vote_sentiment(sil_composite)

        # Map ML direction to target sign
        target_sign = 1 if ml_direction == SignalDirection.BUY else -1

        # Count directional votes relative to ML direction
        directional_votes = [ema_vote, rsi_vote, macd_vote, bb_vote, sentiment_vote]
        agreeing = sum(1 for v in directional_votes if v == target_sign)
        opposing = sum(1 for v in directional_votes if v == -target_sign)
        neutral = sum(1 for v in directional_votes if v == 0)

        # Confirmation votes (VOL, ADX) add only if >= 2 directional agree
        if agreeing >= 2:
            if vol_vote > 0:
                agreeing += 1
            if adx_vote > 0:
                agreeing += 1

        quality_score = agreeing / 7.0

        # VWAP alignment (soft — reported, not gated)
        vwap = float(current_bar.get("vwap", 0))
        if vwap > 0:
            vwap_aligned = (
                (ml_direction == SignalDirection.BUY and price >= vwap)
                or (ml_direction == SignalDirection.SELL and price <= vwap)
            )
        else:
            vwap_aligned = True  # no VWAP data → assume aligned

        # HTF alignment (soft — reported, not gated)
        htf_bias = current_bar.get("htf_bias")
        if htf_bias == "bullish":
            htf_aligned = ml_direction == SignalDirection.BUY
        elif htf_bias == "bearish":
            htf_aligned = ml_direction == SignalDirection.SELL
        else:
            htf_aligned = None  # no HTF data

        votes_detail = {
            "ema": ema_vote, "rsi": rsi_vote, "macd": macd_vote,
            "bb": bb_vote, "vol": vol_vote, "adx": adx_vote,
            "sentiment": sentiment_vote,
        }

        return {
            "agreeing_votes": agreeing,
            "opposing_votes": opposing,
            "neutral_votes": neutral,
            "quality_score": round(quality_score, 4),
            "vwap_aligned": vwap_aligned,
            "htf_aligned": htf_aligned,
            "session_blocked": False,
            "dead_market_blocked": False,
            "votes_detail": votes_detail,
            "session_mult": session_mult,
        }

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
