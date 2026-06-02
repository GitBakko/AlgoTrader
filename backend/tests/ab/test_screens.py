import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts" / "ab"))

import numpy as np
import pandas as pd


def test_overnight_net_leak_safe_and_financing():
    from test_overnight import overnight_net
    idx = pd.date_range("2024-01-01", periods=3, freq="D")
    close = pd.Series([100.0, 110.0, 121.0], index=idx)
    open_ = pd.Series([100.0, 105.0, 110.0], index=idx)
    out = overnight_net(open_, close, 0.001)
    assert pd.isna(out.iloc[0])
    assert abs(out.iloc[1] - (105/100 - 1 - 0.001)) < 1e-9
    assert abs(out.iloc[2] - (110/110 - 1 - 0.001)) < 1e-9


def _uptrend_with_dip() -> pd.Series:
    idx = pd.date_range("2022-01-01", periods=320, freq="D")
    base = 100.0 * (1.0005 ** np.arange(320))
    base[250:255] *= 0.93
    return pd.Series(base, index=idx)


def test_rsi_extremes():
    from test_rsi2 import rsi
    up = pd.Series(np.arange(1, 60, dtype=float))
    dn = pd.Series(np.arange(60, 1, -1, dtype=float))
    assert rsi(up, 2).iloc[-1] > 95
    assert rsi(dn, 2).iloc[-1] < 5


def test_rsi2_position_no_lookahead():
    from test_rsi2 import rsi2_position
    close = _uptrend_with_dip()
    full = rsi2_position(close)
    k = 260
    trunc = rsi2_position(close.iloc[:k])
    assert np.array_equal(full.iloc[:k].to_numpy(), trunc.to_numpy())
    assert full.iloc[:200].sum() == 0.0
    assert full.iloc[250:].sum() > 0.0
