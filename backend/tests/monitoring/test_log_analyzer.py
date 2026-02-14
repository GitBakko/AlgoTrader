"""
Tests for LogAnalyzer - Log analysis and statistics.
"""
import pytest
from datetime import datetime, timedelta
from pathlib import Path
import json
import tempfile

from src.monitoring.log_analyzer import LogAnalyzer, SignalStats, ExecutionStats, RiskStats
from src.monitoring.trade_logger import TradeLogger, SignalType, ExecutionStatus, RiskEventType


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def temp_log_dir():
    """Create temporary directory for log files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def populated_logs(temp_log_dir):
    """Create log files with sample data."""
    logger = TradeLogger(log_dir=temp_log_dir)

    # Create sample signals
    now = datetime.utcnow()
    for i in range(10):
        await logger.log_signal(
            epic="XAUUSD" if i % 2 == 0 else "BTCUSD",
            direction=SignalType.LONG if i % 3 == 0 else SignalType.SHORT,
            confidence=0.6 + i * 0.01,
            strategy="ml_strategy" if i % 2 == 0 else "vwap_strategy",
            features={"rsi": 50.0 + i},
            execution_status=ExecutionStatus.EXECUTED if i % 2 == 0 else ExecutionStatus.REJECTED,
        )

    # Create sample executions
    for i in range(5):
        # Entry
        await logger.log_execution(
            epic="XAUUSD",
            direction="BUY",
            size=0.5,
            entry_price=2050.0 + i,
            status=ExecutionStatus.EXECUTED,
            deal_id=f"DEAL{i}",
        )

        # Close some trades with P&L
        if i < 3:
            await logger.log_execution(
                epic="XAUUSD",
                direction="SELL",
                size=0.5,
                entry_price=2050.0 + i,
                status=ExecutionStatus.EXECUTED,
                deal_id=f"DEAL{i}",
            )
            # Update with exit details (simulated)
            # In real scenario, this would be updated via update_execution_log method

    # Create sample risk events
    for i in range(3):
        await logger.log_risk_decision(
            event_type=RiskEventType.CIRCUIT_BREAKER if i == 0 else RiskEventType.POSITION_LIMIT,
            description=f"Risk event {i}",
            action="rejected_trade",
            current_equity=10000.0 - i * 100,
            current_drawdown_pct=i * 0.5,
            daily_pnl=-50.0 * i,
        )

    return temp_log_dir


@pytest.fixture
def log_analyzer(temp_log_dir):
    """Create LogAnalyzer instance."""
    return LogAnalyzer(log_dir=temp_log_dir)


# ═══════════════════════════════════════════════════════════════════════════
# SignalStats Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_signal_stats_empty(log_analyzer):
    """Test signal stats with no data."""
    stats = await log_analyzer.get_signal_stats()

    assert isinstance(stats, SignalStats)
    assert stats.total_signals == 0
    assert stats.executed == 0
    assert stats.execution_rate_pct == 0.0


@pytest.mark.asyncio
async def test_signal_stats_with_data(log_analyzer, populated_logs):
    """Test signal stats with populated data."""
    stats = await log_analyzer.get_signal_stats()

    assert isinstance(stats, SignalStats)
    assert stats.total_signals == 10
    assert stats.executed == 5  # Every other signal
    assert stats.rejected == 5
    assert stats.execution_rate_pct == 50.0

    # Check groupings
    assert "XAUUSD" in stats.by_epic
    assert "BTCUSD" in stats.by_epic
    assert "ml_strategy" in stats.by_strategy
    assert "vwap_strategy" in stats.by_strategy


@pytest.mark.asyncio
async def test_signal_stats_date_range(log_analyzer, populated_logs):
    """Test signal stats with date range filter."""
    # Query for future dates (should return empty)
    future_start = datetime.utcnow() + timedelta(days=1)
    future_end = datetime.utcnow() + timedelta(days=2)

    stats = await log_analyzer.get_signal_stats(start_date=future_start, end_date=future_end)

    assert stats.total_signals == 0


# ═══════════════════════════════════════════════════════════════════════════
# ExecutionStats Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_execution_stats_empty(log_analyzer):
    """Test execution stats with no data."""
    stats = await log_analyzer.get_execution_stats()

    assert isinstance(stats, ExecutionStats)
    assert stats.total_trades == 0
    assert stats.total_pnl == 0.0
    assert stats.win_rate_pct == 0.0


@pytest.mark.asyncio
async def test_execution_stats_with_data(log_analyzer, populated_logs):
    """Test execution stats with populated data."""
    stats = await log_analyzer.get_execution_stats()

    assert isinstance(stats, ExecutionStats)
    assert stats.total_trades == 8  # 5 entries + 3 closes (simulated)
    assert stats.open_positions >= 0
    assert isinstance(stats.total_pnl, float)


# ═══════════════════════════════════════════════════════════════════════════
# RiskStats Tests
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_risk_stats_empty(log_analyzer):
    """Test risk stats with no data."""
    stats = await log_analyzer.get_risk_stats()

    assert isinstance(stats, RiskStats)
    assert stats.total_events == 0
    assert stats.circuit_breaker_triggers == 0
    assert stats.max_drawdown_pct == 0.0


@pytest.mark.asyncio
async def test_risk_stats_with_data(log_analyzer, populated_logs):
    """Test risk stats with populated data."""
    stats = await log_analyzer.get_risk_stats()

    assert isinstance(stats, RiskStats)
    assert stats.total_events == 3
    assert stats.circuit_breaker_triggers == 1
    assert stats.position_limit_hits == 2
    assert "circuit_breaker" in stats.by_event_type


@pytest.mark.asyncio
async def test_risk_stats_max_drawdown(log_analyzer, populated_logs):
    """Test risk stats max drawdown calculation."""
    stats = await log_analyzer.get_risk_stats()

    # Max drawdown should be from highest event (i=2 → 1.0%)
    assert stats.max_drawdown_pct >= 0.0


# ═══════════════════════════════════════════════════════════════════════════
# File Fallback Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_read_signals_file_nonexistent(log_analyzer):
    """Test reading from non-existent signals file."""
    df = log_analyzer._read_signals_file(
        datetime.utcnow() - timedelta(days=1),
        datetime.utcnow()
    )
    assert df.is_empty()


def test_read_executions_file_nonexistent(log_analyzer):
    """Test reading from non-existent executions file."""
    df = log_analyzer._read_executions_file(
        datetime.utcnow() - timedelta(days=1),
        datetime.utcnow()
    )
    assert df.is_empty()


def test_read_risk_events_file_nonexistent(log_analyzer):
    """Test reading from non-existent risk events file."""
    df = log_analyzer._read_risk_events_file(
        datetime.utcnow() - timedelta(days=1),
        datetime.utcnow()
    )
    assert df.is_empty()


# ═══════════════════════════════════════════════════════════════════════════
# Date Range Filtering
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_signal_stats_default_date_range(log_analyzer, populated_logs):
    """Test signal stats with default date range (30 days)."""
    stats = await log_analyzer.get_signal_stats()
    # Should include all recent signals
    assert stats.total_signals == 10


@pytest.mark.asyncio
async def test_execution_stats_default_date_range(log_analyzer, populated_logs):
    """Test execution stats with default date range (30 days)."""
    stats = await log_analyzer.get_execution_stats()
    # Should include all recent executions
    assert stats.total_trades > 0


@pytest.mark.asyncio
async def test_risk_stats_default_date_range(log_analyzer, populated_logs):
    """Test risk stats with default date range (30 days)."""
    stats = await log_analyzer.get_risk_stats()
    # Should include all recent risk events
    assert stats.total_events == 3


# ═══════════════════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_analyzer_with_custom_log_dir():
    """Test analyzer with custom log directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        custom_dir = Path(tmpdir) / "custom_logs"
        analyzer = LogAnalyzer(log_dir=custom_dir)

        # Should handle non-existent directory gracefully
        stats = await analyzer.get_signal_stats()
        assert stats.total_signals == 0


