"""
Tests for TradeLogger - Structured logging system.
"""
import pytest
from datetime import datetime
from pathlib import Path
import json
import tempfile

from src.monitoring.trade_logger import (
    TradeLogger,
    SignalLog,
    ExecutionLog,
    RiskEventLog,
    SignalType,
    ExecutionStatus,
    RiskEventType,
    get_trade_logger,
)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_log_dir():
    """Create temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def trade_logger(temp_log_dir):
    """Create TradeLogger instance with temp directory."""
    return TradeLogger(log_dir=temp_log_dir)


# ═══════════════════════════════════════════════════════════════════════════
# Pydantic Model Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_signal_log_valid():
    """Test SignalLog creation with valid data."""
    signal = SignalLog(
        epic="XAUUSD",
        direction=SignalType.LONG,
        confidence=0.75,
        strategy="ml_strategy",
        features={"rsi_14": 45.2, "macd": 0.8},
        model_version="xgb_v1.2.0",
        model_proba={"LONG": 0.75, "SHORT": 0.15, "HOLD": 0.10},
    )

    assert signal.epic == "XAUUSD"
    assert signal.direction == SignalType.LONG
    assert signal.confidence == 0.75
    assert signal.strategy == "ml_strategy"
    assert signal.features["rsi_14"] == 45.2
    assert signal.model_version == "xgb_v1.2.0"
    assert signal.model_proba["LONG"] == 0.75


def test_signal_log_confidence_validation():
    """Test SignalLog confidence must be in [0.0, 1.0]."""
    # Valid confidence
    signal = SignalLog(
        epic="BTCUSD",
        direction=SignalType.SHORT,
        confidence=0.5,
        strategy="test",
    )
    assert signal.confidence == 0.5

    # Invalid confidence (out of range)
    with pytest.raises(ValueError):
        SignalLog(
            epic="BTCUSD",
            direction=SignalType.SHORT,
            confidence=1.5,  # > 1.0
            strategy="test",
        )

    with pytest.raises(ValueError):
        SignalLog(
            epic="BTCUSD",
            direction=SignalType.SHORT,
            confidence=-0.1,  # < 0.0
            strategy="test",
        )


def test_execution_log_valid():
    """Test ExecutionLog creation with valid data."""
    execution = ExecutionLog(
        deal_id="DEAL123456",
        epic="US500",
        direction="BUY",
        size=1.0,
        entry_price=4500.25,
        stop_loss=4490.00,
        take_profit=4520.00,
        status=ExecutionStatus.EXECUTED,
        kelly_fraction=0.15,
        risk_pct=2.0,
        equity_at_entry=10000.0,
    )

    assert execution.deal_id == "DEAL123456"
    assert execution.epic == "US500"
    assert execution.direction == "BUY"
    assert execution.size == 1.0
    assert execution.entry_price == 4500.25
    assert execution.status == ExecutionStatus.EXECUTED


def test_execution_log_with_exit():
    """Test ExecutionLog with exit details."""
    execution = ExecutionLog(
        deal_id="DEAL789",
        epic="NVDA",
        direction="SELL",
        size=10.0,
        entry_price=500.00,
        status=ExecutionStatus.EXECUTED,
        exit_price=510.00,
        exit_timestamp=datetime.utcnow(),
        realized_pnl=-100.0,
    )

    assert execution.exit_price == 510.00
    assert execution.realized_pnl == -100.0
    assert execution.exit_timestamp is not None


def test_risk_event_log_valid():
    """Test RiskEventLog creation with valid data."""
    risk_event = RiskEventLog(
        event_type=RiskEventType.CIRCUIT_BREAKER,
        epic="XAUUSD",
        description="Daily loss limit exceeded",
        current_equity=9500.0,
        peak_equity=10000.0,
        current_drawdown_pct=5.0,
        daily_pnl=-500.0,
        open_positions=2,
        consecutive_losses=4,
        action="stopped_trading",
    )

    assert risk_event.event_type == RiskEventType.CIRCUIT_BREAKER
    assert risk_event.description == "Daily loss limit exceeded"
    assert risk_event.current_drawdown_pct == 5.0
    assert risk_event.action == "stopped_trading"


# ═══════════════════════════════════════════════════════════════════════════
# TradeLogger Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_log_signal_to_file(trade_logger, temp_log_dir):
    """Test logging signal to file (PostgreSQL fallback)."""
    await trade_logger.log_signal(
        epic="BTCUSD",
        direction=SignalType.LONG,
        confidence=0.82,
        strategy="ml_strategy",
        features={"bb_position": 0.3, "rsi": 55.0},
        model_version="xgb_v1.0.0",
    )

    # Check file was created and contains correct data
    signal_file = temp_log_dir / "signals.jsonl"
    assert signal_file.exists()

    with open(signal_file, "r") as f:
        line = f.readline()
        data = json.loads(line)

    assert data["epic"] == "BTCUSD"
    assert data["direction"] == "LONG"
    assert data["confidence"] == 0.82
    assert data["strategy"] == "ml_strategy"
    assert data["features"]["rsi"] == 55.0


@pytest.mark.asyncio
async def test_log_execution_to_file(trade_logger, temp_log_dir):
    """Test logging execution to file (PostgreSQL fallback)."""
    await trade_logger.log_execution(
        epic="XAUUSD",
        direction="BUY",
        size=0.5,
        entry_price=2050.25,
        status=ExecutionStatus.EXECUTED,
        deal_id="DEAL999",
        stop_loss=2045.00,
        take_profit=2060.00,
        kelly_fraction=0.10,
    )

    # Check file was created
    exec_file = temp_log_dir / "executions.jsonl"
    assert exec_file.exists()

    with open(exec_file, "r") as f:
        line = f.readline()
        data = json.loads(line)

    assert data["epic"] == "XAUUSD"
    assert data["deal_id"] == "DEAL999"
    assert data["size"] == 0.5
    assert data["entry_price"] == 2050.25
    assert data["status"] == "executed"


@pytest.mark.asyncio
async def test_log_risk_decision_to_file(trade_logger, temp_log_dir):
    """Test logging risk decision to file (PostgreSQL fallback)."""
    await trade_logger.log_risk_decision(
        event_type=RiskEventType.DAILY_LOSS,
        description="Daily loss limit exceeded (-5.2%)",
        action="stopped_trading",
        epic="BTCUSD",
        current_equity=9480.0,
        peak_equity=10000.0,
        current_drawdown_pct=5.2,
        daily_pnl=-520.0,
    )

    # Check file was created
    risk_file = temp_log_dir / "risk_events.jsonl"
    assert risk_file.exists()

    with open(risk_file, "r") as f:
        line = f.readline()
        data = json.loads(line)

    assert data["event_type"] == "daily_loss"
    assert data["description"] == "Daily loss limit exceeded (-5.2%)"
    assert data["action"] == "stopped_trading"
    assert data["current_drawdown_pct"] == 5.2


@pytest.mark.asyncio
async def test_multiple_signals_to_file(trade_logger, temp_log_dir):
    """Test logging multiple signals appends to file."""
    for i in range(3):
        await trade_logger.log_signal(
            epic=f"TEST{i}",
            direction=SignalType.LONG if i % 2 == 0 else SignalType.SHORT,
            confidence=0.5 + i * 0.1,
            strategy="test_strategy",
        )

    signal_file = temp_log_dir / "signals.jsonl"
    with open(signal_file, "r") as f:
        lines = f.readlines()

    assert len(lines) == 3

    # Verify each line is valid JSON
    for line in lines:
        data = json.loads(line)
        assert "epic" in data
        assert "direction" in data
        assert "confidence" in data


@pytest.mark.asyncio
async def test_log_signal_with_rejection(trade_logger):
    """Test logging signal with rejection reason."""
    await trade_logger.log_signal(
        epic="WTIUSD",
        direction=SignalType.SHORT,
        confidence=0.65,
        strategy="vwap_strategy",
        execution_status=ExecutionStatus.REJECTED,
        rejection_reason="Circuit breaker active",
    )

    # Should not raise error
    assert True


def test_get_trade_logger_singleton():
    """Test global TradeLogger singleton."""
    logger1 = get_trade_logger()
    logger2 = get_trade_logger()

    # Should be same instance
    assert logger1 is logger2


def test_signal_log_serialization():
    """Test SignalLog JSON serialization."""
    signal = SignalLog(
        epic="EURUSD",
        direction=SignalType.HOLD,
        confidence=0.3,
        strategy="squeeze_strategy",
        features={"rsi_14": 55.0, "momentum": -0.2},
    )

    # Test Pydantic model_dump_json
    json_str = signal.model_dump_json()
    data = json.loads(json_str)

    assert data["epic"] == "EURUSD"
    assert data["direction"] == "HOLD"
    assert data["features"]["rsi_14"] == 55.0
    assert data["features"]["momentum"] == -0.2


def test_execution_log_serialization():
    """Test ExecutionLog JSON serialization."""
    execution = ExecutionLog(
        epic="TSLA",
        direction="BUY",
        size=5.0,
        entry_price=250.50,
        status=ExecutionStatus.EXEC_FAILED,
        error_message="Insufficient margin",
    )

    json_str = execution.model_dump_json()
    data = json.loads(json_str)

    assert data["epic"] == "TSLA"
    assert data["status"] == "exec_failed"
    assert data["error_message"] == "Insufficient margin"


def test_risk_event_log_serialization():
    """Test RiskEventLog JSON serialization."""
    risk_event = RiskEventLog(
        event_type=RiskEventType.POSITION_LIMIT,
        description="Max 5 open positions exceeded",
        action="rejected_trade",
        open_positions=5,
    )

    json_str = risk_event.model_dump_json()
    data = json.loads(json_str)

    assert data["event_type"] == "position_limit"
    assert data["action"] == "rejected_trade"
    assert data["open_positions"] == 5


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


def test_signal_log_empty_features():
    """Test SignalLog with empty features dict."""
    signal = SignalLog(
        epic="DE40",
        direction=SignalType.LONG,
        confidence=0.55,
        strategy="test",
        features={},  # Empty dict
    )

    assert signal.features == {}


def test_execution_log_no_stops():
    """Test ExecutionLog without stop loss or take profit."""
    execution = ExecutionLog(
        epic="XAGUSD",
        direction="SELL",
        size=10.0,
        entry_price=25.50,
        status=ExecutionStatus.EXECUTED,
        # No stop_loss or take_profit
    )

    assert execution.stop_loss is None
    assert execution.take_profit is None


def test_risk_event_log_global_event():
    """Test RiskEventLog for global event (no specific epic)."""
    risk_event = RiskEventLog(
        event_type=RiskEventType.EQUITY_FILTER,
        epic=None,  # Global event
        description="Equity below 20-day SMA",
        action="halved_position_size",
        current_equity=9800.0,
    )

    assert risk_event.epic is None
    assert risk_event.action == "halved_position_size"


@pytest.mark.asyncio
async def test_trade_logger_init_creates_dir(temp_log_dir):
    """Test TradeLogger creates log directory if not exists."""
    new_dir = temp_log_dir / "new_logs"
    assert not new_dir.exists()

    logger = TradeLogger(log_dir=new_dir)
    assert new_dir.exists()
    assert logger.log_dir == new_dir
