"""Contract tests for Capital.com /api/v1/history/transactions schema.

Companion to the activity schema tests. Encodes the live TRADE-row contract
verified 2026-04-21: the `dealId` on a TRADE row equals the close-side
dealId emitted in the matching activity event, and `size` carries the
realized P&L as a string in the account currency (NOT the position size).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.broker.models import Transaction

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "broker_api"


def _fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    if not path.exists():
        pytest.skip(f"Fixture {name} missing — run scripts/capture_broker_fixtures.py")
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def test_transactions_payload_parses_through_pydantic():
    payload = _fixture("live_20260421_transactions.json")
    txns = payload["response"].get("transactions", [])
    assert txns, "No transactions in captured fixture"
    parsed = [Transaction(**t) for t in txns]
    # Every TRADE row has a dealId, a reference, a note, and a size string.
    for txn in parsed:
        assert txn.reference, "TRADE row missing reference"
        if txn.transaction_type and txn.transaction_type.upper() == "TRADE":
            assert txn.deal_id is not None, "TRADE row missing dealId"
            assert txn.size is not None, "TRADE row missing size"
            assert txn.pl_value is not None, (
                f"TRADE row {txn.reference} size={txn.size!r} did not parse to P&L"
            )


def test_trade_row_size_is_string_containing_signed_pnl():
    """Broker ships `size` as a decimal string on TRADE rows. Regression
    guard: if they ever switch to float we want to fail loud so the
    numeric-handling branch is updated intentionally.
    """
    payload = _fixture("live_20260421_transactions.json")
    txns = payload["response"].get("transactions", [])
    trade_rows = [t for t in txns if (t.get("transactionType") or "").upper() == "TRADE"]
    if not trade_rows:
        pytest.skip("No TRADE rows in fixture window")

    for raw in trade_rows:
        size = raw.get("size")
        assert isinstance(size, str), (
            f"Broker changed TRADE.size to {type(size).__name__}; update "
            f"Transaction.pl_value parsing and this assertion deliberately."
        )
        # Must be parseable as a signed decimal.
        float(size)


def test_trade_row_currency_field_present():
    payload = _fixture("live_20260421_transactions.json")
    txns = payload["response"].get("transactions", [])
    trade_rows = [t for t in txns if (t.get("transactionType") or "").upper() == "TRADE"]
    if not trade_rows:
        pytest.skip("No TRADE rows in fixture window")

    for raw in trade_rows:
        assert raw.get("currency"), (
            f"TRADE row missing currency field: {raw}. Required for FX check."
        )


def test_trade_row_no_openlevel_closelevel_on_current_schema():
    """Documentation test for the CURRENT demo schema (2026-04-21).

    If Capital.com ever reintroduces `openLevel` / `closeLevel`, this test
    fails — which is a POSITIVE signal: update the Transaction model to
    use the richer fields and relax this assertion.
    """
    payload = _fixture("live_20260421_transactions.json")
    txns = payload["response"].get("transactions", [])
    trade_rows = [t for t in txns if (t.get("transactionType") or "").upper() == "TRADE"]
    if not trade_rows:
        pytest.skip("No TRADE rows in fixture window")

    has_open = any("openLevel" in raw for raw in trade_rows)
    has_close = any("closeLevel" in raw for raw in trade_rows)
    assert not has_open and not has_close, (
        "Capital.com re-added openLevel/closeLevel to TRADE rows — "
        "update Transaction model and _finalize to use them."
    )
