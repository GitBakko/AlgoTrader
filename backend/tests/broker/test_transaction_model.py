"""Tests for Transaction.pl_value currency handling."""

from __future__ import annotations

import logging

import pytest

from src.broker.models import Transaction


def _base_txn(**overrides):
    data = {
        "date": "2026-04-20T00:02:00",
        "type": "DEAL",
        "reference": "ref-123",
        "instrumentName": "Oil - Crude",
        "openLevel": 84.50,
        "closeLevel": 84.87,
        "profitAndLoss": "USD74.18",
        "size": 10.0,
        "currency": "USD",
    }
    data.update(overrides)
    return Transaction(**data)


@pytest.fixture(autouse=True)
def _propagate_loguru_to_caplog(caplog):
    """Forward loguru records to stdlib logging so caplog can capture them."""
    from loguru import logger

    class _PropagateHandler:
        def write(self, message):
            record = message.record
            logging.getLogger(record["name"]).log(record["level"].no, record["message"])

    handler_id = logger.add(_PropagateHandler(), format="{message}", level="WARNING")
    yield
    logger.remove(handler_id)


def test_pl_value_parses_usd_prefix():
    txn = _base_txn(profitAndLoss="USD74.18")
    assert txn.pl_value == pytest.approx(74.18)


def test_pl_value_parses_negative_eur_prefix():
    txn = _base_txn(profitAndLoss="-EUR12.50", currency="EUR")
    assert txn.pl_value == pytest.approx(-12.50)


def test_pl_value_warns_when_currency_differs_from_account(caplog):
    """When account is USD but P&L arrives in EUR, we must log a WARNING
    (we do NOT convert — just flag for visibility)."""
    txn = _base_txn(profitAndLoss="EUR44.38", currency="EUR")
    with caplog.at_level(logging.WARNING, logger="src.broker.models"):
        value = txn.pl_value_in(account_currency="USD")
    assert value == pytest.approx(44.38)
    assert any(
        "currency mismatch" in record.message.lower() for record in caplog.records
    ), f"Expected WARNING about currency mismatch, got: {[r.message for r in caplog.records]}"


def test_pl_value_in_no_warning_when_currency_matches():
    txn = _base_txn(profitAndLoss="USD74.18", currency="USD")
    assert txn.pl_value_in("USD") == pytest.approx(74.18)


def test_pl_value_returns_none_for_empty():
    txn = _base_txn(profitAndLoss=None, amount=None)
    assert txn.pl_value is None
