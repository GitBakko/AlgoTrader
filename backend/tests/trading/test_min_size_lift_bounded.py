"""Regression: lifting size to the broker minimum must re-check the
exposure cap (audit M1.5a). Approved 0.2 units with broker min 1.0 was
executed at 5x the risk-approved size, silently."""

from src.trading.paper_loop import PaperTradingLoop


class TestBoundedMinSizeLift:
    def test_lift_blocked_when_min_exceeds_cap(self):
        final, ok = PaperTradingLoop._bounded_min_size_lift(
            approved_size=0.2, min_deal_size=1.0, max_size_by_exposure=0.8
        )
        assert ok is False

    def test_lift_allowed_within_cap(self):
        final, ok = PaperTradingLoop._bounded_min_size_lift(
            approved_size=0.2, min_deal_size=1.0, max_size_by_exposure=3.0
        )
        assert ok is True and final == 1.0

    def test_no_lift_needed_passes_through(self):
        final, ok = PaperTradingLoop._bounded_min_size_lift(
            approved_size=2.0, min_deal_size=1.0, max_size_by_exposure=3.0
        )
        assert ok is True and final == 2.0

    def test_unknown_cap_falls_back_permissive_with_flag(self):
        # When the audit payload lacks max_size_by_exposure (older risk
        # result), behave like HEAD (lift) but signal it via ok=True —
        # see implementation contract.
        final, ok = PaperTradingLoop._bounded_min_size_lift(
            approved_size=0.2, min_deal_size=1.0, max_size_by_exposure=None
        )
        assert ok is True and final == 1.0

    def test_min_exactly_at_cap_allows_lift(self):
        # Boundary: the guard is strict (>), so a broker minimum that lands
        # EXACTLY on the exposure cap is still liftable.
        final, ok = PaperTradingLoop._bounded_min_size_lift(
            approved_size=0.2, min_deal_size=1.0, max_size_by_exposure=1.0
        )
        assert ok is True and final == 1.0

    def test_zero_cap_blocks_lift(self):
        # cap=0.0 is a real value (zero/negative equity sentinel from the
        # risk audit), NOT "unknown" — it must block, not fall back.
        final, ok = PaperTradingLoop._bounded_min_size_lift(
            approved_size=0.2, min_deal_size=1.0, max_size_by_exposure=0.0
        )
        assert ok is False
