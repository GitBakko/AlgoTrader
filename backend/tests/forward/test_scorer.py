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
