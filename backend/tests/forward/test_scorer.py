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
