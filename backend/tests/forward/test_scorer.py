import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))


def _rows(n, pnl_each, start="2026-01-01"):
    import pandas as pd
    days = pd.date_range(start, periods=n, freq="B")
    return [{"size": 1.0, "entry": 200.0, "net_pnl": pnl_each,
             "closed_at": d.isoformat()} for d in days]


def test_insufficient_below_min_trades():
    from forward.scorer import score, MIN_TRADES
    out = score(_rows(10, 1.0))
    assert "INSUFFICIENT" in out["verdict"]
    assert MIN_TRADES == 100


def test_kill_when_zero_edge():
    from forward.scorer import score
    rows = _rows(150, 1.0)
    for i in range(0, len(rows), 2):
        rows[i]["net_pnl"] = -1.0
    out = score(rows)
    assert out["n_trades"] == 150
    assert "KILL" in out["verdict"]


def test_score_excludes_pending_reconcile_rows():
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
    from forward.scorer import score
    # 3 real reconciled trades + 2 PENDING_RECONCILE $0 rows; the $0s must NOT enter the stats
    rows = []
    for i in range(3):
        rows.append({"closed_at": f"2026-06-0{i+1}T16:00:00+00:00", "size": 1.0,
                     "entry": 100.0, "net_pnl": 5.0, "close_reason": "BROKER_TRADE"})
    for i in range(2):
        rows.append({"closed_at": f"2026-06-0{i+4}T16:00:00+00:00", "size": 1.0,
                     "entry": 100.0, "net_pnl": 0.0, "close_reason": "PENDING_RECONCILE"})
    out = score(rows)
    assert out["n_trades"] == 3   # only the reconciled rows counted


def test_daily_series_excludes_weekends():
    # Fri + next Mon: calendar bins would be 4 (Fri,Sat,Sun,Mon) — business days = 2.
    # Calendar padding deflated Sharpe by ~sqrt(252/365).
    from forward.scorer import score
    rows = [
        {"closed_at": "2026-06-05T16:00:00+00:00", "size": 1.0, "entry": 100.0, "net_pnl": 1.0},
        {"closed_at": "2026-06-08T16:00:00+00:00", "size": 1.0, "entry": 100.0, "net_pnl": 2.0},
    ]
    out = score(rows)
    assert out["n_days"] == 2


def test_weekend_close_rolls_forward_no_pnl_lost():
    # A Saturday-stamped close (future crypto hypotheses) must roll onto Monday,
    # not silently drop out of the series.
    import sys, pathlib
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))
    import pandas as pd
    from forward.scorer import _daily_returns
    df = pd.DataFrame([
        {"closed_at": "2026-06-06T10:00:00+00:00", "size": 1.0, "entry": 100.0, "net_pnl": 3.0},  # Sat
        {"closed_at": "2026-06-08T16:00:00+00:00", "size": 1.0, "entry": 100.0, "net_pnl": 1.0},  # Mon
    ])
    df["closed_at"] = pd.to_datetime(df["closed_at"], utc=True)
    df["ret"] = df["net_pnl"] / (df["size"] * df["entry"])
    daily = _daily_returns(df)
    assert len(daily) == 1                       # everything lands on Monday
    assert abs(daily.iloc[0] - 0.04) < 1e-12     # 3/100 + 1/100 — nothing lost


def test_ci_gate_not_bypassed_when_nan():
    # >=100 trades crammed into too few days for ANY bootstrap CI: the old code
    # compared NaN bounds (False) and fell through to PROMOTE un-vetted.
    from forward.scorer import score
    import pandas as pd
    days = pd.bdate_range("2026-06-01", periods=8)
    rows = []
    for i in range(104):                          # 13 trades/day x 8 business days
        d = days[i % 8]
        rows.append({"closed_at": (d + pd.Timedelta(hours=16)).isoformat() + "+00:00",
                     "size": 1.0, "entry": 200.0, "net_pnl": 1.0})
    out = score(rows)
    assert "INSUFFICIENT" in out["verdict"]
    assert "CI unavailable" in out["verdict"]
    assert "PROMOTE" not in out["verdict"]


def test_ci_computable_at_realistic_gate():
    # The realistic gate shape: ~120 trades over 60 business days. Adaptive block
    # must yield a finite CI (old fixed block=21 needed >=105 days -> NaN).
    from forward.scorer import score
    import math
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(7)
    days = pd.bdate_range("2026-06-01", periods=60)
    rows = []
    for i in range(120):
        d = days[i % 60]
        rows.append({"closed_at": (d + pd.Timedelta(hours=16)).isoformat() + "+00:00",
                     "size": 1.0, "entry": 200.0, "net_pnl": float(rng.normal(0.6, 2.0))})
    out = score(rows)
    lo, hi = out["ci90"]
    assert math.isfinite(lo) and math.isfinite(hi)
    assert "CI unavailable" not in out["verdict"]
