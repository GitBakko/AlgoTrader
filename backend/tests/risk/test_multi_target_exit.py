"""Tests for TP1/TP2 multi-target exit calculation in RiskManager."""

import pytest

from src.risk.risk_manager import RiskManager
from src.strategy.schemas import SignalDirection, TradingSignal


def _make_signal(
    epic: str = "XAUUSD",
    direction: SignalDirection = SignalDirection.BUY,
    confidence: float = 0.80,
    price: float = 2000.0,
    signal_class: int = 2,
) -> TradingSignal:
    """Helper to create trading signals."""
    return TradingSignal(
        epic=epic,
        direction=direction,
        confidence=confidence,
        signal_class=signal_class,
        entry_price=price,
    )


@pytest.mark.unit
@pytest.mark.risk
class TestMultiTargetExit:
    """Tests for TP1/TP2 calculation in RiskManager."""

    def test_tp1_tp2_calculated_buy(self):
        """BUY: TP1 = entry + risk, TP2 = entry + 2*risk."""
        rm = RiskManager(initial_equity=100000.0)
        signal = _make_signal(
            direction=SignalDirection.BUY,
            price=2000.0,
            confidence=0.80,
            signal_class=2,
        )

        result = rm.check_trade(signal, equity=100000.0, atr=20.0)

        assert result.approved is True
        # Stop loss is 2 ATR below entry: 2000 - (2 * 20) = 1960
        # Risk distance = 2000 - 1960 = 40
        # TP1 = 2000 + 40 = 2040
        # TP2 = 2000 + 80 = 2080
        assert result.stop_loss == pytest.approx(1960.0, rel=1e-4)
        assert result.take_profit_1 == pytest.approx(2040.0, rel=1e-4)
        assert result.take_profit_2 == pytest.approx(2080.0, rel=1e-4)

    def test_tp1_tp2_calculated_sell(self):
        """SELL: TP1 = entry - risk, TP2 = entry - 2*risk."""
        rm = RiskManager(initial_equity=100000.0)
        signal = _make_signal(
            direction=SignalDirection.SELL,
            price=2000.0,
            confidence=0.80,
            signal_class=0,
        )

        result = rm.check_trade(signal, equity=100000.0, atr=20.0)

        assert result.approved is True
        # Stop loss is 2 ATR above entry: 2000 + (2 * 20) = 2040
        # Risk distance = 2040 - 2000 = 40
        # TP1 = 2000 - 40 = 1960
        # TP2 = 2000 - 80 = 1920
        assert result.stop_loss == pytest.approx(2040.0, rel=1e-4)
        assert result.take_profit_1 == pytest.approx(1960.0, rel=1e-4)
        assert result.take_profit_2 == pytest.approx(1920.0, rel=1e-4)

    def test_partial_close_pct_default(self):
        """Default partial_close_pct is 0.50."""
        rm = RiskManager(initial_equity=100000.0)
        signal = _make_signal()

        result = rm.check_trade(signal, equity=100000.0, atr=20.0)

        assert result.approved is True
        assert result.partial_close_pct == pytest.approx(0.50, rel=1e-4)

    def test_tp1_less_than_tp2_buy(self):
        """TP1 < TP2 for BUY."""
        rm = RiskManager(initial_equity=100000.0)
        signal = _make_signal(
            direction=SignalDirection.BUY,
            price=50000.0,  # Bitcoin
            confidence=0.75,
            signal_class=2,
        )

        result = rm.check_trade(signal, equity=100000.0, atr=1000.0)

        assert result.approved is True
        assert result.take_profit_1 < result.take_profit_2
        # TP1 should be closer to entry than TP2
        assert abs(result.take_profit_1 - signal.entry_price) < abs(
            result.take_profit_2 - signal.entry_price
        )

    def test_tp1_greater_than_tp2_sell(self):
        """TP1 > TP2 for SELL."""
        rm = RiskManager(initial_equity=100000.0)
        signal = _make_signal(
            direction=SignalDirection.SELL,
            price=4500.0,  # S&P 500
            confidence=0.85,
            signal_class=0,
        )

        result = rm.check_trade(signal, equity=100000.0, atr=30.0)

        assert result.approved is True
        assert result.take_profit_1 > result.take_profit_2
        # TP1 should be closer to entry than TP2
        assert abs(result.take_profit_1 - signal.entry_price) < abs(
            result.take_profit_2 - signal.entry_price
        )

    def test_tp1_between_entry_and_tp2(self):
        """TP1 is between entry and TP2 (profit progression test)."""
        rm = RiskManager(initial_equity=100000.0)

        # Test BUY
        signal_buy = _make_signal(
            direction=SignalDirection.BUY,
            price=2000.0,
            signal_class=2,
        )
        result_buy = rm.check_trade(signal_buy, equity=100000.0, atr=25.0)
        assert result_buy.approved is True
        # For BUY: entry < TP1 < TP2
        assert signal_buy.entry_price < result_buy.take_profit_1
        assert result_buy.take_profit_1 < result_buy.take_profit_2

        # Test SELL
        signal_sell = _make_signal(
            direction=SignalDirection.SELL,
            price=2000.0,
            signal_class=0,
        )
        result_sell = rm.check_trade(signal_sell, equity=100000.0, atr=25.0)
        assert result_sell.approved is True
        # For SELL: entry > TP1 > TP2
        assert signal_sell.entry_price > result_sell.take_profit_1
        assert result_sell.take_profit_1 > result_sell.take_profit_2
