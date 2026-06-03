import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import pytest


@pytest.mark.network
def test_yfinance_default_fetch_returns_real_volume():
    """Smoke: real Yahoo 5-min bars carry real exchange volume (not CFD tick-count).
    Skips (never fails) when Yahoo is unreachable/rate-limited so CI stays green offline."""
    from forward.screener import _default_fetch_5m
    try:
        out = _default_fetch_5m(["AAPL", "MSFT"], 5)
    except Exception as e:  # noqa: BLE001 — network flake must skip, not fail
        pytest.skip(f"yfinance unreachable: {e}")
    if not out or "AAPL" not in out or out["AAPL"].empty:
        pytest.skip("yfinance returned no AAPL data (offline/rate-limited)")
    df = out["AAPL"]
    assert "Volume" in df.columns
    # real exchange volume is large (>1000/bar typical), not CFD tick-count single digits
    assert df["Volume"].max() > 1000
