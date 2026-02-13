"""
Pairs Trading Strategy for Gold-Bitcoin.

Exploits mean-reversion of the spread between cointegrated assets.
Entry: Z-score outside ±2.0 SD. Exit: Z-score returns to 0 (or time stop).
Dollar-neutral: size_a * price_a = size_b * price_b * hedge_ratio.
"""

import numpy as np
from loguru import logger
from pydantic import BaseModel, Field

from src.strategy.pairs.cointegration import CointegrationAnalyzer, CointegrationResult


class PairsSignal(BaseModel):
    """Signal from pairs trading strategy."""

    action: str  # "LONG_SPREAD", "SHORT_SPREAD", "CLOSE", "HOLD"
    z_score: float
    hedge_ratio: float
    size_a: float = 0.0  # Size for asset A
    size_b: float = 0.0  # Size for asset B
    direction_a: str = "HOLD"  # BUY/SELL/HOLD for asset A
    direction_b: str = "HOLD"  # BUY/SELL/HOLD for asset B
    confidence: float = 0.0
    reason: str = ""


class PairsConfig(BaseModel):
    """Configuration for pairs trading strategy."""

    entry_z: float = Field(default=2.0, ge=1.0, le=4.0)
    exit_z: float = Field(default=0.5, ge=0.0, le=2.0)
    stop_z: float = Field(default=3.0, ge=2.0, le=5.0)
    max_hold_bars: int = Field(default=168, ge=24, le=504)  # 1 week at 1h
    zscore_lookback: int = Field(default=50, ge=20, le=200)
    recalibration_window: int = Field(default=504, ge=100, le=2016)  # 21 days at 1h
    min_cointegration_period: int = Field(default=252, ge=100, le=1000)
    equity_per_leg: float = Field(default=5000.0, ge=100.0)


