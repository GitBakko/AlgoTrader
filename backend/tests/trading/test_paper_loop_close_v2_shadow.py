"""Shadow-mode wiring tests for close-detection v2 inside paper_loop.

Verifies that the v2 CloseDetector runs alongside v1 without affecting v1's
authoritative decisions, records the expected Prometheus counters, and
detects v1/v2 disagreements.

Step 6 of `calm-questing-quail.md`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.trading.close_detector import Deferred, Reconciled, Unreconciled
from src.trading.paper_loop import PaperTradingLoop


def _make_loop() -> PaperTradingLoop:
    """Minimal PaperTradingLoop instance that bypasses the heavy __init__.

    Only the attributes touched by the shadow helpers are populated.
    """
    loop = PaperTradingLoop.__new__(PaperTradingLoop)
    loop.broker = MagicMock()
    loop._close_detector = None
    loop._account_currency = "USD"
    return loop


def _reconciled(deal_id: str = "POS-1", pnl: float = 29.28) -> Reconciled:
    activity = MagicMock()
    activity.deal_id = "CLOSE-" + deal_id
    txn = MagicMock()
    return Reconciled(
        deal_id=deal_id,
        close_dealid="CLOSE-" + deal_id,
        pnl=pnl,
        exit_price=24107.3,
        close_reason="TAKE_PROFIT_HIT",
        activity=activity,
        transaction=txn,
    )


class TestGetCloseDetector:
    def test_returns_none_when_broker_missing(self) -> None:
        loop = _make_loop()
        loop.broker = None
        assert loop._get_close_detector() is None

    def test_builds_and_caches_detector(self) -> None:
        loop = _make_loop()
        with patch("src.broker.fx.FxConverter") as fx_mock, patch(
            "src.trading.close_detector.CloseDetector"
        ) as cd_mock:
            fx_mock.return_value = MagicMock(name="fx")
            cd_mock.return_value = MagicMock(name="detector")

            first = loop._get_close_detector()
            second = loop._get_close_detector()

        assert first is second
        cd_mock.assert_called_once()

    def test_init_error_returns_none_and_logs(self) -> None:
        loop = _make_loop()
        with patch("src.broker.fx.FxConverter", side_effect=RuntimeError("FRED down")):
            assert loop._get_close_detector() is None


@pytest.mark.asyncio
class TestRunShadowCloseDetection:
    async def test_noop_when_detector_unavailable(self) -> None:
        loop = _make_loop()
        loop.broker = None  # forces _get_close_detector to return None

        with patch(
            "src.monitoring.metrics.MetricsCollector.record_close_detection_v2_shadow"
        ) as shadow_mock, patch(
            "src.monitoring.metrics.MetricsCollector.record_close_shadow_disagreement"
        ) as disagree_mock:
            await loop._run_shadow_close_detection(
                previous_snapshot={"POS-1": {"epic": "DE40"}},
                current_positions=[],
                transactions=[],
                v1_outcomes={"POS-1": "primary"},
            )

        shadow_mock.assert_not_called()
        disagree_mock.assert_not_called()

    async def test_agreement_records_shadow_but_no_disagreement(self) -> None:
        loop = _make_loop()
        detector = MagicMock()
        detector.detect = AsyncMock(return_value=[_reconciled("POS-1")])
        loop._close_detector = detector

        with patch(
            "src.monitoring.metrics.MetricsCollector.record_close_detection_v2_shadow"
        ) as shadow_mock, patch(
            "src.monitoring.metrics.MetricsCollector.record_close_shadow_disagreement"
        ) as disagree_mock:
            await loop._run_shadow_close_detection(
                previous_snapshot={"POS-1": {"epic": "DE40"}},
                current_positions=[],
                transactions=[],
                v1_outcomes={"POS-1": "primary"},
            )

        shadow_mock.assert_called_once_with(outcome="reconciled", epic="DE40")
        disagree_mock.assert_not_called()

    async def test_disagreement_records_disagreement_metric(self) -> None:
        loop = _make_loop()
        detector = MagicMock()
        # v2 reconciles, v1 deferred → disagreement
        detector.detect = AsyncMock(return_value=[_reconciled("POS-1")])
        loop._close_detector = detector

        with patch(
            "src.monitoring.metrics.MetricsCollector.record_close_detection_v2_shadow"
        ) as shadow_mock, patch(
            "src.monitoring.metrics.MetricsCollector.record_close_shadow_disagreement"
        ) as disagree_mock:
            await loop._run_shadow_close_detection(
                previous_snapshot={"POS-1": {"epic": "DE40"}},
                current_positions=[],
                transactions=[],
                v1_outcomes={"POS-1": "deferred"},
            )

        shadow_mock.assert_called_once_with(outcome="reconciled", epic="DE40")
        disagree_mock.assert_called_once_with(
            v1_path="deferred", v2_outcome="reconciled", epic="DE40"
        )

    async def test_deferred_outcome_agreement_with_deferred_v1(self) -> None:
        loop = _make_loop()
        detector = MagicMock()
        detector.detect = AsyncMock(
            return_value=[Deferred(deal_id="POS-2", reason="no_activity_event")]
        )
        loop._close_detector = detector

        with patch(
            "src.monitoring.metrics.MetricsCollector.record_close_detection_v2_shadow"
        ) as shadow_mock, patch(
            "src.monitoring.metrics.MetricsCollector.record_close_shadow_disagreement"
        ) as disagree_mock:
            await loop._run_shadow_close_detection(
                previous_snapshot={"POS-2": {"epic": "OIL_CRUDE"}},
                current_positions=[],
                transactions=[],
                v1_outcomes={"POS-2": "deferred"},
            )

        shadow_mock.assert_called_once_with(outcome="deferred", epic="OIL_CRUDE")
        disagree_mock.assert_not_called()

    async def test_unreconciled_outcome_disagreeing_with_v1_primary(self) -> None:
        loop = _make_loop()
        detector = MagicMock()
        detector.detect = AsyncMock(
            return_value=[Unreconciled(deal_id="POS-3", reason="fx_unavailable")]
        )
        loop._close_detector = detector

        with patch(
            "src.monitoring.metrics.MetricsCollector.record_close_detection_v2_shadow"
        ) as shadow_mock, patch(
            "src.monitoring.metrics.MetricsCollector.record_close_shadow_disagreement"
        ) as disagree_mock:
            await loop._run_shadow_close_detection(
                previous_snapshot={"POS-3": {"epic": "XAUUSD"}},
                current_positions=[],
                transactions=[],
                v1_outcomes={"POS-3": "primary"},
            )

        shadow_mock.assert_called_once_with(outcome="unreconciled", epic="XAUUSD")
        disagree_mock.assert_called_once_with(
            v1_path="primary", v2_outcome="unreconciled", epic="XAUUSD"
        )

    async def test_detector_exception_emits_error_metric_per_deal(self) -> None:
        loop = _make_loop()
        detector = MagicMock()
        detector.detect = AsyncMock(side_effect=RuntimeError("broker fetch failed"))
        loop._close_detector = detector

        snapshot = {
            "POS-A": {"epic": "DE40"},
            "POS-B": {"epic": "OIL_CRUDE"},
        }
        with patch(
            "src.monitoring.metrics.MetricsCollector.record_close_detection_v2_shadow"
        ) as shadow_mock, patch(
            "src.monitoring.metrics.MetricsCollector.record_close_shadow_disagreement"
        ) as disagree_mock:
            await loop._run_shadow_close_detection(
                previous_snapshot=snapshot,
                current_positions=[],
                transactions=[],
                v1_outcomes={"POS-A": "primary", "POS-B": "deferred"},
            )

        assert shadow_mock.call_count == 2
        shadow_calls = {c.kwargs["epic"]: c.kwargs["outcome"] for c in shadow_mock.call_args_list}
        assert shadow_calls == {"DE40": "error", "OIL_CRUDE": "error"}
        disagree_mock.assert_not_called()

    async def test_passes_injected_transactions_to_detector(self) -> None:
        loop = _make_loop()
        detector = MagicMock()
        detector.detect = AsyncMock(return_value=[])
        loop._close_detector = detector

        txns = [MagicMock(name="txn1")]
        await loop._run_shadow_close_detection(
            previous_snapshot={},
            current_positions=[],
            transactions=txns,
            v1_outcomes={},
        )

        detector.detect.assert_awaited_once()
        call_kwargs = detector.detect.await_args.kwargs
        assert call_kwargs["transactions"] is txns
        assert call_kwargs["previous"] == {}
        assert call_kwargs["current"] == []


@pytest.mark.asyncio
class TestDetectBrokerClosedShadowIntegration:
    """End-to-end: v1 remains authoritative, v2 runs only when flag enabled."""

    def _prepare_loop(self, *, v2_enabled: bool) -> PaperTradingLoop:
        loop = _make_loop()
        # minimal attrs touched by _detect_broker_closed
        from src.execution.schemas import ExecutionMode

        exec_engine = MagicMock()
        exec_engine.mode = ExecutionMode.DEMO
        loop.execution_engine = exec_engine
        loop._previous_positions = {}
        loop._pending_close_detections = {}
        loop._broker_closed_deals = set()
        loop._db_session_factory = None
        loop._fetch_recent_transactions = AsyncMock(return_value=[])
        loop._run_shadow_close_detection = AsyncMock()
        return loop

    async def test_flag_off_skips_shadow(self) -> None:
        loop = self._prepare_loop(v2_enabled=False)
        # seed previous state so loop reaches the later code path
        loop._previous_positions = {
            "POS-1": {"deal_id": "POS-1", "epic": "DE40", "level": 24100.0, "direction": "BUY"}
        }

        with patch("src.trading.paper_loop.get_settings") as settings_mock:
            settings_mock.return_value = MagicMock(
                close_reconciliation_timeout_seconds=600,
                close_detection_v2_enabled=False,
            )
            await loop._detect_broker_closed(current_positions=[])

        loop._run_shadow_close_detection.assert_not_awaited()

    async def test_flag_on_invokes_shadow_after_v1(self) -> None:
        loop = self._prepare_loop(v2_enabled=True)
        loop._previous_positions = {
            "POS-1": {"deal_id": "POS-1", "epic": "DE40", "level": 24100.0, "direction": "BUY"}
        }

        with patch("src.trading.paper_loop.get_settings") as settings_mock:
            settings_mock.return_value = MagicMock(
                close_reconciliation_timeout_seconds=600,
                close_detection_v2_enabled=True,
            )
            await loop._detect_broker_closed(current_positions=[])

        loop._run_shadow_close_detection.assert_awaited_once()
        kwargs = loop._run_shadow_close_detection.await_args.kwargs
        assert "POS-1" in kwargs["previous_snapshot"]
        # v1 logged "POS-1" as deferred (no transaction match, no timeout yet)
        assert kwargs["v1_outcomes"] == {"POS-1": "deferred"}

    async def test_paper_mode_never_runs_shadow(self) -> None:
        loop = self._prepare_loop(v2_enabled=True)
        from src.execution.schemas import ExecutionMode

        loop.execution_engine.mode = ExecutionMode.PAPER

        with patch("src.trading.paper_loop.get_settings") as settings_mock:
            settings_mock.return_value = MagicMock(
                close_reconciliation_timeout_seconds=600,
                close_detection_v2_enabled=True,
            )
            await loop._detect_broker_closed(current_positions=[])

        loop._run_shadow_close_detection.assert_not_awaited()
