import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pandas as pd
from datetime import datetime, timezone


def _frame(rows):
    """rows: list[(iso_utc, volume)] -> DataFrame[Volume] with UTC DatetimeIndex."""
    idx = pd.to_datetime([r[0] for r in rows], utc=True)
    return pd.DataFrame({"Volume": [r[1] for r in rows]}, index=idx)


def _fake_fetch(data):
    def _f(symbols, days):
        return {s: data[s] for s in symbols if s in data}
    return _f


def test_rvol_high_today_is_eligible():
    from forward.screener import RvolScreener
    # baseline days 06-01,06-02 each 100 early vol; today 06-03 has 300 -> rvol 3.0
    df = _frame([
        ("2026-06-01T13:30:00Z", 100), ("2026-06-02T13:30:00Z", 100),
        ("2026-06-03T13:30:00Z", 300),
    ])
    sc = RvolScreener(fetch_5m=_fake_fetch({"AAPL": df}), rvol_min=1.5, top_k=5,
                      or_window_min=30, baseline_days=20)
    now = datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc)
    out = sc.select(["AAPL"], now)
    assert round(out["rvol"]["AAPL"], 2) == 3.0
    assert "AAPL" in out["eligible"]


def test_rvol_below_threshold_not_eligible():
    from forward.screener import RvolScreener
    df = _frame([
        ("2026-06-01T13:30:00Z", 100), ("2026-06-02T13:30:00Z", 100),
        ("2026-06-03T13:30:00Z", 110),   # rvol 1.1 < 1.5
    ])
    sc = RvolScreener(fetch_5m=_fake_fetch({"AAPL": df}), rvol_min=1.5)
    out = sc.select(["AAPL"], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert out["eligible"] == set()


def test_top_k_caps_eligible_count():
    from forward.screener import RvolScreener
    data = {}
    for i, sym in enumerate(["A", "B", "C"]):
        today = 200 + i * 100            # A=200,B=300,C=400 -> rvol 2,3,4
        data[sym] = _frame([
            ("2026-06-01T13:30:00Z", 100), ("2026-06-02T13:30:00Z", 100),
            ("2026-06-03T13:30:00Z", today),
        ])
    sc = RvolScreener(fetch_5m=_fake_fetch(data), rvol_min=1.5, top_k=2)
    out = sc.select(["A", "B", "C"], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert out["eligible"] == {"C", "B"}        # top-2 by rvol


def test_only_regular_session_window_counts():
    from forward.screener import RvolScreener
    # pre-market 13:00 huge vol must be ignored; only 13:30/13:35 in [13:30,14:00) count
    df = _frame([
        ("2026-06-02T13:00:00Z", 9999),  # pre-market, ignored
        ("2026-06-02T13:30:00Z", 50), ("2026-06-02T13:35:00Z", 50),  # baseline early=100
        ("2026-06-03T13:00:00Z", 9999),  # pre-market, ignored
        ("2026-06-03T13:30:00Z", 150), ("2026-06-03T13:35:00Z", 150),  # today early=300 -> rvol 3
    ])
    sc = RvolScreener(fetch_5m=_fake_fetch({"AAPL": df}), rvol_min=1.5, or_window_min=30)
    out = sc.select(["AAPL"], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert round(out["rvol"]["AAPL"], 2) == 3.0


def test_empty_or_missing_feed_skips_symbol():
    from forward.screener import RvolScreener
    sc = RvolScreener(fetch_5m=_fake_fetch({}), rvol_min=1.5)   # no data for AAPL
    out = sc.select(["AAPL"], datetime(2026, 6, 3, 14, 0, tzinfo=timezone.utc))
    assert out["eligible"] == set() and "AAPL" not in out["rvol"]