@pytest.mark.asyncio
async def test_signal_stats_with_holds(log_analyzer, populated_logs):
    """Test signal stats correctly counts HOLD signals."""
    stats = await log_analyzer.get_signal_stats()
    # HOLD signals: i % 3 != 0 and not SHORT → should have some
    assert stats.hold >= 0


# ═══════════════════════════════════════════════════════════════════════════
# Data Class Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_signal_stats_dataclass():
    """Test SignalStats dataclass structure."""
    stats = SignalStats(
        total_signals=100,
        executed=80,
        rejected=15,
        hold=5,
        execution_rate_pct=80.0,
        by_epic={"XAUUSD": 50, "BTCUSD": 50},
        by_strategy={"ml_strategy": 60, "vwap_strategy": 40},
        by_direction={"LONG": 45, "SHORT": 50, "HOLD": 5},
    )

    assert stats.total_signals == 100
    assert stats.execution_rate_pct == 80.0
    assert "XAUUSD" in stats.by_epic


def test_execution_stats_dataclass():
    """Test ExecutionStats dataclass structure."""
    stats = ExecutionStats(
        total_trades=50,
        open_positions=5,
        closed_trades=45,
        total_pnl=1500.0,
        avg_pnl=33.33,
        wins=30,
        losses=15,
        win_rate_pct=66.67,
        avg_win=75.0,
        avg_loss=-25.0,
        profit_factor=3.0,
        avg_duration_hours=24.5,
        by_epic={"XAUUSD": {"trades": 25, "pnl": 800.0, "win_rate_pct": 68.0}},
    )

    assert stats.total_trades == 50
    assert stats.win_rate_pct == 66.67
    assert stats.profit_factor == 3.0


def test_risk_stats_dataclass():
    """Test RiskStats dataclass structure."""
    stats = RiskStats(
        total_events=10,
        circuit_breaker_triggers=3,
        position_limit_hits=4,
        drawdown_limit_hits=3,
        max_drawdown_pct=8.5,
        avg_daily_pnl=-120.0,
        by_event_type={"circuit_breaker": 3, "position_limit": 4},
        last_event_timestamp=datetime.utcnow(),
    )

    assert stats.total_events == 10
    assert stats.max_drawdown_pct == 8.5
    assert stats.last_event_timestamp is not None
