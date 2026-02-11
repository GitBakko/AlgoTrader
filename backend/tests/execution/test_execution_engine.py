"""Tests for execution engine orchestrator."""

import pytest

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.risk.schemas import RiskCheckResult
from src.strategy.schemas import SignalDirection, TradingSignal


@pytest.fixture
def engine():
    return ExecutionEngine(mode=ExecutionMode.PAPER)


def _make_signal(epic="XAUUSD", direction=SignalDirection.BUY, price=2000.0) -> TradingSignal:
    return TradingSignal(
        epic=epic,
        direction=direction,
        confidence=0.80,
        signal_class=2,
        entry_price=price,
    )


def _make_risk_result(size=1.0, sl=1960.0, tp=2080.0) -> RiskCheckResult:
    return RiskCheckResult(
        approved=True,
        position_size=size,
        stop_loss=sl,
        take_profit=tp,
    )


class TestExecutionEngine:
    @pytest.mark.asyncio
    async def test_execute_signal(self, engine):
        signal = _make_signal()
        risk = _make_risk_result()
        result = await engine.execute_signal(signal, risk)
        assert result.success is True
        assert result.deal_id.startswith("PAPER-")
        assert result.fill_price == 2000.0

    @pytest.mark.asyncio
    async def test_position_tracked_after_execute(self, engine):
        signal = _make_signal()
        risk = _make_risk_result()
        await engine.execute_signal(signal, risk)
        positions = await engine.get_open_positions()
        assert len(positions) == 1
        assert positions[0]["epic"] == "XAUUSD"

    @pytest.mark.asyncio
    async def test_close_position(self, engine):
        signal = _make_signal()
        risk = _make_risk_result()
        exec_result = await engine.execute_signal(signal, risk)
        close_result = await engine.close_position(exec_result.deal_id, "TP")
        assert close_result.success is True
        positions = await engine.get_open_positions()
        assert len(positions) == 0

    @pytest.mark.asyncio
    async def test_slippage_recorded(self, engine):
        signal = _make_signal()
        risk = _make_risk_result()
        await engine.execute_signal(signal, risk)
        # Paper mode has 0 slippage
        avg = engine.slippage_tracker.get_average_slippage("XAUUSD")
        assert avg == 0.0

    @pytest.mark.asyncio
    async def test_multiple_positions(self, engine):
        for i in range(3):
            signal = _make_signal(epic=f"ASSET{i}", price=100.0 + i)
            risk = _make_risk_result(sl=95.0 + i, tp=110.0 + i)
            await engine.execute_signal(signal, risk)
        positions = await engine.get_open_positions()
        assert len(positions) == 3

    @pytest.mark.asyncio
    async def test_filter_positions_by_epic(self, engine):
        s1 = _make_signal(epic="XAUUSD")
        s2 = _make_signal(epic="BTCUSD", price=50000.0)
        r1 = _make_risk_result()
        r2 = _make_risk_result(sl=49000.0, tp=52000.0)
        await engine.execute_signal(s1, r1)
        await engine.execute_signal(s2, r2)
        gold = await engine.get_open_positions("XAUUSD")
        assert len(gold) == 1

    @pytest.mark.asyncio
    async def test_update_stops(self, engine):
        signal = _make_signal()
        risk = _make_risk_result()
        exec_result = await engine.execute_signal(signal, risk)
        result = await engine.update_stops(exec_result.deal_id, 1970.0)
        assert result.success is True

    def test_mode_property(self, engine):
        assert engine.mode == ExecutionMode.PAPER
