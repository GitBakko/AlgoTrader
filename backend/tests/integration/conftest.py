"""
Integration test fixtures.
These tests verify that the full pipeline works end-to-end
without requiring external services (broker, PostgreSQL, Redis).
"""

import pytest
import numpy as np
import polars as pl
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.execution.execution_engine import ExecutionEngine
from src.execution.schemas import ExecutionMode
from src.risk.risk_manager import RiskManager
from src.risk.schemas import RiskLimits
from src.strategy.strategy_manager import StrategyManager


@pytest.fixture
def sample_ohlc_df():
    """Create sample OHLC DataFrame with 200 bars (enough for feature engineering)."""
    n = 200
    base_price = 2000.0
    dates = [
        datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(hours=i)
        for i in range(n)
    ]

    np.random.seed(42)
    closes = base_price + np.cumsum(np.random.randn(n) * 5)
    highs = closes + np.abs(np.random.randn(n) * 3)
    lows = closes - np.abs(np.random.randn(n) * 3)
    opens = closes + np.random.randn(n) * 2
    volumes = np.random.randint(1000, 10000, n)

    return pl.DataFrame({
        "timestamp": dates,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes.astype(float),
    })


@pytest.fixture
def engine():
    """Paper mode execution engine."""
    return ExecutionEngine(mode=ExecutionMode.PAPER)


@pytest.fixture
def risk_mgr():
    """Risk manager with default limits."""
    return RiskManager(initial_equity=10000.0, limits=RiskLimits())


@pytest.fixture
def strategy_mgr():
    """Strategy manager."""
    return StrategyManager()
