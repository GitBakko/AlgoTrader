import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

from datetime import datetime, timezone


def test_market_context_has_orb_fields_defaulting_none():
    from forward.strategy import MarketContext
    now = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    sc = datetime(2026, 6, 3, 20, 45, tzinfo=timezone.utc)
    ctx = MarketContext("AAPL", 100.0, 101.0, 101.5, now, sc)
    assert ctx.or_high is None and ctx.or_low is None and ctx.rvol is None
    ctx2 = MarketContext("AAPL", 100.0, 101.0, 101.5, now, sc,
                         atr=1.0, or_high=102.0, or_low=100.5, rvol=2.3)
    assert ctx2.or_high == 102.0 and ctx2.or_low == 100.5 and ctx2.rvol == 2.3


def test_gap_fade_does_not_need_opening_range():
    from forward.strategy import GapFadeStrategy
    assert GapFadeStrategy(epics=["AAPL"]).needs_opening_range is False
