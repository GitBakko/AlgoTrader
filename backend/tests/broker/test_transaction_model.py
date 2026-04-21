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


# ===== Live Capital.com schema (verified 2026-04-21) =====
#
# The /history/transactions endpoint actually returns these fields per row:
#   transactionType: "TRADE" | "SWAP" | "DEPOSIT" | "WITHDRAWAL"
#   dealId:          the Position deal_id (deterministic match key)
#   reference:       internal transaction id (NOT a deal_reference)
#   size:            STRING. For TRADE rows it carries the realized P&L
#                    in the account currency (e.g. "79.37", "-17.45").
#   note:            "Trade closed" / "Overnight fee" / etc.
#   currency:        e.g. "USDd"
# It does NOT return openLevel / closeLevel / profitAndLoss any more.

LIVE_TRADE_CLOSE = {
    "date": "2026-04-20T19:32:45.307",
    "dateUtc": "2026-04-20T17:32:45.307",
    "instrumentName": "OIL_CRUDE",
    "transactionType": "TRADE",
    "note": "Trade closed",
    "reference": "125579931413917",
    "size": "79.37",
    "currency": "USDd",
    "status": "PROCESSED",
    "dealId": "00018509-0055-311e-0000-00008262416d",
}


def test_live_trade_row_parses_pnl_from_size():
    """On the current live schema, TRADE rows carry the realized P&L in
    the `size` string field. `pl_value` must parse it as a signed float."""
    txn = Transaction(**LIVE_TRADE_CLOSE)
    assert txn.deal_id == "00018509-0055-311e-0000-00008262416d"
    assert txn.transaction_type == "TRADE"
    assert txn.pl_value == pytest.approx(79.37)


def test_live_trade_row_parses_negative_pnl():
    payload = dict(LIVE_TRADE_CLOSE, size="-17.45")
    txn = Transaction(**payload)
    assert txn.pl_value == pytest.approx(-17.45)


def test_swap_row_skipped_for_pnl_extraction():
    """SWAP rows are overnight financing fees, not closes — `pl_value` should
    not invent a P&L from the swap amount. The legacy `profitAndLoss` field
    is absent on the live schema, so we expect None."""
    payload = {
        "date": "2026-04-20T23:05:15.347",
        "instrumentName": "OIL_CRUDE",
        "transactionType": "SWAP",
        "note": "Overnight fee",
        "reference": "125593300669265",
        "size": "1.88",
        "currency": "USDd",
    }
    txn = Transaction(**payload)
    assert txn.pl_value is None


def test_currency_warning_uses_currency_field_when_pnl_string_absent(caplog):
    """On the live schema there is no `profitAndLoss` string with a currency
    prefix. `pl_value_in` must fall back to the dedicated `currency` field
    (stripping the demo-account 'd' suffix from values like 'USDd')."""
    payload = dict(LIVE_TRADE_CLOSE, currency="EURd", size="44.38")
    txn = Transaction(**payload)
    with caplog.at_level(logging.WARNING, logger="src.broker.models"):
        value = txn.pl_value_in(account_currency="USD")
    assert value == pytest.approx(44.38)
    assert any("currency mismatch" in r.message.lower() for r in caplog.records), (
        f"Expected currency-mismatch WARNING, got: {[r.message for r in caplog.records]}"
    )
