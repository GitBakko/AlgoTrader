"""Tests that _persist_position_close correctly handles pnl=None (Tier 3)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def loop_with_db():
    from src.trading.paper_loop import PaperTradingLoop

    loop = PaperTradingLoop.__new__(PaperTradingLoop)

    # Build a fake Position repo that returns None (position never persisted)
    repo = MagicMock()
    repo.get_by_deal_id = AsyncMock(return_value=None)

    # create returns the Position it was given (populated with an id)
    async def _create(p):
        p.id = 1
        return p

    repo.create = AsyncMock(side_effect=_create)

    session = AsyncMock()
    session.flush = AsyncMock()
    session.refresh = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    # Patch PositionRepository constructor used inside _persist_position_close
    class _SF:
        async def __aenter__(self_inner):
            return session
        async def __aexit__(self_inner, *a):
            return None

    def _factory():
        return _SF()

    loop._db_session_factory = _factory
    loop._created_positions = []

    return loop, repo, session


@pytest.mark.asyncio
async def test_persist_with_pnl_none_writes_null(loop_with_db, monkeypatch):
    """UNRECONCILED path passes pnl=None → Position.profit_loss is NULL,
    Trade.profit_loss is NULL, commit still succeeds, no round() crash."""
    loop, repo, session = loop_with_db

    captured = {"position": None, "trade": None}

    from src.database import models as _models

    real_position = _models.Position
    real_trade = _models.Trade

    def _capture_position(**kw):
        p = real_position(**kw)
        p.id = 42
        captured["position"] = p
        return p

    def _capture_trade(**kw):
        t = real_trade(**kw)
        captured["trade"] = t
        return t

    monkeypatch.setattr("src.database.models.Position", _capture_position)
    monkeypatch.setattr("src.database.models.Trade", _capture_trade)

    # Monkeypatch the repo class used inside the method
    from src.database import repositories as _repos

    monkeypatch.setattr(_repos, "PositionRepository", lambda s: repo)

    await loop._persist_position_close(
        deal_id="pending-1",
        epic="WTIUSD",
        direction="BUY",
        size=10.0,
        entry_price=84.50,
        exit_price=84.50,  # placeholder per Task 7
        pnl=None,  # UNRECONCILED
        close_reason="UNRECONCILED",
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    # Position was created (since repo.get_by_deal_id returned None)
    repo.create.assert_awaited_once()
    session.commit.assert_awaited_once()
    session.add.assert_called_once()  # Trade

    assert captured["position"] is not None
    assert captured["position"].profit_loss is None
    assert captured["position"].close_reason == "UNRECONCILED"
    assert captured["position"].status == "CLOSED"

    assert captured["trade"] is not None
    assert captured["trade"].profit_loss is None
    assert captured["trade"].trade_type == "CLOSE"


@pytest.mark.asyncio
async def test_persist_with_pnl_float_writes_decimal(loop_with_db, monkeypatch):
    """Sanity check: non-None pnl still round-trips to Decimal properly."""
    loop, repo, session = loop_with_db

    from src.database import models as _models

    captured = {}

    real_position = _models.Position

    def _capture(**kw):
        p = real_position(**kw)
        p.id = 7
        captured["position"] = p
        return p

    monkeypatch.setattr("src.database.models.Position", _capture)

    from src.database import repositories as _repos

    monkeypatch.setattr(_repos, "PositionRepository", lambda s: repo)

    await loop._persist_position_close(
        deal_id="happy-1",
        epic="WTIUSD",
        direction="BUY",
        size=10.0,
        entry_price=84.50,
        exit_price=85.60,
        pnl=246.8612345,  # deliberately many decimals
        close_reason="TP",
        opened_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )

    assert captured["position"].profit_loss == Decimal("246.86")
