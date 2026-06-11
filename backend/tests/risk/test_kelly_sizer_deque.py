"""Regression: KellySizer must accept a deque trade_history (audit M1.1).

paper_loop keeps self._trade_history as deque(maxlen=200) and passes it raw
to RiskManager -> KellySizer. collections.deque does not support slicing:
on HEAD the 30th in-session trade arms a TypeError in compute_stats and
every subsequent check_trade fails for ALL epics until restart.
"""

from collections import deque

from src.risk.kelly_sizer import AdaptiveKellySizer


def _mk_history(n: int) -> list[dict]:
    # Alternate wins/losses so stats are well-defined
    return [{"pnl": 10.0 if i % 2 == 0 else -5.0} for i in range(n)]


class TestKellyDequeSupport:
    def test_compute_stats_accepts_deque(self):
        sizer = AdaptiveKellySizer(min_trades=30, lookback_trades=100)
        history = deque(_mk_history(35), maxlen=200)
        stats = sizer.compute_stats(history)
        assert stats is not None
        assert 0.0 < stats.win_rate < 1.0

    def test_compute_stats_deque_below_min_returns_none(self):
        sizer = AdaptiveKellySizer(min_trades=30)
        assert sizer.compute_stats(deque(_mk_history(10))) is None


class TestSeedTradeHistory:
    def test_seed_trade_history_keeps_maxlen_contract(self):
        """main.py recovery injection must preserve the 200-trade bound."""
        from src.trading.paper_loop import PaperTradingLoop

        loop = PaperTradingLoop.__new__(PaperTradingLoop)
        loop.seed_trade_history(_mk_history(500))
        assert len(loop._trade_history) == 200
        assert isinstance(loop._trade_history, deque)
        # Most recent entries are kept (history list is chronological)
        assert loop._trade_history[-1] == _mk_history(500)[-1]
