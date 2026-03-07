"""Tests for the ORB+FVG M1 backtest runner."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.backtest.orb_fvg_runner import (
    ORBBacktestResult,
    ORBTrade,
    _calculate_metrics,
    _simulate_trade,
)
from src.strategy.orb_fvg_strategy import FVGSignal
from src.strategy.schemas import SignalDirection


# ---------------------------------------------------------------------------
# Helper: build a bar dict
# ---------------------------------------------------------------------------

def _bar(hour: int, minute: int, o: float, h: float, l: float, c: float) -> dict:
    """Create a bar dict with a UTC timestamp on 2026-01-15."""
    return {
        "timestamp": datetime(2026, 1, 15, hour, minute, tzinfo=timezone.utc),
        "open": o,
        "high": h,
        "low": l,
        "close": c,
        "volume": 100.0,
    }


# ---------------------------------------------------------------------------
# _simulate_trade tests
# ---------------------------------------------------------------------------

class TestSimulateTrade:
    """Verify bar-by-bar SL / TP / EOD logic."""

    def _make_fvg(
        self,
        direction: str = "BUY",
        entry: float = 100.0,
        sl: float = 98.0,
        tp: float = 104.0,
    ) -> FVGSignal:
        return FVGSignal(
            direction=SignalDirection.BUY if direction == "BUY" else SignalDirection.SELL,
            fvg_type="bullish" if direction == "BUY" else "bearish",
            entry_price=entry,
            stop_loss=sl,
            take_profit=tp,
            c2_bar=_bar(14, 38, 99, 101, 98, 100),
        )

    def test_buy_hits_tp(self):
        """BUY trade — bar high reaches TP → exit at TP, positive P&L."""
        fvg = self._make_fvg("BUY", entry=100.0, sl=98.0, tp=104.0)
        bars = [
            _bar(15, 0, 100, 101, 99.5, 100.5),  # no hit
            _bar(15, 1, 100.5, 104.5, 100, 103),  # high >= 104 → TP
            _bar(15, 2, 103, 105, 102, 104),       # should not reach here
        ]
        trade = _simulate_trade(fvg, bars, "XAUUSD", "2026-01-15")

        assert trade.exit_reason == "TP"
        assert trade.exit_price == pytest.approx(104.0)
        assert trade.pnl == pytest.approx(4.0)  # 104 - 100
        assert trade.bars_in_trade == 2

    def test_buy_hits_sl(self):
        """BUY trade — bar low reaches SL → exit at SL, negative P&L."""
        fvg = self._make_fvg("BUY", entry=100.0, sl=98.0, tp=104.0)
        bars = [
            _bar(15, 0, 100, 101, 99.5, 100.5),  # no hit
            _bar(15, 1, 100, 100.5, 97.5, 98.5),  # low <= 98 → SL
        ]
        trade = _simulate_trade(fvg, bars, "XAUUSD", "2026-01-15")

        assert trade.exit_reason == "SL"
        assert trade.exit_price == pytest.approx(98.0)
        assert trade.pnl == pytest.approx(-2.0)  # 98 - 100
        assert trade.bars_in_trade == 2

    def test_sell_hits_tp(self):
        """SELL trade — bar low reaches TP → exit at TP, positive P&L."""
        fvg = self._make_fvg("SELL", entry=100.0, sl=102.0, tp=96.0)
        bars = [
            _bar(15, 0, 100, 100.5, 99, 99.5),  # no hit
            _bar(15, 1, 99.5, 100, 95.5, 96.5),  # low <= 96 → TP
        ]
        trade = _simulate_trade(fvg, bars, "XAUUSD", "2026-01-15")

        assert trade.exit_reason == "TP"
        assert trade.exit_price == pytest.approx(96.0)
        assert trade.pnl == pytest.approx(4.0)  # 100 - 96
        assert trade.bars_in_trade == 2

    def test_sell_hits_sl(self):
        """SELL trade — bar high reaches SL → exit at SL, negative P&L."""
        fvg = self._make_fvg("SELL", entry=100.0, sl=102.0, tp=96.0)
        bars = [
            _bar(15, 0, 100, 102.5, 99, 101),  # high >= 102 → SL
        ]
        trade = _simulate_trade(fvg, bars, "XAUUSD", "2026-01-15")

        assert trade.exit_reason == "SL"
        assert trade.exit_price == pytest.approx(102.0)
        assert trade.pnl == pytest.approx(-2.0)  # 100 - 102
        assert trade.bars_in_trade == 1

    def test_eod_exit(self):
        """Bar at 20:00 UTC → exit at close, reason EOD."""
        fvg = self._make_fvg("BUY", entry=100.0, sl=98.0, tp=104.0)
        bars = [
            _bar(19, 58, 100, 101, 99.5, 100.5),  # no hit
            _bar(19, 59, 100.5, 101.5, 99.8, 101),  # no hit
            _bar(20, 0, 101, 101.5, 100.5, 101.2),  # EOD (20*60 >= 1200)
        ]
        trade = _simulate_trade(fvg, bars, "XAUUSD", "2026-01-15")

        assert trade.exit_reason == "EOD"
        assert trade.exit_price == pytest.approx(101.2)
        assert trade.pnl == pytest.approx(1.2)  # 101.2 - 100
        assert trade.bars_in_trade == 3


# ---------------------------------------------------------------------------
# _calculate_metrics tests
# ---------------------------------------------------------------------------

class TestCalculateMetrics:
    """Verify aggregate metric calculations."""

    def _make_trade(self, pnl: float, entry: float = 100.0, sl: float = 98.0) -> ORBTrade:
        return ORBTrade(
            date="2026-01-15",
            epic="XAUUSD",
            direction="BUY",
            orb_high=101.0,
            orb_low=99.0,
            fvg_type="bullish",
            entry_price=entry,
            stop_loss=sl,
            take_profit=104.0,
            exit_price=entry + pnl,
            exit_reason="TP" if pnl > 0 else "SL",
            pnl=pnl,
            bars_in_trade=10,
        )

    def test_win_rate(self):
        """1 win + 1 loss → 50% win rate."""
        result = ORBBacktestResult(epic="XAUUSD", period="test")
        result.trades = [self._make_trade(50.0), self._make_trade(-25.0)]

        _calculate_metrics(result, 10_000.0)

        assert result.win_rate == pytest.approx(0.5)

    def test_profit_factor(self):
        """Win=50, loss=-25 → PF = 2.0."""
        result = ORBBacktestResult(epic="XAUUSD", period="test")
        result.trades = [self._make_trade(50.0), self._make_trade(-25.0)]

        _calculate_metrics(result, 10_000.0)

        assert result.profit_factor == pytest.approx(2.0)

    def test_empty_trades(self):
        """No trades → all metrics stay at zero."""
        result = ORBBacktestResult(epic="XAUUSD", period="test")

        _calculate_metrics(result, 10_000.0)

        assert result.win_rate == 0.0
        assert result.profit_factor == 0.0
        assert result.total_pnl == 0.0
        assert result.max_consecutive_losses == 0
        assert result.sharpe_ratio == 0.0
        assert result.max_drawdown_pct == 0.0

    def test_max_consecutive_losses(self):
        """Sequence L, L, W, L, L, L → max consecutive losses = 3."""
        result = ORBBacktestResult(epic="XAUUSD", period="test")
        result.trades = [
            self._make_trade(-10.0),  # L
            self._make_trade(-10.0),  # L
            self._make_trade(30.0),   # W
            self._make_trade(-10.0),  # L
            self._make_trade(-10.0),  # L
            self._make_trade(-10.0),  # L
        ]

        _calculate_metrics(result, 10_000.0)

        assert result.max_consecutive_losses == 3

    def test_total_pnl(self):
        """Total P&L is the sum of all trade P&Ls."""
        result = ORBBacktestResult(epic="XAUUSD", period="test")
        result.trades = [
            self._make_trade(50.0),
            self._make_trade(-25.0),
            self._make_trade(10.0),
        ]

        _calculate_metrics(result, 10_000.0)

        assert result.total_pnl == pytest.approx(35.0)

    def test_sharpe_positive(self):
        """With consistent wins, Sharpe should be positive."""
        result = ORBBacktestResult(epic="XAUUSD", period="test")
        result.trades = [
            self._make_trade(20.0),
            self._make_trade(25.0),
            self._make_trade(15.0),
            self._make_trade(30.0),
        ]

        _calculate_metrics(result, 10_000.0)

        assert result.sharpe_ratio > 0

    def test_max_drawdown(self):
        """Drawdown computed from peak-to-trough equity."""
        result = ORBBacktestResult(epic="XAUUSD", period="test")
        # Start at 10000, +100 → 10100 (peak), -300 → 9800 (trough)
        # DD = (10100 - 9800) / 10100 ≈ 2.97%
        result.trades = [
            self._make_trade(100.0),
            self._make_trade(-300.0),
        ]

        _calculate_metrics(result, 10_000.0)

        expected_dd = 300.0 / 10_100.0
        assert result.max_drawdown_pct == pytest.approx(expected_dd, rel=1e-3)
