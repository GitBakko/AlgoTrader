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
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015, min_rr=0.0)
    sig = s.should_enter(_ctx(100.0, 103.0, 103.0))   # +3% gap up
    assert sig is not None and sig.direction == Direction.SELL
    assert sig.stop_level > 103.0                      # stop above entry for a short

def test_gap_down_fades_long_stop_below():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015, min_rr=0.0)
    sig = s.should_enter(_ctx(100.0, 97.0, 97.0))      # -3% gap down
    assert sig is not None and sig.direction == Direction.BUY
    assert sig.stop_level < 97.0

def test_small_gap_no_trade():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01)
    assert s.should_enter(_ctx(100.0, 100.5, 100.5)) is None   # +0.5% < 1%

def test_atr_stop_used_when_present():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_atr_mult=2.0, min_rr=0.0)
    sig = s.should_enter(_ctx(100.0, 103.0, 103.0, atr=1.0))
    assert sig.stop_level == 105.0                     # open + 2*ATR


def _pos(direction, prev, open_, entry):
    from forward.strategy import OpenPosition
    from datetime import datetime, timezone
    return OpenPosition("AAPL", direction, entry, 1.0, 0.0, prev, open_,
                        datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc), "D1")


def test_short_exits_at_50pct_fill():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], fill_fraction=0.5)
    pos = _pos(Direction.SELL, 100.0, 104.0, 104.0)   # gap +4 -> target 102.0
    assert s.exit_rule(pos, _ctx(100.0, 104.0, 102.0)) is True    # reached
    assert s.exit_rule(pos, _ctx(100.0, 104.0, 103.0)) is False   # not yet


def test_long_exits_at_50pct_fill():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], fill_fraction=0.5)
    pos = _pos(Direction.BUY, 100.0, 96.0, 96.0)      # gap -4 -> target 98.0
    assert s.exit_rule(pos, _ctx(100.0, 96.0, 98.0)) is True
    assert s.exit_rule(pos, _ctx(100.0, 96.0, 97.0)) is False


def test_eod_flatten():
    from forward.strategy import GapFadeStrategy
    from datetime import datetime, timezone
    s = GapFadeStrategy(epics=["AAPL"])
    pos = _pos(Direction.SELL, 100.0, 104.0, 104.0)
    late = datetime(2026, 6, 2, 21, 0, tzinfo=timezone.utc)
    sc = datetime(2026, 6, 2, 20, 45, tzinfo=timezone.utc)
    assert s.exit_rule(pos, _ctx(100.0, 104.0, 104.0, now=late, session_close=sc)) is True


def test_nonpositive_prev_close_no_trade():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01)
    assert s.should_enter(_ctx(0.0, 103.0, 103.0)) is None


# ---------------------------------------------------------------------------
# R:R floor — refuse entries whose 50%-fill target is closer than the stop
# (target = fill_fraction * gap; stop = _stop_distance). A +1.5% gap fades to a
# 0.75% target but the stop is ~1.5% -> R:R ~0.5 -> -EV by construction. Default
# min_rr=1.0 blocks these; the direction/stop tests above pass min_rr=0.0 to
# isolate their concern from this gate.
# ---------------------------------------------------------------------------

def test_rr_gate_default_is_one():
    from forward.strategy import GapFadeStrategy
    assert GapFadeStrategy(epics=["AAPL"]).min_rr == 1.0


def test_rr_gate_rejects_target_below_stop():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015,
                        fill_fraction=0.5, min_rr=1.0)
    # +1.5% gap clears the threshold, but target 0.75% < stop ~1.52% -> R:R ~0.49 -> reject
    assert s.should_enter(_ctx(100.0, 101.5, 101.5)) is None


def test_rr_gate_allows_target_above_stop():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015,
                        fill_fraction=0.5, min_rr=1.0)
    # +5% gap -> target 2.5% > stop ~1.58% -> R:R ~1.59 -> allow
    sig = s.should_enter(_ctx(100.0, 105.0, 105.0))
    assert sig is not None and sig.direction == Direction.SELL


def test_rr_gate_disabled_allows_low_rr():
    from forward.strategy import GapFadeStrategy
    s = GapFadeStrategy(epics=["AAPL"], gap_threshold=0.01, stop_pct_fallback=0.015,
                        fill_fraction=0.5, min_rr=0.0)
    # gate off -> the same low-R:R +1.5% gap is allowed (escape hatch for tests/tuning)
    assert s.should_enter(_ctx(100.0, 101.5, 101.5)) is not None


def test_open_position_field_order():
    from forward.strategy import OpenPosition
    from datetime import datetime, timezone
    p = OpenPosition("AAPL", Direction.SELL, 103.0, 1.5, 105.0, 100.0, 103.0,
                     datetime(2026, 6, 2, 14, 0, tzinfo=timezone.utc), "D1")
    assert p.entry == 103.0 and p.size == 1.5 and p.stop_level == 105.0
    assert p.prev_close == 100.0 and p.today_open == 103.0 and p.deal_id == "D1"
