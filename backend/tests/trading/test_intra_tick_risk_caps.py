"""Regression: one iteration must not open past max_total_open_positions.

On HEAD the same tick-start position list is passed to every epic, so with
9 open and a cap of 10, every signal in a multi-signal tick sees 9<10 and
is approved (audit M1.2 / finding H3).
"""

from src.trading.paper_loop import PaperTradingLoop


class TestIntraTickRiskCaps:
    def test_register_intra_tick_open_appends_stub_in_place(self):
        loop = PaperTradingLoop.__new__(PaperTradingLoop)
        shared: list[dict] = [{"epic": "XAUUSD", "size": 1.0, "level": 2000.0, "direction": "BUY"}]
        same_ref = shared
        loop._register_intra_tick_open(
            shared, epic="NVDA", direction="BUY", size=2.0, entry_price=500.0
        )
        assert shared is same_ref
        assert len(shared) == 2
        stub = shared[-1]
        assert stub["epic"] == "NVDA"
        assert stub["direction"] == "BUY"
        assert stub["size"] == 2.0
        assert stub["level"] == 500.0

    def test_risk_manager_counts_stub_against_exposure(self):
        """The stub must be consumable by the exposure-notional helper."""
        from src.risk.risk_manager import _position_notional_account_ccy

        stub_holder: list[dict] = []
        PaperTradingLoop._register_intra_tick_open(
            stub_holder, epic="NVDA", direction="BUY", size=2.0, entry_price=500.0
        )
        assert _position_notional_account_ccy(stub_holder[0]) == 1000.0
