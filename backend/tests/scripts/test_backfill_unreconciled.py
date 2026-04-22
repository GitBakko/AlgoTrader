"""Unit tests for `scripts/backfill_unreconciled.py`.

Step 14 of close-detection v2 (plan `calm-questing-quail.md`).

Verifies three invariants:

1. Only rows with ``status='CLOSED'`` AND ``close_reason='UNRECONCILED'``
   AND ``profit_loss IS NULL`` are touched.
2. Dry-run never commits and never mutates the DB rows (rollback path).
3. Apply mode writes the reconciled P&L, exit price, and close_reason
   from the v2 outcome; Deferred / Unreconciled / error outcomes are
   reported but NEVER written.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.backfill_unreconciled import (
    BackfillReport,
    _position_to_prev_pos,
    backfill_one,
    main,
    parse_args,
    run_backfill,
)
from src.trading.close_detector import Deferred, Reconciled, Unreconciled


def _pos(**kw) -> SimpleNamespace:
    """Minimal stand-in for src.database.models.Position."""
    base = {
        "deal_id": "POS-1",
        "epic": "DE40",
        "direction": "BUY",
        "size": Decimal("1.0"),
        "entry_price": Decimal("24000.0"),
        "current_price": None,
        "profit_loss": None,
        "close_reason": "UNRECONCILED",
        "status": "CLOSED",
        "opened_at": datetime(2026, 4, 21, 22, 0, 0, tzinfo=UTC),
        "closed_at": datetime(2026, 4, 21, 23, 0, 0, tzinfo=UTC),
        "deal_reference": None,
        "updated_at": datetime(2026, 4, 22, 0, 0, 0, tzinfo=UTC),
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _reconciled(deal_id: str = "POS-1") -> Reconciled:
    return Reconciled(
        deal_id=deal_id,
        close_dealid="CLOSE-" + deal_id,
        pnl=29.28,
        exit_price=24107.3,
        close_reason="TAKE_PROFIT_HIT",
        activity=MagicMock(),
        transaction=MagicMock(),
    )


class TestPositionToPrevPos:
    def test_maps_all_fields(self):
        row = _pos()
        prev = _position_to_prev_pos(row)
        assert prev["deal_id"] == "POS-1"
        assert prev["epic"] == "DE40"
        assert prev["direction"] == "BUY"
        assert prev["level"] == 24000.0
        assert prev["size"] == 1.0
        assert "T" in prev["opened_at"]  # ISO format
        assert prev["deal_reference"] is None


@pytest.mark.asyncio
class TestBackfillOne:
    async def _build_detector(self, outcomes):
        detector = MagicMock()
        detector._broker = MagicMock()
        detector._broker.get_activity_history = AsyncMock(return_value=[])
        detector._broker.get_transaction_history = AsyncMock(return_value=[])
        detector.detect = AsyncMock(return_value=outcomes)
        return detector

    async def test_reconciled_in_apply_mode_writes_row(self):
        row = _pos()
        session = MagicMock()
        session.add = MagicMock()
        report = BackfillReport()
        detector = await self._build_detector([_reconciled("POS-1")])

        await backfill_one(
            row=row,
            detector=detector,
            session=session,
            report=report,
            apply_writes=True,
        )

        session.add.assert_called_once_with(row)
        assert row.profit_loss == Decimal("29.28")
        assert row.current_price == Decimal("24107.300000")
        assert row.close_reason == "TAKE_PROFIT_HIT"
        assert report.reconciled == ["POS-1"]
        assert report.deferred == []
        assert report.unreconciled_v2 == []

    async def test_reconciled_in_dry_run_does_not_write(self):
        row = _pos()
        session = MagicMock()
        session.add = MagicMock()
        report = BackfillReport()
        detector = await self._build_detector([_reconciled("POS-1")])

        await backfill_one(
            row=row,
            detector=detector,
            session=session,
            report=report,
            apply_writes=False,
        )

        session.add.assert_not_called()
        assert row.profit_loss is None
        assert row.close_reason == "UNRECONCILED"  # unchanged
        assert report.reconciled == ["POS-1"]

    async def test_deferred_outcome_never_writes(self):
        row = _pos()
        session = MagicMock()
        session.add = MagicMock()
        report = BackfillReport()
        detector = await self._build_detector(
            [Deferred(deal_id="POS-1", reason="no_activity_event")]
        )

        await backfill_one(
            row=row,
            detector=detector,
            session=session,
            report=report,
            apply_writes=True,  # even in apply mode
        )

        session.add.assert_not_called()
        assert row.profit_loss is None
        assert report.deferred == [("POS-1", "no_activity_event")]

    async def test_unreconciled_outcome_never_writes(self):
        row = _pos()
        session = MagicMock()
        session.add = MagicMock()
        report = BackfillReport()
        detector = await self._build_detector(
            [Unreconciled(deal_id="POS-1", reason="fx_unavailable")]
        )

        await backfill_one(
            row=row,
            detector=detector,
            session=session,
            report=report,
            apply_writes=True,
        )

        session.add.assert_not_called()
        assert row.profit_loss is None
        assert report.unreconciled_v2 == [("POS-1", "fx_unavailable")]

    async def test_detector_exception_is_recorded_as_error(self):
        row = _pos()
        session = MagicMock()
        session.add = MagicMock()
        report = BackfillReport()
        detector = MagicMock()
        detector._broker = MagicMock()
        detector._broker.get_activity_history = AsyncMock(return_value=[])
        detector._broker.get_transaction_history = AsyncMock(return_value=[])
        detector.detect = AsyncMock(side_effect=RuntimeError("fetch failed"))

        await backfill_one(
            row=row,
            detector=detector,
            session=session,
            report=report,
            apply_writes=True,
        )

        session.add.assert_not_called()
        assert len(report.errors) == 1
        assert report.errors[0][0] == "POS-1"
        assert "fetch failed" in report.errors[0][1]


@pytest.mark.asyncio
class TestRunBackfill:
    async def test_dry_run_calls_rollback_not_commit(self):
        row = _pos()
        session = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        # fetch_candidates uses session.execute → return a mocked result
        from scripts import backfill_unreconciled as mod

        # Monkeypatch fetch_candidates for this test
        async def _fake_fetch(_):
            return [row]

        original = mod.fetch_candidates
        mod.fetch_candidates = _fake_fetch
        try:
            detector = MagicMock()
            detector._broker = MagicMock()
            detector._broker.get_activity_history = AsyncMock(return_value=[])
            detector._broker.get_transaction_history = AsyncMock(return_value=[])
            detector.detect = AsyncMock(return_value=[_reconciled("POS-1")])

            report = await run_backfill(
                session=session, detector=detector, apply_writes=False
            )
        finally:
            mod.fetch_candidates = original

        session.commit.assert_not_called()
        session.rollback.assert_awaited_once()
        assert report.reconciled == ["POS-1"]

    async def test_apply_mode_commits_when_anything_reconciled(self):
        row = _pos()
        session = MagicMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        from scripts import backfill_unreconciled as mod

        async def _fake_fetch(_):
            return [row]

        original = mod.fetch_candidates
        mod.fetch_candidates = _fake_fetch
        try:
            detector = MagicMock()
            detector._broker = MagicMock()
            detector._broker.get_activity_history = AsyncMock(return_value=[])
            detector._broker.get_transaction_history = AsyncMock(return_value=[])
            detector.detect = AsyncMock(return_value=[_reconciled("POS-1")])

            await run_backfill(session=session, detector=detector, apply_writes=True)
        finally:
            mod.fetch_candidates = original

        session.commit.assert_awaited_once()
        session.rollback.assert_not_called()


class TestParseArgs:
    def test_default_is_dry_run(self):
        args = parse_args([])
        assert args.dry_run is True
        assert args.apply is False

    def test_apply_flips_dry_run(self):
        args = parse_args(["--apply", "--yes"])
        assert args.apply is True
        assert args.dry_run is False
        assert args.yes is True

    def test_account_currency_override(self):
        args = parse_args(["--account-currency", "EUR"])
        assert args.account_currency == "EUR"

    def test_window_minutes_default_and_override(self):
        assert parse_args([]).window_minutes == 10
        assert parse_args(["--window-minutes", "2880"]).window_minutes == 2880


class TestMainSafetyGate:
    def test_apply_without_yes_refused(self):
        rc = main(["--apply"])
        assert rc == 2  # EXIT_REFUSED

    def test_apply_with_yes_reaches_event_loop(self, monkeypatch):
        # We don't want to actually spin up asyncio / connect to DB here.
        called = {"n": 0}

        async def _fake_main(args):
            called["n"] += 1
            return 0

        from scripts import backfill_unreconciled as mod

        monkeypatch.setattr(mod, "_main", _fake_main)

        rc = main(["--apply", "--yes"])
        assert rc == 0
        assert called["n"] == 1
