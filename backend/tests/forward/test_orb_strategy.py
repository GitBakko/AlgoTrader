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


def _octx(or_hi, or_lo, cur, **kw):
    from forward.strategy import MarketContext
    now = kw.get("now", datetime(2026, 6, 3, 14, 30, tzinfo=timezone.utc))
    sc = kw.get("session_close", datetime(2026, 6, 3, 20, 45, tzinfo=timezone.utc))
    return MarketContext("AAPL", 100.0, 101.0, cur, now, sc,
                         atr=kw.get("atr"), or_high=or_hi, or_low=or_lo,
                         rvol=kw.get("rvol", 2.0))


def test_orb_break_up_goes_long_stop_below():
    from forward.strategy import ORBStrategy
    from src.broker.models import Direction
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    sig = s.should_enter(_octx(102.0, 100.0, 102.5))   # price above OR high
    assert sig is not None and sig.direction == Direction.BUY
    assert sig.stop_level < 102.5                       # stop below entry

def test_orb_break_down_goes_short_stop_above():
    from forward.strategy import ORBStrategy
    from src.broker.models import Direction
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    sig = s.should_enter(_octx(102.0, 100.0, 99.5))     # price below OR low
    assert sig is not None and sig.direction == Direction.SELL
    assert sig.stop_level > 99.5                         # stop above entry

def test_orb_inside_range_no_trade():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    assert s.should_enter(_octx(102.0, 100.0, 101.0)) is None

def test_orb_no_opening_range_no_trade():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"])
    assert s.should_enter(_octx(None, None, 105.0)) is None

def test_orb_below_rvol_threshold_no_trade():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5)
    assert s.should_enter(_octx(102.0, 100.0, 102.5, rvol=1.0)) is None

def test_orb_buffer_blocks_marginal_break():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5, breakout_buffer=0.01)  # need +1% beyond
    assert s.should_enter(_octx(102.0, 100.0, 102.5)) is None            # +0.49% < 1%
    assert s.should_enter(_octx(102.0, 100.0, 103.1)) is not None        # +1.08% > 1%

def test_orb_atr_floor_widens_tight_range_stop():
    from forward.strategy import ORBStrategy
    s = ORBStrategy(epics=["AAPL"], rvol_min=1.5, stop_atr_mult=1.0)
    # tight range (or_low 102.4 vs price 102.5) but atr=2.0 -> stop floored to 100.5
    sig = s.should_enter(_octx(102.45, 102.4, 102.5, atr=2.0))
    assert sig.stop_level == 100.5                       # min(or_low, price - atr) = 102.5-2.0

def test_orb_exit_eod_only():
    from forward.strategy import ORBStrategy, OpenPosition
    from src.broker.models import Direction
    s = ORBStrategy(epics=["AAPL"])
    pos = OpenPosition("AAPL", Direction.BUY, 102.5, 1.0, 100.0, 0.0, 102.5,
                       datetime(2026, 6, 3, 14, 30, tzinfo=timezone.utc), "D1")
    early = _octx(102.0, 100.0, 110.0, now=datetime(2026, 6, 3, 15, 0, tzinfo=timezone.utc))
    late = _octx(102.0, 100.0, 110.0, now=datetime(2026, 6, 3, 21, 0, tzinfo=timezone.utc))
    assert s.exit_rule(pos, early) is False              # mid-session: hold (SL is broker-side)
    assert s.exit_rule(pos, late) is True                # past session_close: flatten