class PairsTradingStrategy:
    """
    Pairs trading strategy for Gold-Bitcoin.

    Workflow:
    1. Test cointegration between XAUUSD and BTCUSD
    2. If cointegrated, compute spread and z-score
    3. Entry: z < -entry_z (long spread) or z > entry_z (short spread)
    4. Exit: z returns to ±exit_z, or z exceeds ±stop_z, or time stop
    """

    def __init__(self, config: PairsConfig | None = None):
        self.config = config or PairsConfig()
        self._analyzer = CointegrationAnalyzer()
        self._coint_result: CointegrationResult | None = None
        self._current_position: PairsSignal | None = None
        self._bars_in_trade: int = 0

    @property
    def is_cointegrated(self) -> bool:
        return self._coint_result is not None and self._coint_result.is_cointegrated

    @property
    def hedge_ratio(self) -> float:
        if self._coint_result is None:
            return 0.0
        return self._coint_result.hedge_ratio

    @property
    def has_position(self) -> bool:
        return self._current_position is not None and self._current_position.action != "HOLD"

    def calibrate(
        self,
        prices_a: np.ndarray,
        prices_b: np.ndarray,
    ) -> CointegrationResult:
        """
        Calibrate the pair relationship (run cointegration test).

        Args:
            prices_a: Gold prices
            prices_b: Bitcoin prices

        Returns:
            CointegrationResult
        """
        self._coint_result = self._analyzer.test_cointegration(prices_a, prices_b)
        logger.info(
            f"Pairs calibration: cointegrated={self._coint_result.is_cointegrated} "
            f"hedge_ratio={self._coint_result.hedge_ratio:.4f} "
            f"half_life={self._coint_result.half_life:.1f} "
            f"p_value={self._coint_result.p_value_approx:.4f}"
        )
        return self._coint_result

    def generate_signal(
        self,
        prices_a: np.ndarray,
        prices_b: np.ndarray,
        current_price_a: float,
        current_price_b: float,
    ) -> PairsSignal:
        """
        Generate a pairs trading signal.

        Args:
            prices_a: Recent Gold prices (enough for zscore_lookback)
            prices_b: Recent Bitcoin prices
            current_price_a: Current Gold price
            current_price_b: Current Bitcoin price

        Returns:
            PairsSignal with action and sizing
        """
        if not self.is_cointegrated:
            return PairsSignal(
                action="HOLD",
                z_score=0.0,
                hedge_ratio=0.0,
                reason="Not cointegrated",
            )

        hr = self._coint_result.hedge_ratio

        # Compute spread and z-score
        spread = self._analyzer.compute_spread(prices_a, prices_b, hr)
        zscore = self._analyzer.compute_zscore(spread, self.config.zscore_lookback)

        current_z = zscore[-1] if len(zscore) > 0 and not np.isnan(zscore[-1]) else 0.0

        # Check for position exit first
        if self.has_position:
            self._bars_in_trade += 1
            return self._check_exit(current_z, hr, current_price_a, current_price_b)

        # Check for entry
        return self._check_entry(current_z, hr, current_price_a, current_price_b)

    def _check_entry(
        self,
        z_score: float,
        hedge_ratio: float,
        price_a: float,
        price_b: float,
    ) -> PairsSignal:
        """Check for entry conditions."""
        cfg = self.config

        if z_score <= -cfg.entry_z:
            # Spread is below mean: long spread (buy A, sell B)
            size_a, size_b = self._compute_sizes(price_a, price_b, hedge_ratio)
            signal = PairsSignal(
                action="LONG_SPREAD",
                z_score=z_score,
                hedge_ratio=hedge_ratio,
                size_a=size_a,
                size_b=size_b,
                direction_a="BUY",
                direction_b="SELL",
                confidence=min(0.75, 0.50 + abs(z_score - cfg.entry_z) * 0.05),
                reason=f"Z-score {z_score:.2f} <= -{cfg.entry_z}",
            )
            self._current_position = signal
            self._bars_in_trade = 0
            logger.info(
                f"Pairs LONG_SPREAD: z={z_score:.2f} "
                f"A_size={size_a:.4f} B_size={size_b:.4f}"
            )
            return signal

        elif z_score >= cfg.entry_z:
            # Spread is above mean: short spread (sell A, buy B)
            size_a, size_b = self._compute_sizes(price_a, price_b, hedge_ratio)
            signal = PairsSignal(
                action="SHORT_SPREAD",
                z_score=z_score,
                hedge_ratio=hedge_ratio,
                size_a=size_a,
                size_b=size_b,
                direction_a="SELL",
                direction_b="BUY",
                confidence=min(0.75, 0.50 + abs(z_score - cfg.entry_z) * 0.05),
                reason=f"Z-score {z_score:.2f} >= {cfg.entry_z}",
            )
            self._current_position = signal
            self._bars_in_trade = 0
            logger.info(
                f"Pairs SHORT_SPREAD: z={z_score:.2f} "
                f"A_size={size_a:.4f} B_size={size_b:.4f}"
            )
            return signal

        return PairsSignal(
            action="HOLD",
            z_score=z_score,
            hedge_ratio=hedge_ratio,
            reason=f"Z-score {z_score:.2f} within entry zone",
        )

    def _check_exit(
        self,
        z_score: float,
        hedge_ratio: float,
        price_a: float,
        price_b: float,
    ) -> PairsSignal:
        """Check for exit conditions on current position."""
        cfg = self.config
        pos = self._current_position

        # Mean reversion exit
        if abs(z_score) <= cfg.exit_z:
            self._close_position()
            return PairsSignal(
                action="CLOSE",
                z_score=z_score,
                hedge_ratio=hedge_ratio,
                reason=f"Mean reversion: z={z_score:.2f} within ±{cfg.exit_z}",
            )

        # Stop loss exit
        if pos.action == "LONG_SPREAD" and z_score <= -cfg.stop_z:
            self._close_position()
            return PairsSignal(
                action="CLOSE",
                z_score=z_score,
                hedge_ratio=hedge_ratio,
                reason=f"Stop loss LONG: z={z_score:.2f} <= -{cfg.stop_z}",
            )

        if pos.action == "SHORT_SPREAD" and z_score >= cfg.stop_z:
            self._close_position()
            return PairsSignal(
                action="CLOSE",
                z_score=z_score,
                hedge_ratio=hedge_ratio,
                reason=f"Stop loss SHORT: z={z_score:.2f} >= {cfg.stop_z}",
            )

        # Time stop
        if self._bars_in_trade >= cfg.max_hold_bars:
            bars_held = self._bars_in_trade
            self._close_position()
            return PairsSignal(
                action="CLOSE",
                z_score=z_score,
                hedge_ratio=hedge_ratio,
                reason=f"Time stop: {bars_held} bars",
            )

        # Continue holding
        return PairsSignal(
            action=pos.action,
            z_score=z_score,
            hedge_ratio=hedge_ratio,
            size_a=pos.size_a,
            size_b=pos.size_b,
            direction_a=pos.direction_a,
            direction_b=pos.direction_b,
            confidence=pos.confidence,
            reason=f"Holding: z={z_score:.2f}, bars={self._bars_in_trade}",
        )

    def _compute_sizes(
        self,
        price_a: float,
        price_b: float,
        hedge_ratio: float,
    ) -> tuple[float, float]:
        """
        Compute dollar-neutral position sizes.
        size_a * price_a = size_b * price_b * hedge_ratio
        """
        equity = self.config.equity_per_leg

        if price_a <= 0 or price_b <= 0:
            return 0.0, 0.0

        size_a = equity / price_a
        # Dollar-neutral: match notional exposure
        size_b = (equity * abs(hedge_ratio)) / price_b if hedge_ratio != 0 else 0.0

        return round(size_a, 6), round(size_b, 6)

    def _close_position(self) -> None:
        """Reset position state."""
        self._current_position = None
        self._bars_in_trade = 0

    def get_status(self) -> dict:
        """Get current strategy status."""
        return {
            "is_cointegrated": self.is_cointegrated,
            "hedge_ratio": self.hedge_ratio,
            "has_position": self.has_position,
            "bars_in_trade": self._bars_in_trade,
            "current_action": self._current_position.action if self._current_position else None,
            "half_life": self._coint_result.half_life if self._coint_result else None,
        }
