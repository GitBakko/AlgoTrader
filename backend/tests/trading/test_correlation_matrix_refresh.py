"""Phase 1 expansion (2026-05-23): paper_loop._refresh_correlation_matrix
populates CorrelationGuard's dynamic matrix.

Test surface:
- Gated by DYNAMIC_CORRELATION_ENABLED flag (independent of regime gate).
- Uses full self.epics (no [:10] truncation, the old regime path's cap).
- Skips when fewer than DYNAMIC_CORRELATION_BOOTSTRAP_MIN_ASSETS epics
  have >=100 bars of data.
- Throttles to one refresh per 30 min unless force=True.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import polars as pl
import pytest


def _make_loop_stub(epics: list[str], candle_count: int = 200):
    """Build a minimal stub mimicking PaperTradingLoop fields used by
    _refresh_correlation_matrix.

    Returns a SimpleNamespace-like object with the attributes the method
    reads. The point is to test the method in isolation from the rest of
    the loop machinery.
    """
    from types import SimpleNamespace

    # Synthetic candles: linear trend per epic so np.corrcoef is well-defined
    def _candles(seed: int) -> pl.DataFrame:
        rng = np.random.default_rng(seed)
        close = 100.0 + np.cumsum(rng.normal(0, 1, candle_count))
        return pl.DataFrame({"close": close})

    candles_map = {epic: _candles(seed=i) for i, epic in enumerate(epics)}
    data_access = MagicMock()
    data_access.get_candles = lambda epic, *_a, **_kw: candles_map.get(epic)

    correlation_guard = MagicMock()
    risk_manager = SimpleNamespace(correlation_guard=correlation_guard)

    loop = SimpleNamespace(
        epics=epics,
        data_access=data_access,
        risk_manager=risk_manager,
        _candle_resolution="4h",
        _correlation_matrix_ts=0.0,
    )
    return loop, correlation_guard


@pytest.mark.asyncio
async def test_matrix_refresh_uses_full_basket() -> None:
    """No [:10] cap — all 20 epics with data feed the matrix."""
    from src.trading.paper_loop import PaperTradingLoop

    epics = [f"EPIC{i:02d}" for i in range(20)]
    loop, guard = _make_loop_stub(epics)

    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = True
        mock_settings.return_value.dynamic_correlation_bootstrap_min_assets = 5
        await PaperTradingLoop._refresh_correlation_matrix(loop)

    assert guard.update_matrix.called
    epics_arg, matrix_arg = guard.update_matrix.call_args[0]
    assert len(epics_arg) == 20  # full basket, not [:10]
    assert matrix_arg.shape == (20, 20)


@pytest.mark.asyncio
async def test_matrix_refresh_skips_when_flag_disabled() -> None:
    from src.trading.paper_loop import PaperTradingLoop

    loop, guard = _make_loop_stub(["BTCUSD", "ETHUSD", "XAUUSD"])
    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = False
        await PaperTradingLoop._refresh_correlation_matrix(loop)

    assert not guard.update_matrix.called


@pytest.mark.asyncio
async def test_matrix_refresh_skips_below_min_assets() -> None:
    """Only 3 epics with data, floor is 5 → no update."""
    from src.trading.paper_loop import PaperTradingLoop

    loop, guard = _make_loop_stub(["BTCUSD", "ETHUSD", "XAUUSD"])
    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = True
        mock_settings.return_value.dynamic_correlation_bootstrap_min_assets = 5
        await PaperTradingLoop._refresh_correlation_matrix(loop)

    assert not guard.update_matrix.called


@pytest.mark.asyncio
async def test_matrix_refresh_throttle_30_min() -> None:
    """Second consecutive call within 30 min must skip the update."""
    from src.trading.paper_loop import PaperTradingLoop

    epics = [f"EPIC{i:02d}" for i in range(6)]
    loop, guard = _make_loop_stub(epics)

    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = True
        mock_settings.return_value.dynamic_correlation_bootstrap_min_assets = 5

        await PaperTradingLoop._refresh_correlation_matrix(loop)
        first_calls = guard.update_matrix.call_count

        # Immediate second call — must throttle
        await PaperTradingLoop._refresh_correlation_matrix(loop)
        assert guard.update_matrix.call_count == first_calls


@pytest.mark.asyncio
async def test_matrix_refresh_force_bypasses_throttle() -> None:
    """force=True bypasses the 30-min throttle (used for startup bootstrap)."""
    from src.trading.paper_loop import PaperTradingLoop

    epics = [f"EPIC{i:02d}" for i in range(6)]
    loop, guard = _make_loop_stub(epics)

    with patch("src.trading.paper_loop.get_settings") as mock_settings:
        mock_settings.return_value.dynamic_correlation_enabled = True
        mock_settings.return_value.dynamic_correlation_bootstrap_min_assets = 5

        await PaperTradingLoop._refresh_correlation_matrix(loop)
        await PaperTradingLoop._refresh_correlation_matrix(loop, force=True)

        assert guard.update_matrix.call_count == 2
