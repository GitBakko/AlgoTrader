"""Tests for close detection matching strategies in paper_loop."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.broker.models import Transaction


def _txn(**kw):
    defaults = {
        "date": datetime(2026, 4, 20, 0, 2, 0),
        "type": "DEAL",
        "reference": "ref-abc",
        "instrumentName": "Oil - Crude",
        "openLevel": 84.50,
        "closeLevel": 84.87,
        "profitAndLoss": "USD246.86",
        "size": 10.0,
        "currency": "USD",
    }
    defaults.update(kw)
    return Transaction(**defaults)


@pytest.fixture
def paper_loop():
    """Minimal paper_loop instance for testing _match_transaction in isolation."""
    from src.trading.paper_loop import PaperTradingLoop

    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    return loop


def test_match_strategy_1_deal_reference_deterministic(paper_loop):
    """When deal_reference matches txn.reference, return that transaction
    regardless of other fields."""
    txns = [
        _txn(reference="wrong-1", closeLevel=99.99, profitAndLoss="USD1.00"),
        _txn(reference="match-ref", closeLevel=84.87, profitAndLoss="USD246.86"),
        _txn(reference="wrong-2", closeLevel=50.00, profitAndLoss="USD5.00"),
    ]
    result = paper_loop._match_transaction(
        transactions=txns,
        deal_id="deal-xyz",
        deal_reference="match-ref",
        epic="WTIUSD",
        entry_price=84.50,
    )
    exit_price, pnl, reason = result
    assert exit_price == pytest.approx(84.87)
    assert pnl == pytest.approx(246.86)
    assert reason == "TP"


def test_match_strategy_1_skips_when_deal_reference_none(paper_loop):
    """Strategy 1 skipped if deal_reference is None (legacy positions);
    falls through to Strategy 2/3."""
    txns = [_txn(reference="some-ref", openLevel=84.50, profitAndLoss="USD100.00")]
    result = paper_loop._match_transaction(
        transactions=txns,
        deal_id="some-ref",  # deal_id equals reference in legacy data
        deal_reference=None,
        epic="WTIUSD",
        entry_price=84.50,
    )
    exit_price, pnl, _ = result
    assert exit_price is not None
    assert pnl == pytest.approx(100.00)
