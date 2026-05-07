"""Step 7 of close-detection v2: no synthetic P&L on TIME_STOP / SL / TP paths.

After these paths successfully submit a close to the broker, the loop must
NOT:
- compute `(current_price - entry_price) * size` P&L
- call `_on_position_closed` with a synthetic P&L
- call `_persist_position_close` with a synthetic P&L
- broadcast a `trade_closed` WS event with a synthetic P&L

All of those side-effects are deferred to CloseDetector reconciliation, which
is wired via `_detect_broker_closed` → `_finalize_close` on the next tick.

Plan: calm-questing-quail.md — Step 7/15.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.execution.schemas import ExecutionResult
from src.trading.paper_loop import PaperTradingLoop


@pytest.fixture
def mock_paper_loop() -> PaperTradingLoop:
    prediction_service = MagicMock()
    strategy_manager = MagicMock()
    risk_manager = MagicMock()
    execution_engine = MagicMock()
    data_access = MagicMock()
    broker = MagicMock()
    broker.get_market_details = AsyncMock(
        return_value={"snapshot": {"bid": 0.0, "offer": 0.0}}
    )
    return PaperTradingLoop(
        prediction_service=prediction_service,
        strategy_manager=strategy_manager,
        risk_manager=risk_manager,
        execution_engine=execution_engine,
        data_access=data_access,
        broker=broker,
        epics=["XAUUSD", "BTCUSD"],
    )


def _set_broker_price(loop: PaperTradingLoop, price: float) -> None:
    """Configure mocked broker snapshot for SL/TP trigger tests.

    Post 2026-05-04 ``_check_stop_losses`` reads price exclusively from
    ``broker.get_market_details(epic).snapshot.{bid,offer}``. Use both
    sides identical so direction-based picking gives the same value.
    """
    loop.broker.get_market_details = AsyncMock(
        return_value={"snapshot": {"bid": price, "offer": price}}
    )


@pytest.mark.asyncio
class TestSlTpNoSyntheticPnl:
    async def test_sl_hit_does_not_persist_synthetic_pnl(
        self, mock_paper_loop: PaperTradingLoop
    ) -> None:
        position = {
            "deal_id": "POS-SL-1",
            "epic": "XAUUSD",
            "direction": "BUY",
            "level": 2000.0,
            "stop_level": 1990.0,
            "size": 1.0,
        }
        _set_broker_price(mock_paper_loop, 1985.0)  # below SL → trigger
        mock_paper_loop.execution_engine.close_position = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="POS-SL-1")
        )
        mock_paper_loop._persist_position_close = AsyncMock()
        mock_paper_loop._on_position_closed = MagicMock()

        await mock_paper_loop._check_stop_losses([position])

        mock_paper_loop.execution_engine.close_position.assert_awaited_once_with(
            deal_id="POS-SL-1", reason="STOP_LOSS_HIT"
        )
        mock_paper_loop._persist_position_close.assert_not_called()
        mock_paper_loop._on_position_closed.assert_not_called()

    async def test_sl_hit_appends_signal_history_with_pnl_none(
        self, mock_paper_loop: PaperTradingLoop
    ) -> None:
        position = {
            "deal_id": "POS-SL-2",
            "epic": "XAUUSD",
            "direction": "BUY",
            "level": 2000.0,
            "stop_level": 1990.0,
            "size": 1.0,
        }
        _set_broker_price(mock_paper_loop, 1985.0)
        mock_paper_loop.execution_engine.close_position = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="POS-SL-2")
        )

        await mock_paper_loop._check_stop_losses([position])

        assert len(mock_paper_loop._signal_history) == 1
        entry = mock_paper_loop._signal_history[-1]
        assert entry["deal_id"] == "POS-SL-2"
        assert entry["status"] == "sl_hit"
        assert entry["pnl"] is None

    async def test_tp_hit_does_not_persist_synthetic_pnl(
        self, mock_paper_loop: PaperTradingLoop
    ) -> None:
        position = {
            "deal_id": "POS-TP-1",
            "epic": "XAUUSD",
            "direction": "SELL",
            "level": 2000.0,
            "stop_level": 2010.0,
            "profit_level": 1990.0,
            "size": 1.0,
        }
        _set_broker_price(mock_paper_loop, 1985.0)  # below TP → trigger for SHORT
        mock_paper_loop.execution_engine.close_position = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="POS-TP-1")
        )
        mock_paper_loop._persist_position_close = AsyncMock()
        mock_paper_loop._on_position_closed = MagicMock()

        await mock_paper_loop._check_stop_losses([position])

        mock_paper_loop.execution_engine.close_position.assert_awaited_once_with(
            deal_id="POS-TP-1", reason="TAKE_PROFIT_HIT"
        )
        mock_paper_loop._persist_position_close.assert_not_called()
        mock_paper_loop._on_position_closed.assert_not_called()
        assert mock_paper_loop._signal_history[-1]["status"] == "tp_hit"
        assert mock_paper_loop._signal_history[-1]["pnl"] is None

    async def test_failed_close_does_not_append_signal_history(
        self, mock_paper_loop: PaperTradingLoop
    ) -> None:
        position = {
            "deal_id": "POS-SL-FAIL",
            "epic": "XAUUSD",
            "direction": "BUY",
            "level": 2000.0,
            "stop_level": 1990.0,
            "size": 1.0,
        }
        _set_broker_price(mock_paper_loop, 1985.0)
        mock_paper_loop.execution_engine.close_position = AsyncMock(
            return_value=ExecutionResult(
                success=False, deal_id="POS-SL-FAIL", error="network"
            )
        )
        before = len(mock_paper_loop._signal_history)

        await mock_paper_loop._check_stop_losses([position])

        assert len(mock_paper_loop._signal_history) == before


@pytest.mark.asyncio
class TestTimeStopNoSyntheticPnl:
    async def test_time_stop_does_not_persist_synthetic_pnl(
        self, mock_paper_loop: PaperTradingLoop
    ) -> None:
        opened_at = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
        position = {
            "deal_id": "POS-TIME-1",
            "epic": "XAUUSD",
            "direction": "BUY",
            "level": 2000.0,
            "stop_level": 1990.0,
            "profit_level": 2020.0,
            "size": 1.0,
            "opened_at": opened_at,
            "market_status": "TRADEABLE",
        }
        _set_broker_price(mock_paper_loop, 2005.0)
        mock_paper_loop.execution_engine.close_position = AsyncMock(
            return_value=ExecutionResult(success=True, deal_id="POS-TIME-1")
        )
        mock_paper_loop._persist_position_close = AsyncMock()
        mock_paper_loop._on_position_closed = MagicMock()

        await mock_paper_loop._check_stop_losses([position])

        mock_paper_loop.execution_engine.close_position.assert_awaited_once_with(
            deal_id="POS-TIME-1", reason="TIME_STOP"
        )
        mock_paper_loop._persist_position_close.assert_not_called()
        mock_paper_loop._on_position_closed.assert_not_called()


class TestExecutionEngineNoArithmeticFallback:
    """Guard against regression: the (fill-entry)*size fallback is gone."""

    def test_source_has_no_arithmetic_pnl_fallback(self) -> None:
        import inspect

        from src.execution import execution_engine as mod

        src = inspect.getsource(mod.ExecutionEngine.close_position)
        # The removed pattern — any re-introduction in close_position trips this.
        assert "(result.fill_price - entry_price) * size" not in src
        assert "(entry_price - result.fill_price) * size" not in src


class TestPaperLoopNoArithmeticFallback:
    """Same guard for paper_loop TIME_STOP / SL / TP paths."""

    def test_check_stop_losses_has_no_arithmetic_pnl(self) -> None:
        import inspect

        from src.trading import paper_loop as pl

        src = inspect.getsource(pl.PaperTradingLoop._check_stop_losses)
        assert "(current_price - entry_price) * size" not in src
        assert "(entry_price - current_price) * size" not in src
