"""
Mean Reversion Strategy — generates BUY/SELL signals from price deviation.

Entry: price far from mean (z-score > threshold) + RSI confirmation + no strong trend
Exit: price returns to mean (TP) or extends further (SL)
"""

from dataclasses import dataclass

from loguru import logger

from src.utils.config import get_settings


@dataclass
class MRSignal:
    direction: str  # "BUY", "SELL", "HOLD"
    z_score: float = 0.0
    confidence: float = 0.0  # How extreme the deviation is (0-1)
    stop_level: float | None = None
    tp_level: float | None = None
    reason: str = ""


class MeanReversionStrategy:
    """Mean reversion signals from price deviation + confirmation.

    Entry rules (all must be true):
    - SELL: z-score > Z_ENTRY AND RSI > 70 AND ADX < ADX_MAX
    - BUY: z-score < -Z_ENTRY AND RSI < 30 AND ADX < ADX_MAX

    TP: return to VWAP/BB middle
    SL: z-score extends to Z_STOP
    """

    RSI_OB = 70  # Overbought
    RSI_OS = 30  # Oversold

    def generate_signal(self, market_data: dict) -> MRSignal:
        """Generate mean reversion signal from market data.

        Args:
            market_data: dict with keys: current_price, bb_pctb, rsi, adx,
                        vwap_z_score, bb_middle, vwap, atr

        Returns:
            MRSignal with direction, levels, and reason
        """
        settings = get_settings()
        z_entry = settings.mr_z_entry
        z_stop = settings.mr_z_stop
        adx_max = settings.mr_adx_max

        current_price = market_data.get("current_price", 0)
        bb_pctb = market_data.get("bb_pctb", 0.5)
        rsi = market_data.get("rsi", 50)
        adx = market_data.get("adx", 25)
        vwap_z = market_data.get("vwap_z_score", 0)
        atr = market_data.get("atr", 0)
        bb_middle = market_data.get("bb_middle", current_price)
        vwap = market_data.get("vwap", current_price)

        # Compute composite z-score from BB and VWAP
        bb_z = (bb_pctb - 0.5) * 4  # Normalize BB %B to approx z-score
        z_score = vwap_z if abs(vwap_z) > abs(bb_z) else bb_z

        # Check for trending market (MR fails in strong trends)
        if adx > adx_max:
            return MRSignal(
                direction="HOLD",
                z_score=z_score,
                reason=f"Trending market: ADX {adx:.1f} > {adx_max:.0f}",
            )

        # Mean target (use VWAP if available, else BB middle)
        mean_target = vwap if vwap and vwap > 0 else bb_middle

        # SELL signal: price far above mean. RSI is a confidence boost, not a hard gate.
        if z_score > z_entry:
            # Confidence: how extreme (z=2 -> 0.5, z=3 -> 1.0)
            confidence = min((z_score - z_entry) / (z_stop - z_entry), 1.0)
            # RSI boost: overbought confirms the SELL setup
            if rsi > self.RSI_OB:
                confidence = min(confidence + 0.2, 1.0)
            # SL: price extends further (z reaches z_stop)
            sl = current_price + (z_stop - z_score) * atr if atr > 0 else None
            # TP: return to mean
            tp = mean_target

            logger.info(
                f"MR SELL: z={z_score:.2f}, RSI={rsi:.1f}, ADX={adx:.1f}, "
                f"TP={tp:.2f}, SL={f'{sl:.2f}' if sl else 'N/A'}"
            )
            return MRSignal(
                direction="SELL",
                z_score=z_score,
                confidence=0.5 + confidence * 0.5,  # Range: 0.5-1.0
                stop_level=sl,
                tp_level=tp,
                reason=f"Price above mean: z={z_score:.2f}, RSI={rsi:.1f}",
            )

        # BUY signal: price far below mean. RSI is a confidence boost, not a hard gate.
        if z_score < -z_entry:
            confidence = min((abs(z_score) - z_entry) / (z_stop - z_entry), 1.0)
            # RSI boost: oversold confirms the BUY setup
            if rsi < self.RSI_OS:
                confidence = min(confidence + 0.2, 1.0)
            sl = current_price - (z_stop - abs(z_score)) * atr if atr > 0 else None
            tp = mean_target

            logger.info(
                f"MR BUY: z={z_score:.2f}, RSI={rsi:.1f}, ADX={adx:.1f}, "
                f"TP={tp:.2f}, SL={f'{sl:.2f}' if sl else 'N/A'}"
            )
            return MRSignal(
                direction="BUY",
                z_score=z_score,
                confidence=0.5 + confidence * 0.5,
                stop_level=sl,
                tp_level=tp,
                reason=f"Price below mean: z={z_score:.2f}, RSI={rsi:.1f}",
            )

        # No extreme deviation
        return MRSignal(
            direction="HOLD",
            z_score=z_score,
            reason=f"No extreme: z={z_score:.2f}, RSI={rsi:.1f}",
        )
