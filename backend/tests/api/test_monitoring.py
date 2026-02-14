"""
Tests for Monitoring API endpoints.
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
from datetime import datetime

from src.api.main import app
from src.monitoring.log_analyzer import SignalStats, ExecutionStats, RiskStats

client = TestClient(app)


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def mock_signal_stats():
    """Mock SignalStats for testing."""
    return SignalStats(
        total_signals=100,
        executed=75,
        rejected=20,
        hold=5,
        execution_rate_pct=75.0,
        by_epic={"XAUUSD": 50, "BTCUSD": 50},
        by_strategy={"ml_strategy": 60, "vwap_strategy": 40},
        by_direction={"LONG": 45, "SHORT": 50, "HOLD": 5},
    )


@pytest.fixture
def mock_execution_stats():
    """Mock ExecutionStats for testing."""
    return ExecutionStats(
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


@pytest.fixture
def mock_risk_stats():
    """Mock RiskStats for testing."""
    return RiskStats(
        total_events=10,
        circuit_breaker_triggers=2,
        position_limit_hits=4,
        drawdown_limit_hits=4,
        max_drawdown_pct=5.5,
        avg_daily_pnl=-50.0,
        by_event_type={"circuit_breaker": 2, "position_limit": 4, "drawdown_limit": 4},
        last_event_timestamp=datetime.utcnow(),
    )


# ═══════════════════════════════════════════════════════════════════════════
# GET /monitoring/logs/signals Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_get_signal_logs_success(mock_signal_stats):
    """Test GET /monitoring/logs/signals returns signal statistics."""
    with patch("src.api.routers.monitoring.get_log_analyzer") as mock_analyzer:
        mock_instance = AsyncMock()
        mock_instance.get_signal_stats.return_value = mock_signal_stats
        mock_analyzer.return_value = mock_instance

        response = client.get("/api/monitoring/logs/signals?days=30")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "period" in data["data"]
    assert data["data"]["period"]["days"] == 30
    assert "summary" in data["data"]
    assert data["data"]["summary"]["total_signals"] == 100
    assert data["data"]["summary"]["execution_rate_pct"] == 75.0
    assert "by_epic" in data["data"]
    assert "XAUUSD" in data["data"]["by_epic"]


def test_get_signal_logs_custom_days():
    """Test GET /monitoring/logs/signals with custom days parameter."""
    response = client.get("/api/monitoring/logs/signals?days=7")

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["period"]["days"] == 7


def test_get_signal_logs_invalid_days():
    """Test GET /monitoring/logs/signals with invalid days parameter."""
    # days too large
    response = client.get("/api/monitoring/logs/signals?days=500")

    assert response.status_code == 422  # Validation error


# ═══════════════════════════════════════════════════════════════════════════
# GET /monitoring/logs/executions Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_get_execution_logs_success(mock_execution_stats):
    """Test GET /monitoring/logs/executions returns execution statistics."""
    with patch("src.api.routers.monitoring.get_log_analyzer") as mock_analyzer:
        mock_instance = AsyncMock()
        mock_instance.get_execution_stats.return_value = mock_execution_stats
        mock_analyzer.return_value = mock_instance

        response = client.get("/api/monitoring/logs/executions?days=30")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "summary" in data["data"]
    assert data["data"]["summary"]["total_trades"] == 50
    assert data["data"]["summary"]["win_rate_pct"] == 66.67
    assert data["data"]["summary"]["profit_factor"] == 3.0


# ═══════════════════════════════════════════════════════════════════════════
# GET /monitoring/logs/risk-events Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_get_risk_event_logs_success(mock_risk_stats):
    """Test GET /monitoring/logs/risk-events returns risk statistics."""
    with patch("src.api.routers.monitoring.get_log_analyzer") as mock_analyzer:
        mock_instance = AsyncMock()
        mock_instance.get_risk_stats.return_value = mock_risk_stats
        mock_analyzer.return_value = mock_instance

        response = client.get("/api/monitoring/logs/risk-events?days=30")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "summary" in data["data"]
    assert data["data"]["summary"]["total_events"] == 10
    assert data["data"]["summary"]["circuit_breaker_triggers"] == 2
    assert data["data"]["summary"]["max_drawdown_pct"] == 5.5


# ═══════════════════════════════════════════════════════════════════════════
# GET /monitoring/stats/performance Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_get_performance_overview_success(mock_signal_stats, mock_execution_stats, mock_risk_stats):
    """Test GET /monitoring/stats/performance returns combined stats."""
    with patch("src.api.routers.monitoring.get_log_analyzer") as mock_analyzer:
        mock_instance = AsyncMock()
        mock_instance.get_signal_stats.return_value = mock_signal_stats
        mock_instance.get_execution_stats.return_value = mock_execution_stats
        mock_instance.get_risk_stats.return_value = mock_risk_stats
        mock_analyzer.return_value = mock_instance

        response = client.get("/api/monitoring/stats/performance?days=7")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "health_score" in data["data"]
    assert 0 <= data["data"]["health_score"] <= 100
    assert "signals" in data["data"]
    assert "execution" in data["data"]
    assert "risk" in data["data"]


def test_get_performance_overview_default_days():
    """Test GET /monitoring/stats/performance with default days (7)."""
    response = client.get("/api/monitoring/stats/performance")

    assert response.status_code == 200
    data = response.json()
    assert data["data"]["period"]["days"] == 7


# ═══════════════════════════════════════════════════════════════════════════
# Health Score Calculation Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_calculate_health_score_excellent():
    """Test health score calculation for excellent performance."""
    from src.api.routers.monitoring import _calculate_health_score

    signal_stats = SignalStats(
        total_signals=100,
        executed=65,
        rejected=30,
        hold=5,
        execution_rate_pct=65.0,  # Optimal
        by_epic={},
        by_strategy={},
        by_direction={},
    )

    execution_stats = ExecutionStats(
        total_trades=50,
        open_positions=2,
        closed_trades=48,
        total_pnl=2000.0,
        avg_pnl=41.67,
        wins=30,
        losses=18,
        win_rate_pct=62.5,  # Good
        avg_win=100.0,
        avg_loss=-30.0,
        profit_factor=3.33,
        avg_duration_hours=12.0,
        by_epic={},
    )

    risk_stats = RiskStats(
        total_events=1,
        circuit_breaker_triggers=0,  # None
        position_limit_hits=1,
        drawdown_limit_hits=0,
        max_drawdown_pct=3.0,  # Low
        avg_daily_pnl=50.0,
        by_event_type={},
        last_event_timestamp=None,
    )

    score = _calculate_health_score(signal_stats, execution_stats, risk_stats)
    assert score >= 85  # Should be high


def test_calculate_health_score_poor():
    """Test health score calculation for poor performance."""
    from src.api.routers.monitoring import _calculate_health_score

    signal_stats = SignalStats(
        total_signals=100,
        executed=15,  # Very low
        rejected=80,
        hold=5,
        execution_rate_pct=15.0,
        by_epic={},
        by_strategy={},
        by_direction={},
    )

    execution_stats = ExecutionStats(
        total_trades=20,
        open_positions=1,
        closed_trades=19,
        total_pnl=-500.0,
        avg_pnl=-26.32,
        wins=5,
        losses=14,
        win_rate_pct=26.32,  # Poor
        avg_win=50.0,
        avg_loss=-60.0,
        profit_factor=0.42,
        avg_duration_hours=6.0,
        by_epic={},
    )

    risk_stats = RiskStats(
        total_events=20,
        circuit_breaker_triggers=8,  # High
        position_limit_hits=7,
        drawdown_limit_hits=5,
        max_drawdown_pct=12.0,  # High
        avg_daily_pnl=-100.0,
        by_event_type={},
        last_event_timestamp=None,
    )

    score = _calculate_health_score(signal_stats, execution_stats, risk_stats)
    assert score <= 30  # Should be low


# ═══════════════════════════════════════════════════════════════════════════
# Error Handling Tests
# ═══════════════════════════════════════════════════════════════════════════


def test_get_signal_logs_analyzer_error():
    """Test GET /monitoring/logs/signals handles analyzer errors gracefully."""
    with patch("src.api.routers.monitoring.get_log_analyzer") as mock_analyzer:
        mock_instance = AsyncMock()
        mock_instance.get_signal_stats.side_effect = Exception("Database error")
        mock_analyzer.return_value = mock_instance

        response = client.get("/api/monitoring/logs/signals?days=30")

    assert response.status_code == 400  # error_response returns 400
    data = response.json()
    assert data["success"] is False
    assert "error" in data
    assert "Database error" in data["error"]


def test_get_execution_logs_analyzer_error():
    """Test GET /monitoring/logs/executions handles analyzer errors gracefully."""
    with patch("src.api.routers.monitoring.get_log_analyzer") as mock_analyzer:
        mock_instance = AsyncMock()
        mock_instance.get_execution_stats.side_effect = Exception("Connection timeout")
        mock_analyzer.return_value = mock_instance

        response = client.get("/api/monitoring/logs/executions?days=7")

    assert response.status_code == 400  # error_response returns 400
    data = response.json()
    assert data["success"] is False


def test_get_performance_overview_partial_failure():
    """Test GET /monitoring/stats/performance handles partial failures."""
    with patch("src.api.routers.monitoring.get_log_analyzer") as mock_analyzer:
        mock_instance = AsyncMock()
        # One stat succeeds, others fail
        mock_instance.get_signal_stats.side_effect = Exception("Error")
        mock_instance.get_execution_stats.side_effect = Exception("Error")
        mock_instance.get_risk_stats.side_effect = Exception("Error")
        mock_analyzer.return_value = mock_instance

        response = client.get("/api/monitoring/stats/performance?days=7")

    assert response.status_code == 400  # error_response returns 400
    data = response.json()
    assert data["success"] is False
