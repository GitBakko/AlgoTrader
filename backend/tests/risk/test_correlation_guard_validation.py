"""Phase 1 expansion (2026-05-23): CorrelationGuard.update_matrix
must reject matrices containing NaN/Inf entries. A constant-price
epic in the basket produces NaN in `np.corrcoef`; without rejection
the dynamic exposure check propagates a NaN multiplier into the
position-sizing chain (silent zero-size trade)."""

import numpy as np

from src.risk.correlation_guard import CorrelationGuard


def _baseline_matrix() -> tuple[list[str], np.ndarray]:
    epics = ["BTCUSD", "ETHUSD", "XAUUSD"]
    matrix = np.array(
        [
            [1.0, 0.7, 0.2],
            [0.7, 1.0, 0.3],
            [0.2, 0.3, 1.0],
        ],
        dtype=float,
    )
    return epics, matrix


def test_update_matrix_accepts_valid() -> None:
    guard = CorrelationGuard()
    epics, mat = _baseline_matrix()
    guard.update_matrix(epics, mat)
    assert guard.get_dynamic_correlation("BTCUSD", "ETHUSD") == 0.7


def test_update_matrix_rejects_nan() -> None:
    guard = CorrelationGuard()
    epics, mat = _baseline_matrix()
    guard.update_matrix(epics, mat)  # prime with valid matrix
    bad = mat.copy()
    bad[0, 1] = np.nan
    bad[1, 0] = np.nan
    guard.update_matrix(epics, bad)
    # Prior matrix preserved
    assert guard.get_dynamic_correlation("BTCUSD", "ETHUSD") == 0.7


def test_update_matrix_rejects_inf() -> None:
    guard = CorrelationGuard()
    epics, mat = _baseline_matrix()
    guard.update_matrix(epics, mat)
    bad = mat.copy()
    bad[2, 0] = np.inf
    bad[0, 2] = np.inf
    guard.update_matrix(epics, bad)
    assert guard.get_dynamic_correlation("BTCUSD", "XAUUSD") == 0.2


def test_update_matrix_first_call_with_nan_leaves_matrix_unset() -> None:
    """If the very first update has NaN, the matrix stays None and
    `get_dynamic_correlation` returns None (static fallback path)."""
    guard = CorrelationGuard()
    epics, mat = _baseline_matrix()
    mat[1, 2] = np.nan
    mat[2, 1] = np.nan
    guard.update_matrix(epics, mat)
    assert guard.get_dynamic_correlation("ETHUSD", "XAUUSD") is None
