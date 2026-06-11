"""
Mean Reversion Strategy — generates BUY/SELL signals from price deviation.

Entry: price far from mean (z-score > threshold) + RSI confirmation + no strong trend
Exit: price returns to mean (TP) or extends further (SL)
"""

from dataclasses import dataclass

from loguru import logger

from src.utils.config import get_settings
from src.utils.constants import COMMODITY_ASSETS, CRYPTO_ASSETS, FOREX_ASSETS

# ATR multipliers per asset class.
# Target: SL between 1-2.5% for all classes regardless of per-asset volatility.
# Forex/Indices have low ATR% -> can afford 2.0x. High-vol assets need tighter.
_STOCK_ASSETS = {"NVDA", "TSLA"}
_INDEX_ASSETS = {"US500", "DE40", "NAS100"}

# (SL_ATR_MULT, TP_MAX_ATR) — TP = SL * 0.75 for consistent R:R across classes
_CLASS_ATR_PARAMS: dict[str, tuple[float, float]] = {
    "forex": (2.0, 1.5),  # ATR% ~0.2-0.3% -> SL ~0.5%
    "index": (2.0, 1.5),  # ATR% ~0.7-1.0% -> SL ~1.5-2.0%
    "commodity": (1.2, 0.9),  # ATR% ~1.4-3.2% -> SL ~1.7-3.8%
    "crypto": (1.2, 0.9),  # ATR% ~1.4-1.9% -> SL ~1.7-2.3%
    "stock": (1.0, 0.75),  # ATR% ~1.4-2.2% -> SL ~1.4-2.2%
}


def _get_atr_params(epic: str) -> tuple[float, float]:
    """Return (SL_ATR_MULT, TP_MAX_ATR) for the given epic's asset class."""
    if epic in _STOCK_ASSETS:
        return _CLASS_ATR_PARAMS["stock"]
    if epic in _INDEX_ASSETS:
        return _CLASS_ATR_PARAMS["index"]
    if epic in CRYPTO_ASSETS:
        return _CLASS_ATR_PARAMS["crypto"]
    if epic in COMMODITY_ASSETS:
        return _CLASS_ATR_PARAMS["commodity"]
    # Default: forex (lowest vol, widest mult is safe)
    return _CLASS_ATR_PARAMS["forex"]


