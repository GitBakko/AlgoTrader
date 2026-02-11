"""
Signal generator: converts ML predictions into actionable trading signals.
Applies confidence filtering, technical confirmation, and counter-trend penalties.
"""

from loguru import logger

from src.models.schemas import PredictionResult, SignalClass
from src.risk.stop_manager import StopManager
from src.strategy.regime_adapter import RegimeAdapter
from src.strategy.schemas import SignalDirection, StrategyConfig, TradingSignal


# Map SignalClass to direction
_SIGNAL_TO_DIRECTION: dict[int, SignalDirection] = {
    SignalClass.STRONG_BUY: SignalDirection.BUY,
    SignalClass.BUY: SignalDirection.BUY,
    SignalClass.HOLD: SignalDirection.HOLD,
    SignalClass.SELL: SignalDirection.SELL,
    SignalClass.STRONG_SELL: SignalDirection.SELL,
}


def _make_hold_signal(epic: str, price: float, regime: str | None) -> TradingSignal:
    """Create a HOLD signal."""
    return TradingSignal(
        epic=epic,
        direction=SignalDirection.HOLD,
        confidence=0.0,
        signal_class=SignalClass.HOLD,
        regime=regime,
        technical_confirmation=False,
        entry_price=price,
    )


class SignalGenerator:
    """Generates trading signals from ML predictions with filters and confirmations."""

    @staticmethod
    def generate_signal(
        prediction: PredictionResult,
        epic: str,
        current_price: float,
        atr: float,
        rsi: float | None = None,
        regime: str | None = None,
        config: StrategyConfig | None = None,
    ) -> TradingSignal:
        """
        Generate a trading signal from an ML prediction.

        Pipeline:
        1. Check minimum confidence threshold
        2. Map SignalClass to BUY/SELL/HOLD direction
        3. RSI overbought/oversold filter
        4. Counter-trend penalty
        5. Re-check confidence after penalty
        6. Calculate suggested SL/TP

        Args:
            prediction: ML model prediction result
            epic: Asset epic code
            current_price: Current market price
            atr: Current ATR value
            rsi: Current RSI value (optional, skips RSI filter if None)
            regime: Current market regime (optional)
            config: Strategy configuration (uses defaults if None)

        Returns:
            TradingSignal with direction, confidence, and suggested levels
        """
        cfg = config or StrategyConfig(epic=epic)
        confidence = prediction.confidence

        # 1. Check minimum confidence threshold
        if confidence < cfg.min_confidence:
            logger.debug(
                f"{epic}: Confidence {confidence:.2f} below threshold "
                f"{cfg.min_confidence:.2f} -> HOLD"
            )
            return _make_hold_signal(epic, current_price, regime)

        # 2. Map SignalClass to direction
        direction = _SIGNAL_TO_DIRECTION.get(prediction.signal_class, SignalDirection.HOLD)
        if direction == SignalDirection.HOLD:
            return _make_hold_signal(epic, current_price, regime)

        # 3. RSI overbought/oversold filter
        technical_confirmation = True
        if rsi is not None:
            if direction == SignalDirection.BUY and rsi > cfg.overbought_rsi:
                logger.debug(
                    f"{epic}: BUY signal rejected, RSI={rsi:.1f} > {cfg.overbought_rsi} "
                    f"(overbought) -> HOLD"
                )
                return _make_hold_signal(epic, current_price, regime)
            if direction == SignalDirection.SELL and rsi < cfg.oversold_rsi:
                logger.debug(
                    f"{epic}: SELL signal rejected, RSI={rsi:.1f} < {cfg.oversold_rsi} "
                    f"(oversold) -> HOLD"
                )
                return _make_hold_signal(epic, current_price, regime)

        # 4. Counter-trend penalty
        if RegimeAdapter.is_counter_trend(direction.value, regime):
            original = confidence
            confidence *= cfg.counter_trend_penalty
            logger.debug(
                f"{epic}: Counter-trend penalty applied: "
                f"{original:.2f} -> {confidence:.2f} "
                f"({direction.value} in {regime})"
            )

        # 5. Re-check confidence after penalty
        if confidence < cfg.min_confidence:
            logger.debug(
                f"{epic}: Confidence {confidence:.2f} below threshold "
                f"after counter-trend penalty -> HOLD"
            )
            return _make_hold_signal(epic, current_price, regime)

        # 6. Calculate suggested SL/TP
        suggested_stop = StopManager.calculate_stop_loss(
            direction=direction.value,
            entry_price=current_price,
            atr=atr,
            multiplier=cfg.stop_multiplier,
        )
        suggested_tp = StopManager.calculate_take_profit(
            direction=direction.value,
            entry_price=current_price,
            atr=atr,
            multiplier=cfg.stop_multiplier,
            risk_reward=cfg.risk_reward_ratio,
        )

        return TradingSignal(
            epic=epic,
            direction=direction,
            confidence=confidence,
            signal_class=prediction.signal_class,
            regime=regime,
            technical_confirmation=technical_confirmation,
            entry_price=current_price,
            suggested_stop=suggested_stop,
            suggested_tp=suggested_tp,
        )
