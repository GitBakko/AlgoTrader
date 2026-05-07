"""Strategy-test conftest.

Production ``.env`` ships ``MR_PRIMARY_ENABLED=true`` and (post 2026-04
revamp) often ``ML_PRIMARY_ENABLED=true``. Strategy unit tests that
exercise the legacy ``_process_default`` (XGBoost direct → SignalDirection)
path break under those flags because the orchestrator routes to the
MR-Primary or ML-Primary chain instead, which (with mocked / default
``market_data``) returns HOLD.

This autouse fixture forces both primary flags OFF for every test in
``tests/strategy/`` so the legacy path is exercised unless a test
explicitly opts back in.

Tests that DO want MR-Primary or ML-Primary must override at the
test/class level (e.g. ``StrategyManager(ml_primary_enabled=True)`` or
their own ``get_settings`` patch).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.utils.config import get_settings


@pytest.fixture(autouse=True)
def _disable_primaries_by_default(monkeypatch):
    """Force MR/ML primary flags OFF for every strategy test by default.

    Patches ``get_settings()`` at the module level used by both
    ``strategy_manager`` and ``mean_reversion_strategy`` so the legacy
    ``_process_default`` path is the one exercised. Tests that need the
    primary chains active will set ``ml_primary_enabled=True`` on the
    StrategyManager constructor (kwarg) and/or override this fixture.
    """
    real = get_settings()

    class _Stub:
        def __getattr__(self, name):
            # Disable the two routing flags; everything else falls through
            # to the real settings instance.
            if name == "mr_primary_enabled":
                return False
            if name == "ml_primary_enabled":
                return False
            return getattr(real, name)

    stub = _Stub()
    with patch("src.strategy.strategy_manager.get_settings", return_value=stub), \
         patch("src.strategy.mean_reversion_strategy.get_settings", return_value=stub):
        yield
