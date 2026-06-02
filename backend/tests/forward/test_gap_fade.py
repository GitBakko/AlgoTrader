import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

from datetime import datetime, timezone
from src.broker.models import Direction


def _ctx(prev, open_, cur, **kw):
    from forward.strategy import MarketContext
    now = kw.get("now", datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc))
    sc = kw.get("session_close", datetime(2026, 6, 2, 20, 45, tzinfo=timezone.utc))
    return MarketContext("AAPL", prev, open_, cur, now, sc, atr=kw.get("atr"))


def test_gap_up_fades_short_stop_above():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015)
    sig = s.should_enter(_ctx(100.0, 103.0, 103.0))   # +3% gap up
    assert sig is not None and sig.direction == Direction.SELL
    assert sig.stop_level > 103.0                      # stop above entry for a short

def test_gap_down_fades_long_stop_below():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015)
    sig = s.should_enter(_ctx(100.0, 97.0, 97.0))      # -3% gap down
    assert sig is not None and sig.direction == Direction.BUY
    assert sig.stop_level < 97.0

def test_small_gap_no_trade():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01)
    assert s.should_enter(_ctx(100.0, 100.5, 100.5)) is None   # +0.5% < 1%

def test_atr_stop_used_when_present():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_atr_mult=2.0)
    sig = s.should_enter(_ctx(100.0, 103.0, 103.0, atr=1.0))
    assert sig.stop_level == 105.0                     # open + 2*ATR