def _enforce_min_tp(
    epic: str,
    current_price: float,
    sl_dist: float | None,
    tp_dist: float,
) -> tuple[float | None, float]:
    """Apply the per-asset-class TP floor and widen SL to keep R:R intact.

    FOREX ATR is so small (USDJPY ATR ~0.05 on price 159 = 0.03%) that
    `TP_MAX_ATR * atr` shrinks the target to noise level — slippage and
    half-spread alone wipe out the edge before TP is reached. The
    `mr_min_tp_pct` floor (0.15% / 0.20% forex) raises the target to
    where the round-trip cost is recoverable; SL is scaled by the same
    factor so the strategy's intrinsic R:R is preserved.
    """
    if current_price <= 0 or tp_dist <= 0:
        return sl_dist, tp_dist
    settings = get_settings()
    try:
        raw_pct = settings.mr_min_tp_pct_forex if epic in FOREX_ASSETS else settings.mr_min_tp_pct
        min_pct = float(raw_pct)
    except (TypeError, ValueError):
        # Mocked settings (e.g. unit tests) — leave the trade untouched
        # rather than crashing the strategy on a sentinel value.
        return sl_dist, tp_dist
    # Sanity bound — a 100% TP distance is nonsense; treat anything
    # outside (0, 0.1] as a mock-leaked sentinel and skip the floor.
    if not (0 < min_pct <= 0.1):
        return sl_dist, tp_dist
    min_tp_dist = current_price * min_pct
    if tp_dist >= min_tp_dist:
        return sl_dist, tp_dist
    scale = min_tp_dist / tp_dist
    new_tp = min_tp_dist
    new_sl = sl_dist * scale if sl_dist is not None and sl_dist > 0 else sl_dist
    logger.info(
        f"[{epic}] TP floor applied: {tp_dist:.5f} → {new_tp:.5f} "
        f"({min_pct * 100:.2f}% min); SL scaled ×{scale:.2f}"
    )
    return new_sl, new_tp


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

    def generate_signal(self, market_data: dict, epic: str = "") -> MRSignal:
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

        # SL/TP sizing: per-asset-class ATR multiples.
        # Literature (Lopez de Prado, QuantPedia) says MR works at TP/SL ~ 0.5-1.0.
        # Different asset classes have wildly different ATR% so a single multiplier
        # produces 0.5% SL on forex but 5% SL on stocks — we normalize per class.
        SL_ATR_MULT, TP_MAX_ATR = _get_atr_params(epic)

        # SELL signal: price far above mean. RSI is a confidence boost, not a hard gate.
        if z_score > z_entry:
            # Confidence: how extreme (z=2 -> 0.5, z=3 -> 1.0)
            confidence = min((z_score - z_entry) / (z_stop - z_entry), 1.0)
            # RSI boost: overbought confirms the SELL setup
            if rsi > self.RSI_OB:
                confidence = min(confidence + 0.2, 1.0)

            # SL: 2 ATR ABOVE current price (price extends further against us)
            sl = current_price + SL_ATR_MULT * atr if atr > 0 else None

            # TP: return to mean, but capped to avoid unrealistic R:R
            raw_tp = mean_target
            min_tp = current_price - TP_MAX_ATR * atr if atr > 0 else raw_tp
            # For SELL: TP must be BELOW entry; cap distance to TP_MAX_ATR
            tp = max(raw_tp, min_tp) if raw_tp < current_price else min_tp

            # Enforce min TP distance (forex micro-target guard).
            sl_dist = (sl - current_price) if sl and sl > current_price else None
            tp_dist = current_price - tp
            new_sl_dist, new_tp_dist = _enforce_min_tp(epic, current_price, sl_dist, tp_dist)
            if new_tp_dist != tp_dist:
                tp = current_price - new_tp_dist
                if new_sl_dist is not None:
                    sl = current_price + new_sl_dist

            rr = (
                (current_price - tp) / (sl - current_price)
                if sl and tp and sl > current_price
                else 0
            )
            logger.info(
                f"MR SELL: z={z_score:.2f}, RSI={rsi:.1f}, ADX={adx:.1f}, "
                f"entry={current_price:.2f}, TP={tp:.2f}, "
                f"SL={f'{sl:.2f}' if sl else 'N/A'}, R:R={rr:.2f}"
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

            # SL: 2 ATR BELOW current price
            sl = current_price - SL_ATR_MULT * atr if atr > 0 else None

            # TP: return to mean, capped at TP_MAX_ATR away
            raw_tp = mean_target
            max_tp = current_price + TP_MAX_ATR * atr if atr > 0 else raw_tp
            # For BUY: TP must be ABOVE entry; cap distance
            tp = min(raw_tp, max_tp) if raw_tp > current_price else max_tp

            # Enforce min TP distance (forex micro-target guard).
            sl_dist = (current_price - sl) if sl and sl < current_price else None
            tp_dist = tp - current_price
            new_sl_dist, new_tp_dist = _enforce_min_tp(epic, current_price, sl_dist, tp_dist)
            if new_tp_dist != tp_dist:
                tp = current_price + new_tp_dist
                if new_sl_dist is not None:
                    sl = current_price - new_sl_dist

            rr = (
                (tp - current_price) / (current_price - sl)
                if sl and tp and sl < current_price
                else 0
            )
            logger.info(
                f"MR BUY: z={z_score:.2f}, RSI={rsi:.1f}, ADX={adx:.1f}, "
                f"entry={current_price:.2f}, TP={tp:.2f}, "
                f"SL={f'{sl:.2f}' if sl else 'N/A'}, R:R={rr:.2f}"
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
        logger.info(
            f"MR HOLD: z={z_score:.2f} (entry=±{z_entry}), bb_pctb={bb_pctb:.3f}, "
            f"vwap_z={vwap_z:.2f}, RSI={rsi:.1f}, ADX={adx:.1f}"
        )
        return MRSignal(
            direction="HOLD",
            z_score=z_score,
            reason=f"No extreme: z={z_score:.2f}, RSI={rsi:.1f}",
        )
