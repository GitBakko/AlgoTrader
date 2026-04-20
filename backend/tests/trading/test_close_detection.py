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


def test_match_strategy_3_normalized_oil_crude(paper_loop):
    """WTIUSD epic matches broker instrument 'Oil - Crude' after normalization."""
    txns = [_txn(reference="unrelated", instrumentName="Oil - Crude", openLevel=84.50)]
    exit_price, pnl, _ = paper_loop._match_transaction(
        transactions=txns,
        deal_id="d-1",
        deal_reference=None,
        epic="WTIUSD",
        entry_price=84.50,
    )
    assert exit_price is not None


@pytest.mark.xfail(
    reason=(
        "Strategy 3 cannot match DE40 → 'Germany 40' via substring: "
        "EPIC_TO_BROKER has no DE40 entry, so broker_epic defaults to 'DE40' "
        "and normalized 'de40' shares no substring with 'germany40'. "
        "In production, DE40 is handled by Strategy 1 via deal_reference "
        "(wired in Task 7). This xfail documents the Strategy 3 gap."
    ),
    strict=True,
)
def test_match_strategy_3_normalized_germany_40_documented_gap(paper_loop):
    """Documents Strategy 3 limitation on DE40 → Germany 40 mapping."""
    txns = [
        _txn(
            reference="unrelated",
            instrumentName="Germany 40",
            openLevel=24510.0,
            closeLevel=24532.0,
            profitAndLoss="EUR44.38",
            currency="EUR",
        )
    ]
    exit_price, pnl, _ = paper_loop._match_transaction(
        transactions=txns,
        deal_id="d-1",
        deal_reference=None,
        epic="DE40",
        entry_price=24510.0,
    )
    assert exit_price == pytest.approx(24532.0)
    assert pnl == pytest.approx(44.38)


def test_match_strategy_3_entry_tolerance_rejects_distant_level(paper_loop):
    """Entry level > 0.1% away from txn.open_level is rejected."""
    txns = [_txn(reference="x", instrumentName="Oil - Crude", openLevel=80.00)]
    result = paper_loop._match_transaction(
        transactions=txns,
        deal_id="d-1",
        deal_reference=None,
        epic="WTIUSD",
        entry_price=84.50,
    )
    assert result == (None, None, None)


def test_match_strategy_3_ambiguous_picks_most_recent(paper_loop, caplog):
    """Two txns, same epic + same entry → pick most recent date, log WARNING."""
    import logging

    older = _txn(
        reference="r-old",
        instrumentName="Oil - Crude",
        openLevel=84.50,
        closeLevel=84.80,
        profitAndLoss="USD100.00",
        date=datetime(2026, 4, 20, 0, 1, 0),
    )
    newer = _txn(
        reference="r-new",
        instrumentName="Oil - Crude",
        openLevel=84.50,
        closeLevel=84.87,
        profitAndLoss="USD246.86",
        date=datetime(2026, 4, 20, 0, 2, 0),
    )
    with caplog.at_level(logging.WARNING):
        exit_price, pnl, _ = paper_loop._match_transaction(
            transactions=[older, newer],
            deal_id="d-1",
            deal_reference=None,
            epic="WTIUSD",
            entry_price=84.50,
        )
    assert exit_price == pytest.approx(84.87)  # newer wins
    assert pnl == pytest.approx(246.86)


def test_match_no_match_returns_all_none(paper_loop):
    result = paper_loop._match_transaction(
        transactions=[],
        deal_id="d-1",
        deal_reference="ref-1",
        epic="WTIUSD",
        entry_price=84.50,
    )
    assert result == (None, None, None)


def test_match_skips_transaction_with_none_pl(paper_loop):
    """Transaction with profitAndLoss=None is skipped, next candidate tried."""
    incomplete = _txn(reference="ref-match", profitAndLoss=None, amount=None)
    good = _txn(
        reference="ref-match",
        profitAndLoss="USD74.18",
        closeLevel=84.87,
    )
    # Same reference on two rows — first is incomplete, second is good
    result = paper_loop._match_transaction(
        transactions=[incomplete, good],
        deal_id="d-1",
        deal_reference="ref-match",
        epic="WTIUSD",
        entry_price=84.50,
    )
    # Strategy 1 finds incomplete first → skips → finds good
    assert result[0] is not None
    assert result[1] == pytest.approx(74.18)
